import optuna
import joblib
import logging
import os
import sys
import random
import copy
import numpy as np

# Ensure proper path visibility
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.interface.carmaker_interface import CarMakerInterface
from src.database.data_handler import ResultHandler
from src.core.parameter_manager import ParameterManager
from src.core.resource_manager import ResourceManager
from src.core.surrogate import SurrogateOracle
from src.core.delta_learner import DeltaLearner # <--- GEN 3.0 ADDITION

logger = logging.getLogger(__name__)

class OptimizationOrchestrator:
    def __init__(self, project_root, cm_exe_path, study_name, storage_url, n_workers=4):
        self.project_root = project_root
        
        # Init Sub-Systems
        self.param_manager = ParameterManager(
            template_dir=os.path.join(project_root, "templates", "TestRuns"), 
            work_dir=project_root
        )
        self.data_handler = ResultHandler(
            parquet_storage_path=os.path.join(project_root, "data", "parquet_store")
        )
        self.interface = CarMakerInterface(cm_exe_path, project_root)
        self.resources = ResourceManager(start_port=16660, max_licenses=n_workers)
        
        # --- INTELLIGENCE MODULES ---
        self.surrogate = SurrogateOracle()
        self.delta_learner = DeltaLearner() # <--- GEN 3.0 ADDITION
        
        # Multi-Objective Study
        self.study = optuna.create_study(
            study_name=study_name,
            storage=storage_url,
            directions=["minimize", "minimize"], 
            load_if_exists=True,
            # We remove the median pruner because we now handle logic internally via Surrogate
            pruner=optuna.pruners.NopPruner() 
        )
        logger.info(f"Gen 3.0 Orchestrator initialized for Study: '{study_name}'")

    def objective(self, trial: optuna.Trial):
        run_id = f"Run_{trial.number:04d}"
        
        # 1. Search Space
        params = {
            "k_spring_f": trial.suggest_float("k_spring_f", 20000, 100000),
            "k_spring_r": trial.suggest_float("k_spring_r", 20000, 100000),
            "c_damp_f": trial.suggest_float("c_damp_f", 1000, 8000),
            "c_damp_r": trial.suggest_float("c_damp_r", 1000, 8000),
            "mass_scale": trial.suggest_float("mass_scale", 0.95, 1.05)
        }

        # --- 2. ACQUISITION GATE (Sim-to-Real Aware) ---
        run_real_sim = True
        predicted_vals = (999.0, 99.0)
        
        if self.surrogate.is_trained:
            # A. Physics Prediction (CarMaker Surrogate)
            pred_res, phys_uncertainty, is_novel = self.surrogate.evaluate_trust(params)
            pred_time = pred_res[0]

            # B. Reality Correction (Delta Learner)
            # If CarMaker is 1.0s too optimistic, we add +1.0s here.
            bias_mean, bias_std = self.delta_learner.predict_bias(params)
            
            # C. Fused Prediction
            corrected_time = pred_time + bias_mean
            # Combine uncertainties (RMS)
            total_uncertainty = np.sqrt(phys_uncertainty**2 + bias_std**2)
            
            # Record Context (Target to beat)
            best_trials = [t for t in self.study.best_trials if t.values]
            current_record = min([t.values[0] for t in best_trials]) if best_trials else 999.0

            # Calculate Lower Confidence Bound (Optimistic Look)
            # uses the CORRECTED time and TOTAL uncertainty
            lcb_time = corrected_time - (1.96 * total_uncertainty)

            # --- DECISION MATRIX ---
            if is_novel:
                logger.info(f"[{run_id}] 🔭 Novel Design (Dist > {self.surrogate.max_trusted_distance:.2f}). Exploration Required.")
                run_real_sim = True
                trial.set_user_attr("decision_reason", "Exploration_Novelty")
            
            elif lcb_time < current_record:
                # If the optimistic prediction (Sim + Bias - Uncertainty) beats record
                logger.info(f"[{run_id}] ⚡ Potential Winner (LCB {lcb_time:.2f} < {current_record:.2f}). Verifying.")
                run_real_sim = True
                trial.set_user_attr("decision_reason", "Exploitation_Potential")

            else:
                # --- SOFT PRUNING ---
                logger.info(f"[{run_id}] 📉 Soft Pruned. Fused Pred {corrected_time:.2f}s (Sim {pred_time:.2f} + Bias {bias_mean:.2f}).")
                run_real_sim = False
                # Return Corrected Time so Optuna learns the "Real World" surface
                predicted_vals = (corrected_time, pred_res[1]) 
                trial.set_user_attr("decision_reason", "Soft_Prune_Skipped")
                trial.set_user_attr("fidelity", "surrogate_corrected") # Mark as synthetic + corrected
        
        # --- 3. EXECUTION ---
        if run_real_sim:
            res = self._run_carmaker_simulation(run_id, params, trial)
            
            # Feed the brain (Real Physics Data Only)
            self.surrogate.add_observation(params, res)
            
            # Retrain periodically
            if len(self.study.trials) % self.surrogate.train_frequency == 0:
                self.surrogate.train()
                
            return res
        else:
            # Return the Fused Prediction to Optuna
            return predicted_vals

    def _run_carmaker_simulation(self, run_id, params, trial=None):
        """Helper to run the actual sim."""
        try:
            test_run_name = self.param_manager.create_run_configuration(
                run_id, params, "Master_Skidpad"
            )
            
            sim_res = {"status": "PENDING"}
            with self.resources.lease(run_id) as port:
                # Pass sector limits dynamically for the Watchdog
                sim_res = self.interface.run_simulation(
                    test_run_name=test_run_name, 
                    tcp_port=port, 
                    timeout_sec=180,
                    trial=trial,
                    sector_limits={"Sector 1": 28.0} # Dynamic Pruning Config
                )
            
            if sim_res.get("status") == "PRUNED": raise optuna.TrialPruned()
            if sim_res.get("status") != "SUCCESS": return 999.0, 99.0
            
            # Measure
            erg_path = os.path.join(self.project_root, "SimOutput", f"{test_run_name}.erg")
            kpis = self.data_handler.process_results(run_id, erg_path)
            
            cost = kpis.get("cost", 999.0)
            max_roll = kpis.get("max_roll", 99.0)
            
            # Attributes
            if trial:
                trial.set_user_attr("source", "CarMaker")
                trial.set_user_attr("fidelity", "high")
                trial.set_user_attr("lap_time", cost)
                trial.set_user_attr("max_roll", max_roll)
                trial.set_user_attr("understeer_grad", kpis.get("understeer_grad", 0.0))
                trial.set_user_attr("yaw_gain", kpis.get("yaw_gain", 0.0))
                trial.set_user_attr("steering_rms", kpis.get("steering_rms", 0.0))
                # Gen 2.0 Metrics
                trial.set_user_attr("stability_index", kpis.get("stability_index", 0.0))
                trial.set_user_attr("response_lag", kpis.get("response_lag", 0.0))
            
            return cost, max_roll

        except optuna.TrialPruned:
            raise
        except Exception as e:
            logger.error(f"Sim failed: {e}")
            return 999.0, 99.0

    def verify_robustness(self, best_trial):
        """Runs stress tests on the winning setup."""
        logger.info(f"🛡️ Starting Robustness Check for Run_{best_trial.number}...")
        base_params = best_trial.params
        variations = []
        
        # 1. Mass +5%
        v1 = copy.deepcopy(base_params)
        v1['mass_scale'] = base_params['mass_scale'] * 1.05
        variations.append(("Mass+5%", v1))
        
        # 2. Springs -5%
        v2 = copy.deepcopy(base_params)
        v2['k_spring_f'] *= 0.95
        v2['k_spring_r'] *= 0.95
        variations.append(("Springs-5%", v2))

        results = {}
        for name, params in variations:
            check_id = f"Robust_{best_trial.number}_{name}"
            res = self._run_carmaker_simulation(check_id, params, trial=None) 
            results[name] = res[0]
            
        logger.info(f"🛡️ Robustness Results: {results}")
        self.study.set_user_attr(f"robustness_run_{best_trial.number}", results)
        return results

    def run(self, n_trials=50, n_jobs=1):
        if n_jobs > 1:
            with joblib.parallel_backend("threading", n_jobs=n_jobs):
                self.study.optimize(self.objective, n_trials=n_trials, n_jobs=n_jobs)
        else:
            self.study.optimize(self.objective, n_trials=n_trials)
            
        if len(self.study.best_trials) > 0:
            best = min(self.study.best_trials, key=lambda t: t.values[0])
            self.verify_robustness(best)
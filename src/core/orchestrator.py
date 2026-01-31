import optuna
import joblib
import logging
import os
import sys
import random

# Ensure proper path visibility
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.interface.carmaker_interface import CarMakerInterface
from src.database.data_handler import ResultHandler
from src.core.parameter_manager import ParameterManager
from src.core.resource_manager import ResourceManager
from src.core.surrogate import SurrogateOracle 

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
        
        # --- AI SURROGATE ---
        self.surrogate = SurrogateOracle()
        
        # Multi-Objective Study
        self.study = optuna.create_study(
            study_name=study_name,
            storage=storage_url,
            directions=["minimize", "minimize"], 
            load_if_exists=True,
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=1)
        )
        logger.info(f"AI-Enhanced Orchestrator initialized for Study: '{study_name}'")

    def objective(self, trial: optuna.Trial):
        run_id = f"Run_{trial.number:04d}"
        
        # 1. Ask (Search Space)
        params = {
            "k_spring_f": trial.suggest_float("k_spring_f", 20000, 100000),
            "k_spring_r": trial.suggest_float("k_spring_r", 20000, 100000),
            "c_damp_f": trial.suggest_float("c_damp_f", 1000, 8000),
            "c_damp_r": trial.suggest_float("c_damp_r", 1000, 8000),
            "mass_scale": trial.suggest_float("mass_scale", 0.95, 1.05)
        }

        # --- 2. AI INTERVENTION (The Filter) ---
        run_real_sim = True
        predicted_result = None

        if self.surrogate.is_trained:
            predicted_result = self.surrogate.predict(params) # Returns (Time, Roll)
            pred_time = predicted_result[0]

            # Get current best lap time (safe fallback if empty)
            best_trials = [t for t in self.study.best_trials if t.values]
            if best_trials:
                current_record = min([t.values[0] for t in best_trials])
                
                # LOGIC: If AI predicts we are >5% slower than record, SKIP.
                # BUT: Randomly run 10% of "bad" ones anyway to check if AI is lying.
                if pred_time > current_record * 1.05:
                    if random.random() > 0.10: # 90% chance to skip
                        logger.info(f"[{run_id}] 🤖 AI Skipped! Pred: {pred_time:.2f}s (Record: {current_record:.2f}s)")
                        run_real_sim = False
                        
                        # Mark as "AI Prediction" in DB
                        trial.set_user_attr("source", "AI_Surrogate")
                        return predicted_result # Return AI guess to Optuna

        # --- 3. REAL SIMULATION (If AI says it's promising) ---
        if run_real_sim:
            try:
                test_run_name = self.param_manager.create_run_configuration(
                    run_id, params, "Master_Skidpad"
                )
                
                sim_res = {"status": "PENDING"}
                with self.resources.lease(run_id) as port:
                    sim_res = self.interface.run_simulation(
                        test_run_name=test_run_name, 
                        tcp_port=port, 
                        timeout_sec=180,
                        trial=trial 
                    )
                
                if sim_res["status"] == "PRUNED":
                    raise optuna.TrialPruned()

                if sim_res["status"] != "SUCCESS":
                    return 999.0, 99.0 
                
                # Measure
                erg_path = os.path.join(self.project_root, "SimOutput", f"{test_run_name}.erg")
                kpis = self.data_handler.process_results(run_id, erg_path)
                
                real_result = (kpis.get("cost", 999.0), kpis.get("max_roll", 99.0))
                
                # --- 4. FEED THE BRAIN ---
                # Teach the AI the result of this real simulation
                self.surrogate.add_observation(params, real_result)
                
                # Retrain periodically
                if len(self.study.trials) % self.surrogate.train_frequency == 0:
                    self.surrogate.train()

                # --- 5. SAVE METRICS (Including Driver Feel) ---
                trial.set_user_attr("source", "CarMaker")
                trial.set_user_attr("lap_time", real_result[0])
                trial.set_user_attr("max_roll", real_result[1])
                # <--- NEW LINE: Saving the Understeer Gradient for Dashboard --->
                trial.set_user_attr("understeer_grad", kpis.get("understeer_grad", 0.0))

                return real_result

            except optuna.TrialPruned:
                raise
            except Exception as e:
                logger.error(f"[{run_id}] Error: {e}")
                return 999.0, 99.0
        
        # Fallback (should not be reached)
        return 999.0, 99.0

    def run(self, n_trials=50, n_jobs=1):
        logger.info(f"🚀 Starting AI-Enhanced Optimization ({n_trials} trials)...")
        if n_jobs > 1:
            with joblib.parallel_backend("threading", n_jobs=n_jobs):
                self.study.optimize(self.objective, n_trials=n_trials, n_jobs=n_jobs)
        else:
            self.study.optimize(self.objective, n_trials=n_trials)
            
        logger.info(f"✅ Finished. Pareto Front Size: {len(self.study.best_trials)}")
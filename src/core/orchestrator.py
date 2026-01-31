import optuna
import joblib
import logging
import os
from src.interface.carmaker_interface import CarMakerInterface
from src.database.data_handler import ResultHandler
from src.core.parameter_manager import ParameterManager
from src.core.resource_manager import ResourceManager

logger = logging.getLogger(__name__)

class OptimizationOrchestrator:
    def __init__(self, project_root, cm_exe_path, study_name, storage_url, n_workers=4):
        self.project_root = project_root
        
        # Init Sub-Systems
        self.param_manager = ParameterManager(os.path.join(project_root, "templates", "TestRuns"), project_root)
        self.data_handler = ResultHandler(os.path.join(project_root, "data", "parquet_store"))
        self.interface = CarMakerInterface(cm_exe_path, project_root)
        self.resources = ResourceManager(start_port=16660, max_licenses=n_workers)
        
        # --- MULTI-OBJECTIVE SETUP ---
        self.study = optuna.create_study(
            study_name=study_name,
            storage=storage_url,
            # CRITICAL: Two directions for two return values
            # 1. Minimize Lap Time
            # 2. Minimize Body Roll
            directions=["minimize", "minimize"], 
            load_if_exists=True
        )
        logger.info(f"Multi-Objective Study '{study_name}' initialized.")

    def objective(self, trial: optuna.Trial):
        run_id = f"Run_{trial.number:04d}"
        
        # 1. Ask (Params) - No change
        params = {
            "k_spring_f": trial.suggest_float("k_spring_f", 20000, 100000),
            "k_spring_r": trial.suggest_float("k_spring_r", 20000, 100000),
            "c_damp_f": trial.suggest_float("c_damp_f", 1000, 8000),
            "c_damp_r": trial.suggest_float("c_damp_r", 1000, 8000),
            "mass_scale": trial.suggest_float("mass_scale", 0.95, 1.05)
        }

        try:
            # 2. Setup
            test_run = self.param_manager.create_run_configuration(run_id, params, "Master_Skidpad")
            
            # 3. Execute with PRUNING ENABLED
            sim_res = {"status": "PENDING"}
            with self.resources.lease(run_id) as port:
                sim_res = self.interface.run_simulation(
                    test_run_name=test_run, 
                    tcp_port=port, 
                    timeout_sec=180,
                    trial=trial # <--- CRITICAL: Pass the trial object here!
                )
            
            # --- HANDLE PRUNED STATE ---
            if sim_res["status"] == "PRUNED":
                # Raise the specific Optuna exception to mark it properly in the DB
                raise optuna.TrialPruned()

            if sim_res["status"] != "SUCCESS":
                return 999.0, 99.0
            
            # 4. Measure
            erg_path = os.path.join(self.project_root, "SimOutput", f"{test_run}.erg")
            kpis = self.data_handler.process_results(run_id, erg_path)
            
            trial.set_user_attr("lap_time", kpis.get("cost"))
            trial.set_user_attr("max_roll", kpis.get("max_roll"))

            return kpis.get("cost", 999.0), kpis.get("max_roll", 99.0)

        except optuna.TrialPruned:
            # Let Optuna handle this exception naturally
            raise
        except Exception as e:
            logger.error(f"Trial {run_id} failed: {e}")
            return 999.0, 99.0

    def run(self, n_trials=50, n_jobs=1):
        logger.info(f"Starting Multi-Objective Optimization ({n_trials} trials)...")
        if n_jobs > 1:
            with joblib.parallel_backend("threading", n_jobs=n_jobs):
                self.study.optimize(self.objective, n_trials=n_trials, n_jobs=n_jobs)
        else:
            self.study.optimize(self.objective, n_trials=n_trials)
        
        # Log the Pareto Front (Best Trade-offs)
        logger.info(f"Pareto Front Size: {len(self.study.best_trials)}")
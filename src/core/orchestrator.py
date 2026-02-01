import optuna
import joblib
import logging
import os
import sys
import numpy as np

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.interface.carmaker_interface import CarMakerInterface
from src.database.data_handler import ResultHandler
from src.core.parameter_manager import ParameterManager
from src.core.resource_manager import ResourceManager
from src.core.surrogate import SurrogateOracle

logger = logging.getLogger(__name__)

class OptimizationOrchestrator:
    """
    GEN 6.0 TITAN ORCHESTRATOR.
    Now optimizes KINEMATICS (Geometry) alongside DYNAMICS (Springs).
    """
    def __init__(self, project_root, cm_exe_path, study_name, storage_url, n_workers=1):
        self.project_root = project_root
        
        self.param_manager = ParameterManager(
            template_dir=os.path.join(project_root, "Data", "TestRun"), # Corrected CM Path
            work_dir=project_root
        )
        self.data_handler = ResultHandler(
            parquet_storage_path=os.path.join(project_root, "data", "parquet_store")
        )
        self.interface = CarMakerInterface(cm_exe_path, project_root)
        self.resources = ResourceManager(start_port=16660, max_licenses=n_workers)
        self.surrogate = SurrogateOracle()
        
        self.study_name = study_name
        self.storage_url = storage_url
        self.study = self._load_or_create_study()

    def _load_or_create_study(self):
        return optuna.create_study(
            study_name=self.study_name,
            storage=self.storage_url,
            direction="minimize",
            load_if_exists=True,
            sampler=optuna.samplers.TPESampler(seed=42, multivariate=True)
        )

    def _objective(self, trial):
        # --- 1. EXPANDED DESIGN SPACE ---
        params = {
            # DYNAMICS (The Tuning Knobs)
            "k_spring_f": trial.suggest_float("k_spring_f", 30000, 90000),
            "k_spring_r": trial.suggest_float("k_spring_r", 30000, 90000),
            "c_damp_f": trial.suggest_float("c_damp_f", 2000, 6000),
            "c_damp_r": trial.suggest_float("c_damp_r", 2000, 6000),
            
            # KINEMATICS (The Architecture - GEN 6.0 UPGRADE)
            # Modifying these physically moves the suspension points in 3D space.
            
            # Roll Center Height Modifier (Moving Upper Wishbone Z)
            # Baseline is approx 0.300m. We explore +/- 50mm.
            "HP_FL_Wishbone_Upper_Z": trial.suggest_float("HP_FL_Wishbone_Upper_Z", 0.250, 0.350),
            
            # Anti-Dive Geometry (Moving Front Lower Rear Point Z)
            # Lowering this increases Anti-Dive.
            "HP_FL_Wishbone_Lower_Rear_Z": trial.suggest_float("HP_FL_Wishbone_Lower_Rear_Z", 0.100, 0.160)
        }

        # --- 2. SURROGATE CHECK ---
        prediction, sigma, is_promising = self.surrogate.evaluate_trust(params)
        if not is_promising:
            trial.set_user_attr("source", "Surrogate_Pruned")
            return prediction[0]

        # --- 3. SIMULATION ---
        logger.info(f"🚀 Trial {trial.number}: Optimizing Geometry & Springs...")
        res = self._run_simulation_task(trial.number, params)

        # --- 4. REPORTING ---
        # Add data to surrogate (Gaussian Process)
        self.surrogate.add_observation(params, (res['cost'], res['stability_index']))
        self.surrogate.train()
        
        # Save KPIs
        for k, v in res.items():
            trial.set_user_attr(k, v)
            
        return res['cost']

    def _run_simulation_task(self, trial_id, params):
        run_id = f"Opt_Trial_{trial_id:04d}"
        
        with self.resources.lease(f"Worker_{trial_id}") as port:
            # 1. Inject Hardpoints (Geometry)
            # We assume your vehicle file is at 'Data/Vehicle/MyCar'
            # UPDATE THIS FILENAME TO MATCH YOUR CARMAKER PROJECT!
            vehicle_file = os.path.join(self.project_root, "Data", "Vehicle", "MyCar") 
            
            hardpoint_map = {
                "Hardpoint.FL.Wishbone.Upper.Z": params["HP_FL_Wishbone_Upper_Z"],
                "Hardpoint.FR.Wishbone.Upper.Z": params["HP_FL_Wishbone_Upper_Z"], # Symmetric
                "Hardpoint.FL.Wishbone.Lower.Rear.Z": params["HP_FL_Wishbone_Lower_Rear_Z"],
                "Hardpoint.FR.Wishbone.Lower.Rear.Z": params["HP_FL_Wishbone_Lower_Rear_Z"]
            }
            
            if os.path.exists(vehicle_file):
                self.param_manager.inject_hardpoints(vehicle_file, hardpoint_map)
            else:
                logger.warning(f"Vehicle file not found at {vehicle_file}. Geometry optimization skipped.")

            # 2. Inject Springs (TestRun)
            # Make sure 'Skidpad_Base' exists in your Data/TestRun folder!
            run_file = self.param_manager.create_run_configuration(run_id, params, "Skidpad_Base")
            
            # 3. Run Simulation
            result = self.interface.run_simulation(
                test_run_name=run_file, 
                tcp_port=port, 
                timeout_sec=120
            )
            
            if result['status'] == 'SUCCESS':
                erg_path = os.path.join(self.project_root, "SimOutput", f"{run_id}.erg")
                return self.data_handler.process_results(run_id, erg_path)
            else:
                return {"cost": 999.0, "stability_index": 0.0}

    def run(self, n_trials=50, n_jobs=1):
        with joblib.parallel_backend("loky", n_jobs=n_jobs):
            self.study.optimize(self._objective, n_trials=n_trials, n_jobs=n_jobs)
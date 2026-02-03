import optuna
import logging
import os
import numpy as np

from src.interface.carmaker_interface import CarMakerInterface
from src.core.parameter_manager import ParameterManager
from src.core.surrogate import SurrogateOracle
from src.core.resource_manager import ResourceManager

class Orchestrator:
    def __init__(self, study_name):
        self.study_name = study_name
        self.logger = logging.getLogger("Orchestrator")
        
        # Silence Optuna's default logging to keep terminal clean
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        
        self.resources = ResourceManager()
        self.storage_url = self.resources.get_db_path()
        self.cm_interface = CarMakerInterface()
        self.param_manager = ParameterManager(template_path="templates/FSE_AllWheelDrive")
        self.surrogate = SurrogateOracle(storage_path="data/suspension_knowledge.pkl")
        self.optimization_mode = "dynamics" 
        
        self.best_lap = float('inf')

    def set_mode(self, mode):
        if mode not in ["dynamics", "kinematics"]: raise ValueError("Invalid mode")
        self.optimization_mode = mode

    def optimize(self, n_trials=100):
        mode_study_name = f"{self.study_name}_{self.optimization_mode}"
        
        study = optuna.create_study(
            study_name=mode_study_name,
            storage=self.storage_url,
            direction="minimize",
            load_if_exists=True,
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5)
        )
        
        self.logger.info(f"📂 Output: {self.resources.get_campaign_path()}")
        
        # Expanded Table Header
        header = f"| {'TRIAL':^5} | {'STATUS':^10} | {'LAP TIME':^10} | {'SETUP NOTES':^50} |"
        self.logger.info("-" * len(header))
        self.logger.info(header)
        self.logger.info("-" * len(header))
        
        study.optimize(self._objective, n_trials=n_trials)
        
        self.logger.info("-" * len(header))
        self.logger.info("✅ Optimization Complete.")
        return study.best_params

    def _objective(self, trial):
        # 1. Suggest Params
        if self.optimization_mode == "dynamics":
            params = self._suggest_dynamics_params(trial)
            
            # --- LOGGING: Compact view of critical params ---
            kf = int(params['Spring_F'] / 1000)
            kr = int(params['Spring_R'] / 1000)
            abf = int(params['Stabilizer_F'] / 1000)
            abr = int(params['Stabilizer_R'] / 1000)
            # Average damping for quick reference
            damp_f = int((params['Damp_Bump_F'] + params['Damp_Reb_F']) / 2)
            
            note = f"K:{kf}/{kr}k ARB:{abf}/{abr}k DampF:~{damp_f}"
        else:
            params = self._suggest_kinematics_params(trial)
            note = "Geometry Hardpoint Update"

        # 2. Surrogate Pruning
        pred_cost, uncertainty = self.surrogate.predict(params)
        if pred_cost > 200.0 and uncertainty < 20.0:
            self._log_row(trial.number, "PRUNED", "N/A", f"AI Predicts Crash ({pred_cost:.0f})")
            raise optuna.TrialPruned()

        # 3. Build & Run
        trial_folder = self.resources.setup_trial_folder(trial.number)
        vehicle_file = os.path.join(trial_folder, "Vehicle_Setup.txt")
        
        success = self.param_manager.inject_parameters(vehicle_file, params)
        if not success: 
            self._log_row(trial.number, "BUILD ERR", "N/A", "File Write Failed")
            return 999.0

        result = self.cm_interface.run_test(vehicle_file, trial_folder, trial.number)
        
        # 4. Result Handling
        if result['status'] == 'Complete':
            lap_time = result['lap_time']
            cost = lap_time + result['cones_hit'] * 2.0
            
            # Check if Best
            status = "COMPLETE"
            if cost < self.best_lap:
                self.best_lap = cost
                status = "⭐ NEW BEST"
            
            self._log_row(trial.number, status, f"{cost:.3f}s", note)
            
            self.surrogate.update(params, cost)
            trial.set_user_attr("mass_penalty", params.get("Body.Mass", 230.0) - 230.0)
            return cost
        else:
            self._log_row(trial.number, "CRASH", "999.0s", "Sim Failed")
            self.surrogate.update(params, 999.0)
            return 999.0

    def _log_row(self, trial_num, status, time_str, note):
        """Prints a formatted table row"""
        RESET = "\033[0m"
        GREEN = "\033[92m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        
        color = RESET
        if "BEST" in status: color = GREEN
        elif "CRASH" in status: color = RED
        elif "PRUNED" in status: color = YELLOW
        
        msg = f"| {trial_num:^5} | {color}{status:^10}{RESET} | {time_str:^10} | {note:<50} |"
        self.logger.info(msg)

    def _suggest_dynamics_params(self, trial):
        """
        FULL VEHICLE DYNAMICS SEARCH SPACE
        """
        return {
            # --- SPRINGS (N/m) ---
            "Spring_F": trial.suggest_float("k_spring_f", 20000, 90000),
            "Spring_R": trial.suggest_float("k_spring_r", 20000, 90000),
            
            # --- DAMPERS FRONT (N/(m/s)) ---
            "Damp_Bump_F": trial.suggest_float("d_bump_f", 500, 5000),
            "Damp_Reb_F":  trial.suggest_float("d_reb_f", 1000, 8000),
            
            # --- DAMPERS REAR ---
            "Damp_Bump_R": trial.suggest_float("d_bump_r", 500, 5000),
            "Damp_Reb_R":  trial.suggest_float("d_reb_r", 1000, 8000),

            # --- ANTI-ROLL BARS (N/m) ---
            "Stabilizer_F": trial.suggest_float("arb_f", 0, 70000),
            "Stabilizer_R": trial.suggest_float("arb_r", 0, 70000),

            # --- STATIC ALIGNMENT (rad) ---
            # Camber: -3.5 deg to -0.5 deg
            "Camber_Static_F": trial.suggest_float("camber_f", -0.06, -0.008), 
            "Camber_Static_R": trial.suggest_float("camber_r", -0.04, -0.008),
            # Toe: -0.5 deg (out) to +0.5 deg (in)
            "Toe_Static_F": trial.suggest_float("toe_f", -0.008, 0.008),
            "Toe_Static_R": trial.suggest_float("toe_r", -0.008, 0.008),
        }

    def _suggest_kinematics_params(self, trial):
        return {
            "HP_FL_Wishbone_Upper_Z": trial.suggest_float("hp_flu_z", 250, 350),
            "HP_Rack_Z": trial.suggest_float("hp_rack_z", 100, 200),
        }
import optuna
import logging
import os
import numpy as np

from src.interface.carmaker_interface import CarMakerInterface
from src.core.parameter_manager import ParameterManager
from src.core.surrogate import SurrogateOracle
from src.core.resource_manager import ResourceManager
from src.core.physics_validator import PhysicsValidator  # <--- NEW
from src.core.delta_learner import DeltaLearner          # <--- NEW

class Orchestrator:
    def __init__(self, study_name):
        self.study_name = study_name
        self.logger = logging.getLogger("Orchestrator")
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        
        self.resources = ResourceManager()
        self.storage_url = self.resources.get_db_path()
        self.cm_interface = CarMakerInterface()
        self.param_manager = ParameterManager(template_path="templates/FSE_AllWheelDrive")
        self.surrogate = SurrogateOracle()
        
        # --- NEW MODULES ---
        self.validator = PhysicsValidator()
        self.delta_learner = DeltaLearner()
        
        self.optimization_mode = "dynamics" 
        self.best_lap = float('inf')
        self.TOTAL_TRACK_DIST = 75.0 

    def optimize(self, n_trials=100):
        study = optuna.create_study(
            study_name=f"{self.study_name}_{self.optimization_mode}",
            storage=self.storage_url,
            direction="minimize",
            load_if_exists=True,
            sampler=optuna.samplers.TPESampler(n_startup_trials=10)
        )
        
        self.logger.info(f"🚀 Starting Phase 3/4 Optimization (Physics Gated)")
        study.optimize(self._objective, n_trials=n_trials)
        return study.best_params

    def _objective(self, trial):
        # 1. Parameter Proposal & PHYSICS GATE
        # We loop until we find a physically valid set (max 10 tries)
        # to avoid wasting the 'trial' object on a NaN result
        for _ in range(10):
            params = self._suggest_dynamics_params(trial)
            is_valid, reason = self.validator.check_viability(params)
            
            if is_valid:
                break
            else:
                # Tell Optuna this area is bad (Pruning)
                # But since we haven't run sim, we just loop to find better params
                # In strict Optuna, we might return a Fail value, but looping is cleaner here.
                pass
        
        if not is_valid:
            self._log_row(trial.number, "PRUNED", "N/A", reason)
            return 999.0 # Hard penalty for physics violation

        # 2. Risk Assessment (cBO)
        risk_score = self.surrogate.predict_score(params)
        
        # 3. Execution
        trial_folder = self.resources.setup_trial_folder(trial.number)
        vehicle_file = os.path.join(trial_folder, "Vehicle_Setup.txt")
        
        if not self.param_manager.inject_parameters(vehicle_file, params):
            return 999.0

        result = self.cm_interface.run_test(vehicle_file, trial_folder, trial.number)
        
        # 4. Result Handling (Soft Penalties + Reality Gap)
        lap_time = result['lap_time']
        dist = result.get('distance', 0)
        is_crash = False
        
        status = "COMPLETE"
        
        if dist < (self.TOTAL_TRACK_DIST * 0.95) or lap_time > 100:
            is_crash = True
            status = "CRASH"
            if dist > 5.0:
                pace = lap_time / dist
                projected_time = pace * self.TOTAL_TRACK_DIST
                final_cost = projected_time * 1.10 
            else:
                final_cost = 300.0 
        else:
            final_cost = lap_time

        # --- APPLY SIM-TO-REAL CORRECTION ---
        correction = self.delta_learner.get_correction(params)
        final_cost += correction
        # ------------------------------------

        self.surrogate.update(params, final_cost, is_crash)
        
        if final_cost < self.best_lap:
            self.best_lap = final_cost
            status = "⭐ NEW BEST"

        self._log_row(trial.number, status, f"{final_cost:.3f}s", f"Dist: {dist:.1f}m | {reason}")
        return final_cost

    def _log_row(self, trial_num, status, time_str, note):
        RESET = "\033[0m"
        color = "\033[92m" if "BEST" in status else ("\033[91m" if "CRASH" in status else ("\033[93m" if "PRUNED" in status else RESET))
        self.logger.info(f"| {trial_num:^5} | {color}{status:^10}{RESET} | {time_str:^10} | {note:<30} |")

    def _suggest_dynamics_params(self, trial):
        # Refined ranges based on Document recommendations (avoiding extreme stiffness)
        return {
            "Spring_F": trial.suggest_float("k_spring_f", 20000, 75000), # N/m
            "Spring_R": trial.suggest_float("k_spring_r", 20000, 75000),
            "Damp_Bump_F": trial.suggest_float("d_bump_f", 500, 4000),   # Ns/m
            "Damp_Reb_F":  trial.suggest_float("d_reb_f", 1500, 6000),
            "Damp_Bump_R": trial.suggest_float("d_bump_r", 500, 4000),
            "Damp_Reb_R":  trial.suggest_float("d_reb_r", 1500, 6000),
            "Stabilizer_F": trial.suggest_float("arb_f", 0, 50000),      # Nm/rad
            "Stabilizer_R": trial.suggest_float("arb_r", 0, 50000),
            "Camber_Static_F": trial.suggest_float("camber_f", -0.05, -0.01), 
            "Camber_Static_R": trial.suggest_float("camber_r", -0.03, -0.005),
            "Toe_Static_F": trial.suggest_float("toe_f", -0.005, 0.005),
            "Toe_Static_R": trial.suggest_float("toe_r", -0.002, 0.005),
        }
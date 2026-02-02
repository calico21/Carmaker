import optuna
import logging
import time
import numpy as np
from src.interface.carmaker_interface import CarMakerInterface
from src.core.parameter_manager import ParameterManager
from src.core.surrogate import SurrogateOracle
from src.database.data_handler import DataHandler

class Orchestrator:
    """
    The 'Brain' of the operation. 
    Now splits optimization into distinct phases: 'kinematics' or 'dynamics'.
    """
    
    def __init__(self, study_name, storage_url="sqlite:///db.sqlite3"):
        self.study_name = study_name
        self.storage_url = storage_url
        self.logger = logging.getLogger("Orchestrator")
        
        # Sub-systems
        self.cm_interface = CarMakerInterface()
        self.param_manager = ParameterManager(template_path="templates/TestRuns/Master_Skidpad")
        self.surrogate = SurrogateOracle()
        self.db = DataHandler()
        
        # State
        self.optimization_mode = "dynamics" # Default
        self.baseline_params = {} # To store fixed params when optimizing the other mode

    def set_mode(self, mode):
        if mode not in ["dynamics", "kinematics"]:
            raise ValueError("Mode must be 'dynamics' or 'kinematics'")
        self.optimization_mode = mode
        self.logger.info(f"Orchestrator switched to {mode.upper()} mode.")

    def optimize(self, n_trials=100):
        """
        Main loop. Creates or loads a study and optimizes for the current mode.
        """
        # Unique study name for each mode to prevent cross-contamination
        mode_study_name = f"{self.study_name}_{self.optimization_mode}"
        
        study = optuna.create_study(
            study_name=mode_study_name,
            storage=self.storage_url,
            direction="minimize",
            load_if_exists=True,
            # Pruner helps stop bad runs early (e.g., if lap time > 150s at 50% dist)
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=10)
        )
        
        self.logger.info(f"Starting optimization: {mode_study_name} | Trials: {n_trials}")
        
        study.optimize(self._objective, n_trials=n_trials)
        
        self.logger.info("Optimization complete.")
        return study.best_params

    def _objective(self, trial):
        """
        The objective function evaluated by Optuna.
        """
        # 1. Suggest Parameters based on Mode
        if self.optimization_mode == "dynamics":
            params = self._suggest_dynamics_params(trial)
            # Inject fixed kinematics (if any)
            # params.update(self.fixed_kinematics) 
        else:
            params = self._suggest_kinematics_params(trial)
            # Inject fixed dynamics
            # params.update(self.fixed_dynamics)

        # 2. Surrogate Check (Fail Fast)
        # Ask the Gaussian Process: "Is this config likely to crash?"
        predicted_cost, uncertainty = self.surrogate.predict(params)
        
        # If we are certain it's a disaster, skip the expensive simulation
        if predicted_cost > 200.0 and uncertainty < 10.0:
            self.logger.info(f"Trial {trial.number} pruned by Surrogate (Pred: {predicted_cost:.2f})")
            raise optuna.TrialPruned()

        # 3. Generate Vehicle File
        # We use a temp file for every trial to avoid race conditions
        vehicle_file = f"Products/Vehicle_Trial_{trial.number}"
        success = self.param_manager.inject_parameters(vehicle_file, params)
        
        if not success:
            return 999.0 # Fail penalty

        # 4. Run Simulation (The Expensive Part)
        # Note: We pass the trial to allow the simulation interface to report intermediate steps for pruning
        sim_result = self.cm_interface.run_test(vehicle_file, trial_id=trial.number)
        
        # 5. Calculate Cost
        if sim_result['status'] == 'Complete':
            real_cost = sim_result['lap_time'] + sim_result['cones_hit'] * 2.0
            
            # Train the Surrogate for next time
            self.surrogate.update(params, real_cost)
            
            return real_cost
        else:
            # Soft failure (crashed but maybe useful data?)
            return 999.0

    def _suggest_dynamics_params(self, trial):
        """
        Search Space: Springs, Dampers, ARBs.
        Strategy: Black Box (Optuna) is perfect for this.
        """
        return {
            "Spring_F": trial.suggest_float("k_spring_f", 20000, 80000),
            "Spring_R": trial.suggest_float("k_spring_r", 20000, 80000),
            "Damp_Bump_F": trial.suggest_float("d_bump_f", 1000, 5000),
            "Damp_Reb_F": trial.suggest_float("d_reb_f", 2000, 8000),
            "ARB_F": trial.suggest_float("k_arb_f", 100, 2000),
            # Add Balance constraints if needed (e.g. Front always stiffer than Rear)
        }

    def _suggest_kinematics_params(self, trial):
        """
        Search Space: Hardpoints.
        Strategy: This uses the Mass Penalty logic we added in ParameterManager.
        Note: Ideally, this should be done in CasADi (White Box), but this
        allows 'Sim-Verified' geometry tuning if CasADi is unavailable.
        """
        return {
            # Moving the Front Upper Wishbone Z-coordinate (Roll Center adjustment)
            "HP_FL_Wishbone_Upper_Z": trial.suggest_float("hp_flu_z", 250, 350),
            # Moving Steering Rack (Bump Steer adjustment)
            "HP_Rack_Z": trial.suggest_float("hp_rack_z", 100, 200),
            # Note: We do NOT tune springs here. 
            # We assume the car has 'standard' springs during this geometric pass.
        }
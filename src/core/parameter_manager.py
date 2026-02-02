import os
import logging
import numpy as np

class ParameterManager:
    """
    Handles the modification of CarMaker text files (Vehicle or TestRun).
    
    CRITICAL FEATURE: 'Mass Penalty'
    - Prevents unrealistic geometry optimization.
    - If hardpoints move significantly, it adds mass (simulating heavier brackets).
    - Updates Inertia (Ixx, Iyy, Izz) to match the new mass.
    """

    def __init__(self, template_path):
        self.template_path = template_path
        self.logger = logging.getLogger("ParameterManager")
        
        # --- PHYSICS CONSTANTS (Calibrate these to your CAD model) ---
        self.NOMINAL_MASS = 230.0  # kg (Chassis only, no driver)
        self.NOMINAL_IXX = 120.0   # kg*m^2
        self.NOMINAL_IYY = 350.0   # kg*m^2
        self.NOMINAL_IZZ = 400.0   # kg*m^2
        
        # Penalty Factors
        # 0.5 kg added for every 1.0 unit of "Geometric Complexity"
        self.MASS_PENALTY_FACTOR = 0.5  
        self.INERTIA_SCALING = 1.05     # Scaling factor for added material

    def inject_parameters(self, output_path, parameters):
        """
        Reads the template, replaces values with optimization parameters, 
        calculates mass penalties, and writes the new file to 'output_path'.
        
        Args:
            output_path (str): Where to save the new vehicle file.
            parameters (dict): The parameters from Optuna/Orchestrator.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if not os.path.exists(self.template_path):
                self.logger.error(f"Template not found: {self.template_path}")
                return False

            with open(self.template_path, 'r') as f:
                lines = f.readlines()

            # 1. Calculate Mass & Inertia Updates based on Geometry changes
            # This ensures the physics engine sees the penalty
            mass_updates = self._calculate_mass_penalty(parameters)
            
            # Merge physics updates into the parameter list
            # Priority: mass_updates overrides 'parameters' if there's a conflict 
            # (though normally they target different keys)
            full_parameters = {**parameters, **mass_updates}

            new_lines = []
            keys_handled = set()

            # 2. Line-by-Line Replacement
            for line in lines:
                line_handled = False
                stripped = line.strip()
                
                # Check if this line corresponds to any parameter we want to change
                for key, val in full_parameters.items():
                    # CarMaker format is usually "Key = Value"
                    # We check if line starts with Key AND is followed by a delimiter
                    if stripped.startswith(key) and (len(stripped) > len(key)) and (stripped[len(key)] in [' ', '=', '\t']):
                        new_lines.append(f"{key} = {val}\n")
                        keys_handled.add(key)
                        line_handled = True
                        break
                
                if not line_handled:
                    new_lines.append(line)

            # 3. Append missing keys 
            # (e.g., if Body.Mass wasn't in the template explicitly, add it now)
            for key, val in full_parameters.items():
                if key not in keys_handled:
                    new_lines.append(f"{key} = {val}\n")

            # 4. Write Output
            with open(output_path, 'w') as f:
                f.writelines(new_lines)
            
            return True

        except Exception as e:
            self.logger.error(f"Failed to inject parameters: {e}")
            return False

    def _calculate_mass_penalty(self, parameters):
        """
        Calculates new Mass and Inertia values based on hardpoint deviations.
        """
        # Filter for geometry parameters (keywords typically used in CarMaker)
        geo_keywords = ["Wishbone", "Tierod", "Rack", "Pushrod"]
        geo_changes = [val for key, val in parameters.items() if any(k in key for k in geo_keywords)]
        
        # If we are only tuning Springs/Dampers (Dynamics Mode), no penalty needed.
        if not geo_changes:
            return {}

        # Heuristic: Calculate standard deviation of changes as a proxy for "complexity"
        # In a real app, you would compare vs self.nominal_hardpoints to get absolute distance.
        # Here, we assume higher variance in coordinates = more complex bracketry.
        complexity_score = np.std(geo_changes) if len(geo_changes) > 1 else 0
        
        # Threshold: Only penalize if there is actual movement (> 1mm variance)
        if complexity_score < 1.0:
            return {}

        added_mass = complexity_score * self.MASS_PENALTY_FACTOR
        new_mass = self.NOMINAL_MASS + added_mass
        
        # Scale Inertia: I = I_0 * (m/m_0)
        # We assume the mass is added structurally, scaling inertia linearly.
        mass_ratio = new_mass / self.NOMINAL_MASS
        
        new_ixx = self.NOMINAL_IXX * mass_ratio
        new_iyy = self.NOMINAL_IYY * mass_ratio
        # Izz (Yaw Inertia) often grows faster than linear when adding width/length
        new_izz = self.NOMINAL_IZZ * mass_ratio * self.INERTIA_SCALING

        self.logger.info(f"⚖️ Geometry Penalty: +{added_mass:.2f}kg | New Izz: {new_izz:.1f}")

        # Return dict for injection
        return {
            "Body.Mass": round(new_mass, 3),
            "Body.Ixx": round(new_ixx, 3),
            "Body.Iyy": round(new_iyy, 3),
            "Body.Izz": round(new_izz, 3)
        }
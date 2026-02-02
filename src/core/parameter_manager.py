import os
import logging
import shutil
import numpy as np

class ParameterManager:
    """
    Handles the modification of CarMaker text files (Vehicle or TestRun)
    to inject optimization parameters (Hardpoints, Springs, Dampers).
    """

    def __init__(self, template_path):
        self.template_path = template_path
        self.logger = logging.getLogger("ParameterManager")
        
        # Nominal mass values (Reference from your CAD model)
        # You should update these to match your specific car's baseline
        self.NOMINAL_MASS = 230.0  # kg (Chassis only)
        self.NOMINAL_IXX = 120.0
        self.NOMINAL_IYY = 350.0
        self.NOMINAL_IZZ = 400.0
        
        # Penalty Factors
        self.MASS_PENALTY_FACTOR = 0.5  # kg per mm of hardpoint deviation (heavier brackets)
        self.INERTIA_SCALING = 1.05     # Scaling factor for added material distribution

    def inject_parameters(self, output_path, parameters):
        """
        Reads the template, replaces values with 'parameters' dict, 
        calculates mass penalties, and writes the new file.
        """
        try:
            with open(self.template_path, 'r') as f:
                lines = f.readlines()

            # 1. Calculate Mass & Inertia Updates based on Geometry changes
            mass_updates = self._calculate_mass_penalty(parameters)
            
            # Merge physics updates into the parameter list so they get written to the file
            # Priority: parameters > mass_updates (though usually they don't overlap)
            full_parameters = {**mass_updates, **parameters}

            new_lines = []
            keys_handled = set()

            # 2. Line-by-Line Replacement
            for line in lines:
                line_handled = False
                stripped = line.strip()
                
                # Check if this line corresponds to any parameter we want to change
                for key, val in full_parameters.items():
                    # Carmaker format: "Key = Value"
                    # We check if the line STARTS with the key (plus space or =)
                    if stripped.startswith(key) and (stripped[len(key)] in [' ', '=']):
                        new_lines.append(f"{key} = {val}\n")
                        keys_handled.add(key)
                        line_handled = True
                        break
                
                if not line_handled:
                    new_lines.append(line)

            # 3. Append missing keys (e.g. if Body.Mass wasn't in the template)
            for key, val in full_parameters.items():
                if key not in keys_handled:
                    new_lines.append(f"{key} = {val}\n")

            # 4. Write Output
            with open(output_path, 'w') as f:
                f.writelines(new_lines)
            
            self.logger.info(f"Generated vehicle file at {output_path} with {len(full_parameters)} updates.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to inject parameters: {e}")
            return False

    def _calculate_mass_penalty(self, parameters):
        """
        Calculates new Mass and Inertia values based on how aggressively 
        the optimizer is moving the hardpoints.
        """
        # Filter for geometry parameters (Hardpoints)
        # Assuming your hardpoint keys start with "HP_" or contain ".Z", ".x", etc.
        geo_changes = [val for key, val in parameters.items() if "Wishbone" in key or "Tierod" in key]
        
        if not geo_changes:
            return {}

        # Heuristic: Calculate deviation from 'standard' positions
        # In a real scenario, you'd compare against self.nominal_hardpoints
        # Here we assume 'parameters' contains absolute coordinates. 
        # We estimate "complexity" by the variance or magnitude of changes.
        
        # Simple Model: 
        # If the optimizer pushes points very far, we assume heavier brackets/tubes.
        # This prevents "Teleporting Hardpoints".
        
        # Calculate a scalar "Complexity Score" (simplified for this fix)
        # We use standard deviation as a proxy for "weird geometry"
        complexity_score = np.std(geo_changes) if len(geo_changes) > 1 else 0
        
        added_mass = complexity_score * self.MASS_PENALTY_FACTOR
        
        new_mass = self.NOMINAL_MASS + added_mass
        
        # Scale Inertia: I = I_0 * (m/m_0)
        # We assume mass is added at the perimeter, increasing inertia linearly or quadratically
        mass_ratio = new_mass / self.NOMINAL_MASS
        
        new_ixx = self.NOMINAL_IXX * mass_ratio
        new_iyy = self.NOMINAL_IYY * mass_ratio
        new_izz = self.NOMINAL_IZZ * mass_ratio * self.INERTIA_SCALING

        return {
            "Body.Mass": round(new_mass, 3),
            "Body.Ixx": round(new_ixx, 3),
            "Body.Iyy": round(new_iyy, 3),
            "Body.Izz": round(new_izz, 3)
        }
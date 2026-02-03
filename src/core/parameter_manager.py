import os
import logging
import numpy as np

class ParameterManager:
    """
    Handles the modification of CarMaker text files (Vehicle or TestRun).
    CORRECTED for FSE_AllWheelDrive format.
    """

    def __init__(self, template_path):
        self.template_path = template_path
        self.logger = logging.getLogger("ParameterManager")
        
        self.NOMINAL_MASS = 230.0
        self.NOMINAL_IXX = 120.0
        self.NOMINAL_IYY = 350.0
        self.NOMINAL_IZZ = 400.0
        self.MASS_PENALTY_FACTOR = 0.5  
        self.INERTIA_SCALING = 1.05

        # --- CORRECTED CARMAKER KEY MAPPING ---
        # Based on actual FSE_AllWheelDrive file format
        self.PARAM_MAP = {
            # Springs - Direct value assignment
            "Spring_F": "SuspF.Spring",
            "Spring_R": "SuspR.Spring",
            
            # Anti-Roll Bars - Direct value assignment
            "Stabilizer_F": "SuspF.Stabi",
            "Stabilizer_R": "SuspR.Stabi",
            
            # Dampers - These use lookup tables, we'll use Amplify factors
            "Damp_Bump_F": "SuspF.Damp_Push.Amplify",
            "Damp_Reb_F": "SuspF.Damp_Pull.Amplify",
            "Damp_Bump_R": "SuspR.Damp_Push.Amplify",
            "Damp_Reb_R": "SuspR.Damp_Pull.Amplify",
            
            # Note: Camber/Toe are NOT simple parameters in the vehicle file
            # They're part of the kinematic .skc file, so we skip them for now
        }

    def inject_parameters(self, output_path, parameters):
        """
        Inject parameters into the vehicle file.
        Only modifies parameters that exist in PARAM_MAP.
        """
        try:
            if not os.path.exists(self.template_path):
                self.logger.error(f"Template not found: {self.template_path}")
                return False

            with open(self.template_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Calculate any mass penalties
            mass_updates = self._calculate_mass_penalty(parameters)
            raw_params = {**parameters, **mass_updates}
            
            # Filter to only valid parameters
            valid_params = {}
            for k, v in raw_params.items():
                if k in self.PARAM_MAP:
                    # Map to CarMaker key
                    cm_key = self.PARAM_MAP[k]
                    valid_params[cm_key] = v
                elif k in ["Body.Mass", "Body.Ixx", "Body.Iyy", "Body.Izz"]:
                    # Direct body parameters
                    valid_params[k] = v

            self.logger.info(f"   -> Injecting {len(valid_params)} parameters")
            
            new_lines = []
            keys_handled = set()

            # Process each line
            for line in lines:
                line_handled = False
                stripped = line.strip()
                
                # Check if this line matches any parameter we want to change
                for key, val in valid_params.items():
                    # Match "Key = Value" or "Key = ..." pattern
                    if stripped.startswith(key):
                        # Check next character is space, =, or tab
                        if len(stripped) > len(key) and stripped[len(key)] in [' ', '=', '\t']:
                            # Special handling for damper amplify (has $ variable)
                            if "Amplify" in key:
                                # Convert raw damping value to amplify factor
                                # Base values from template: ~150-500 N/(m/s)
                                # User values: 500-8000 N/(m/s)
                                # Amplify = user_value / base_value
                                base_value = 1.0  # We'll scale relative to current Amplify
                                
                                # Extract current amplify if it exists
                                if "=" in stripped:
                                    parts = stripped.split("=")
                                    if len(parts) > 1:
                                        try:
                                            current = parts[1].strip().replace("$amp=", "")
                                            base_value = float(current)
                                        except:
                                            base_value = 1.0
                                
                                # Calculate new amplify factor
                                # Assuming base damping ~2000 N/(m/s)
                                new_amplify = val / 2000.0
                                new_lines.append(f"{key} = {new_amplify:.3f}\n")
                            else:
                                # Simple value replacement
                                new_lines.append(f"{key} = {val}\n")
                            
                            keys_handled.add(key)
                            line_handled = True
                            break
                
                if not line_handled:
                    new_lines.append(line)

            # Log what was changed
            if keys_handled:
                self.logger.info(f"   -> Modified keys: {', '.join(sorted(keys_handled))}")
            else:
                self.logger.warning(f"   -> No parameters were modified!")

            # Write output
            with open(output_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            return True

        except Exception as e:
            self.logger.error(f"Failed to inject parameters: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _calculate_mass_penalty(self, parameters):
        """Calculate mass penalty for geometry changes"""
        geo_keywords = ["Wishbone", "Tierod", "Rack", "Pushrod"]
        geo_changes = [val for key, val in parameters.items() if any(k in key for k in geo_keywords)]
        
        if not geo_changes:
            return {}

        complexity_score = np.std(geo_changes) if len(geo_changes) > 1 else 0
        if complexity_score < 1.0: 
            return {}

        added_mass = complexity_score * self.MASS_PENALTY_FACTOR
        new_mass = self.NOMINAL_MASS + added_mass
        mass_ratio = new_mass / self.NOMINAL_MASS
        
        return {
            "Body.Mass": round(new_mass, 3),
            "Body.Ixx": round(self.NOMINAL_IXX * mass_ratio, 3),
            "Body.Iyy": round(self.NOMINAL_IYY * mass_ratio, 3),
            "Body.Izz": round(self.NOMINAL_IZZ * mass_ratio * self.INERTIA_SCALING, 3)
        }
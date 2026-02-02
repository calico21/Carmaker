import os
import logging
import numpy as np

class ParameterManager:
    """
    Handles the modification of CarMaker text files (Vehicle or TestRun).
    Includes automatic key mapping for standard CarMaker datasets.
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

        # --- CARMAKER KEY MAPPING ---
        # Maps "Python Friendly Names" -> "Official CarMaker Infofile Keys"
        self.PARAM_MAP = {
            # Springs
            "Spring_F": "Susp.Spring.F.stiff",
            "Spring_R": "Susp.Spring.R.stiff",
            # Dampers (Assuming linear coeff 'Cmp'/'Reb' or Scaling Factor 'Fac')
            # Adjust these keys if you use a specific Non-Linear Map
            "Damp_Bump_F": "Susp.Damp.F.Cmp", 
            "Damp_Reb_F":  "Susp.Damp.F.Reb",
            "Damp_Bump_R": "Susp.Damp.R.Cmp",
            "Damp_Reb_R":  "Susp.Damp.R.Reb",
            # Anti-Roll Bars
            "Stabilizer_F": "Susp.Stabi.F.stiff",
            "Stabilizer_R": "Susp.Stabi.R.stiff",
            # Alignment (Kinematics)
            "Camber_Static_F": "Susp.Kin.F.Camber",
            "Camber_Static_R": "Susp.Kin.R.Camber",
            "Toe_Static_F": "Susp.Kin.F.Toe",
            "Toe_Static_R": "Susp.Kin.R.Toe"
        }

    def inject_parameters(self, output_path, parameters):
        try:
            if not os.path.exists(self.template_path):
                self.logger.error(f"Template not found: {self.template_path}")
                return False

            with open(self.template_path, 'r') as f:
                lines = f.readlines()

            # 1. Physics Calcs (Mass Penalty)
            mass_updates = self._calculate_mass_penalty(parameters)
            raw_params = {**parameters, **mass_updates}
            
            # 2. Translate Keys (Python Name -> CarMaker Name)
            # If the user's template ALREADY uses 'Spring_F', we keep it.
            # If not, we try the mapped key 'Susp.Spring.F.stiff'.
            full_parameters = {}
            for k, v in raw_params.items():
                # Add the original key
                full_parameters[k] = v
                # Add the mapped key if it exists
                if k in self.PARAM_MAP:
                    full_parameters[self.PARAM_MAP[k]] = v

            new_lines = []
            keys_handled = set()

            # 3. Line-by-Line Replacement
            for line in lines:
                line_handled = False
                stripped = line.strip()
                
                for key, val in full_parameters.items():
                    # Check for "Key = Value" match
                    if stripped.startswith(key) and (len(stripped) > len(key)) and (stripped[len(key)] in [' ', '=', '\t']):
                        new_lines.append(f"{key} = {val}\n")
                        keys_handled.add(key)
                        # Mark BOTH the alias and the official key as handled
                        line_handled = True
                        break
                
                if not line_handled:
                    new_lines.append(line)

            # 4. Append missing keys 
            # (Only append the Official Key if mapped, otherwise the Raw Key)
            for k, v in raw_params.items():
                # Determine which key to check/write
                target_key = self.PARAM_MAP.get(k, k)
                
                # Check if EITHER version was handled
                if (k not in keys_handled) and (target_key not in keys_handled):
                    new_lines.append(f"{target_key} = {v}\n")

            with open(output_path, 'w') as f:
                f.writelines(new_lines)
            
            return True

        except Exception as e:
            self.logger.error(f"Failed to inject parameters: {e}")
            return False

    def _calculate_mass_penalty(self, parameters):
        # ... (Same as before) ...
        geo_keywords = ["Wishbone", "Tierod", "Rack", "Pushrod"]
        geo_changes = [val for key, val in parameters.items() if any(k in key for k in geo_keywords)]
        
        if not geo_changes:
            return {}

        complexity_score = np.std(geo_changes) if len(geo_changes) > 1 else 0
        if complexity_score < 1.0: return {}

        added_mass = complexity_score * self.MASS_PENALTY_FACTOR
        new_mass = self.NOMINAL_MASS + added_mass
        mass_ratio = new_mass / self.NOMINAL_MASS
        
        return {
            "Body.Mass": round(new_mass, 3),
            "Body.Ixx": round(self.NOMINAL_IXX * mass_ratio, 3),
            "Body.Iyy": round(self.NOMINAL_IYY * mass_ratio, 3),
            "Body.Izz": round(self.NOMINAL_IZZ * mass_ratio * self.INERTIA_SCALING, 3)
        }
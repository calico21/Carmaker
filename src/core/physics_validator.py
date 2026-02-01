import numpy as np

class WhiteBoxValidator:
    """
    The 'Sanity Check'. 
    Compares Complex Multibody Simulation (CarMaker) against 
    First-Principles Physics (Bicycle Model).
    
    If they disagree, the design is suspect.
    """
    def __init__(self, wheelbase=1.53, track_width=1.2, mass_base=250):
        self.L = wheelbase
        self.W = track_width
        self.m_base = mass_base
        self.g = 9.81

    def validate_steady_state(self, params: dict, kpis: dict):
        """
        Checks if the Understeer Gradient calculated from Sim 
        matches the Theoretical Understeer Gradient (F=ma).
        """
        # 1. Extract Design Parameters
        k_f = params.get('k_spring_f', 30000)
        k_r = params.get('k_spring_r', 30000)
        mass = self.m_base * params.get('mass_scale', 1.0)
        
        # 2. Theoretical Load Transfer Distribution (simplified)
        # Assuming roll stiffness is proportional to spring rate (ignoring ARBs for simplicity)
        LLTD = k_f / (k_f + k_r)
        
        # 3. Theoretical Understeer (Simplified Bundorf Analysis)
        # Higher Front Stiffness -> Higher LLTD -> More Understeer
        # This is a 'Trend Check'. 
        theoretical_trend = "Understeer" if LLTD > 0.55 else "Oversteer"
        
        # 4. Simulation Reality
        sim_ug = kpis.get('understeer_grad', 0.0)
        sim_behavior = "Understeer" if sim_ug > 0 else "Oversteer"
        
        # 5. The Judge's Check
        is_plausible = (theoretical_trend == sim_behavior)
        
        return {
            "Physics_Check": "PASS" if is_plausible else "WARN",
            "Theoretical_LLTD": LLTD,
            "Sim_Understeer_Grad": sim_ug,
            "Explanation": f"Sim shows {sim_behavior} ({sim_ug:.2f} deg/g), Physics predicts {theoretical_trend} (LLTD {LLTD:.2f})."
        }

    def check_grip_limit(self, lap_time_s, track_length_m=269.0):
        """
        Checks if the Lap Time implies impossible friction.
        """
        avg_speed = track_length_m / lap_time_s # m/s
        
        # Skidpad (R=9.125m) Max Speed Estimate: V = sqrt(mu * g * R)
        # Assuming mu=1.6 (FSAE Softs)
        max_theoretical_v = np.sqrt(1.6 * 9.81 * 9.125) # ~11.9 m/s
        
        # If we are significantly faster than theory, the Sim is broken (e.g. hitting cones adds grip?)
        if avg_speed > max_theoretical_v * 1.1: # 10% buffer
            return "FAIL: Supernatural Grip"
        return "PASS: Physically Possible"
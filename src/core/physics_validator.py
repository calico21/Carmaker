import numpy as np
import logging

class PhysicsValidator:
    """
    PHASE 3: PRE-SIMULATION PHYSICS GATEKEEPER
    Filters out 'Black Hole' configurations that are physically unstable 
    before wasting simulation time.
    """
    def __init__(self):
        self.logger = logging.getLogger("Physics_Validator")
        
        # --- CONSTANTS FOR FS CAR (AMZ/Delft Benchmarks) ---
        self.M_CAR_SPRUNG = 230.0  # kg (Total Sprung Mass)
        self.M_DRIVER = 75.0       # kg
        self.WD_F = 0.48           # Weight Distribution Front (48%)
        
        # Per Corner Sprung Mass (Approximate)
        self.m_s_f = ((self.M_CAR_SPRUNG + self.M_DRIVER) * self.WD_F) / 2.0
        self.m_s_r = ((self.M_CAR_SPRUNG + self.M_DRIVER) * (1 - self.WD_F)) / 2.0
        
        # Limits [Cite: Document Section 4.2]
        self.MIN_FREQ_HZ = 1.5
        self.MAX_FREQ_HZ = 4.5
        self.MAX_STATIC_SAG_MM = 25.0 # Max compression under gravity
        self.MIN_STATIC_SAG_MM = 5.0

    def check_viability(self, params: dict) -> tuple[bool, str]:
        """
        Returns: (is_valid, reason)
        """
        # 1. Calculate Ride Frequencies (Hz)
        # f = (1/2pi) * sqrt(k / m)
        # Note: We assume Motion Ratio (MR) ~ 1.0 for simplicity, 
        # or that 'k_spring' is Wheel Rate. If k is Spring Rate, k_wheel = k_spring * MR^2
        mr_front = 1.0 # Update if Bellcrank exists
        mr_rear = 1.0
        
        k_f = params.get("Spring_F", 0) * (mr_front**2)
        k_r = params.get("Spring_R", 0) * (mr_rear**2)
        
        freq_f = (1 / (2 * np.pi)) * np.sqrt(k_f / self.m_s_f)
        freq_r = (1 / (2 * np.pi)) * np.sqrt(k_r / self.m_s_r)
        
        # CHECK 1: Frequency Range (Comfort vs Grip window)
        if not (self.MIN_FREQ_HZ <= freq_f <= self.MAX_FREQ_HZ):
            return False, f"Front Freq {freq_f:.2f}Hz out of bounds"
            
        if not (self.MIN_FREQ_HZ <= freq_r <= self.MAX_FREQ_HZ):
            return False, f"Rear Freq {freq_r:.2f}Hz out of bounds"

        # CHECK 2: Flat Ride / Pitch Sensitivity
        # Usually Rear Freq > Front Freq is preferred for flat ride,
        # but in Aero cars (FS), stiff front is common for platform control.
        # We just check they aren't wildly mismatched.
        ratio = freq_f / freq_r
        if ratio > 1.5 or ratio < 0.7:
             return False, f"Freq Imbalance F/R ratio: {ratio:.2f}"

        # CHECK 3: Static Sag (Gravity Drop)
        # Sag = F / k = (m * g) / k
        sag_f = (self.m_s_f * 9.81) / k_f * 1000 # mm
        sag_r = (self.m_s_r * 9.81) / k_r * 1000 # mm
        
        if sag_f > self.MAX_STATIC_SAG_MM or sag_f < self.MIN_STATIC_SAG_MM:
            return False, f"Front Static Sag {sag_f:.1f}mm invalid"
            
        if sag_r > self.MAX_STATIC_SAG_MM or sag_r < self.MIN_STATIC_SAG_MM:
            return False, f"Rear Static Sag {sag_r:.1f}mm invalid"

        return True, "Valid"
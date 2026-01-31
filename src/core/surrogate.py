import numpy as np
from sklearn.ensemble import RandomForestRegressor
import logging

logger = logging.getLogger(__name__)

class SurrogateOracle:
    """
    An AI Assistant that learns the physics of the car.
    It predicts TWO values: [Lap Time, Max Roll] based on input parameters.
    """
    def __init__(self):
        # RandomForest supports Multi-Output regression naturally (predicting 2 values at once)
        self.model = RandomForestRegressor(n_estimators=100, n_jobs=-1, random_state=42)
        self.is_trained = False
        self.X_history = []  # Input: [SpringF, SpringR, DampF, DampR, Mass]
        self.y_history = []  # Output: [LapTime, MaxRoll]
        self.train_frequency = 10 # Retrain every 10 new real simulations

    def add_observation(self, params: dict, results: tuple):
        """Feed the AI new data after a real simulation."""
        # Convert dict {'k_spring': 50000...} to list [50000, ...]
        features = list(params.values())
        
        # results is (LapTime, MaxRoll)
        if results[0] < 900: # Only learn from VALID runs (ignore crashes/999s)
            self.X_history.append(features)
            self.y_history.append(list(results))

    def train(self):
        """Teach the AI based on history."""
        # We need at least 20 valid runs to start guessing
        if len(self.X_history) < 20: 
            return

        X = np.array(self.X_history)
        y = np.array(self.y_history)
        
        try:
            self.model.fit(X, y)
            self.is_trained = True
            logger.info(f"🧠 Surrogate AI Retrained on {len(X)} samples.")
        except Exception as e:
            logger.warning(f"Surrogate training failed: {e}")

    def predict(self, params: dict):
        """Ask the AI: 'How fast and stable would this be?'"""
        if not self.is_trained:
            return None 
        
        features = np.array([list(params.values())])
        # Returns [[LapTime, MaxRoll]] -> convert to tuple
        prediction = self.model.predict(features)[0]
        return tuple(prediction)
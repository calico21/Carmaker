import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
import logging

logger = logging.getLogger(__name__)

class SurrogateOracle:
    """
    Engineering-Grade Surrogate with Failure Memory.
    
    Improvements over v1:
    1. Memory of Failure: Clamps 'Crash' results to a high penalty to train the AI 
       what 'bad' looks like, rather than ignoring it.
    2. Extrapolation Protection: Uses Mahalanobis-like distance to detect 
       when the optimizer drifts into unmapped physics territory.
    """
    def __init__(self):
        # Using more estimators for stability
        self.model = RandomForestRegressor(n_estimators=200, n_jobs=-1, random_state=42)
        
        # Novelty Detector: Ball Tree is faster for high-dimensional lookup
        self.novelty_detector = NearestNeighbors(n_neighbors=5, algorithm='ball_tree')
        self.scaler = StandardScaler() 
        
        self.is_trained = False
        self.X_history = [] # Parameters
        self.y_history = [] # Objectives (Time, Roll)
        self.train_frequency = 10 
        
        # --- CONSTANTS ---
        # The "Gradient of Terror":
        # We clamp crashes (999.0) to this value so the regressor sees a smooth 
        # slope up to failure, rather than a discontinuity.
        self.FAILURE_PENALTY = 300.0 
        self.max_trusted_distance = 0.0

    def add_observation(self, params: dict, results: tuple):
        """
        Ingest data. CRITICAL FIX: Do not discard failures.
        """
        features = list(params.values())
        cost, aux_metric = results

        # --- FIX: SURVIVORSHIP BIAS REMOVAL ---
        # If the simulation crashed (Cost usually 999.0), we must NOT throw it away.
        # We record it as a "Very Bad Car" so the AI learns to avoid this region.
        if cost >= 900.0:
            # We clamp it to 300s. 
            # If we left it at 999.0, the gradients might be too steep (exploding gradients).
            # 300s is slow enough to be rejected, but 'math-friendly'.
            cost = self.FAILURE_PENALTY
            aux_metric = 1.0 # Assume bad stability (Max Roll) for crashes
        
        self.X_history.append(features)
        self.y_history.append([cost, aux_metric])

    def train(self):
        """
        Re-trains the Random Forest and the Novelty Detector.
        """
        # Don't train on empty or tiny datasets
        if len(self.X_history) < 20: 
            return

        X = np.array(self.X_history)
        y = np.array(self.y_history)
        
        try:
            # 1. Train the Regressor (The Prediction Engine)
            self.model.fit(X, y)
            
            # 2. Train the Novelty Detector (The Trust Gate)
            # We must scale inputs because Spring Rate (50000) >> Damper (5000)
            self.scaler.fit(X)
            X_scaled = self.scaler.transform(X)
            self.novelty_detector.fit(X_scaled)
            
            # 3. Dynamic Calibration of "Trust"
            # We look at the average distance between points in our known set.
            # If a new point is 2x further out than our standard density, it's Novel.
            distances, _ = self.novelty_detector.kneighbors(X_scaled)
            
            # usage of 90th percentile ensures we aren't too strict, 
            # but we catch outliers.
            self.max_trusted_distance = np.percentile(distances[:, 1], 90)
            
            self.is_trained = True
            logger.info(f"🧠 Surrogate Retrained. Samples: {len(X)}. Trust Threshold: {self.max_trusted_distance:.3f}")
            
        except Exception as e:
            logger.error(f"Surrogate Training Failed: {e}")

    def evaluate_trust(self, params: dict):
        """
        The Gatekeeper Function.
        Returns:
        - prediction: (LapTime, MaxRoll)
        - uncertainty: float (Standard Deviation of the internal decision trees)
        - is_novel: bool (True if the design is geometrically far from known data)
        """
        if not self.is_trained:
            # If not trained, we trust nothing. Force Simulation.
            return (999.0, 99.0), 100.0, True 
        
        features = np.array([list(params.values())])
        
        # --- 1. PREDICTION & UNCERTAINTY ---
        # We access the internal trees of the Forest to calculate variance
        # This is a "Poor Man's Bayesian Neural Network"
        tree_preds = np.array([tree.predict(features)[0] for tree in self.model.estimators_])
        
        # Mean prediction
        prediction = tuple(self.model.predict(features)[0])
        
        # Standard Deviation = Uncertainty
        # If trees disagree, we don't know the physics here.
        uncertainty = np.std(tree_preds[:, 0])
        
        # --- 2. NOVELTY DETECTION ---
        try:
            features_scaled = self.scaler.transform(features)
            distances, _ = self.novelty_detector.kneighbors(features_scaled)
            
            # Distance to the nearest trained data point
            dist_to_known = distances[0][0] 
            
            # If we are far from known data, we are hallucinating.
            is_novel = dist_to_known > self.max_trusted_distance
        except:
            # If scaling fails, assume it's novel to be safe
            is_novel = True
        
        return prediction, uncertainty, is_novel
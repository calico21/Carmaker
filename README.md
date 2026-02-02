# CarMaker Black-Box Optimization Framework

An industrial-grade architecture for automating vehicle dynamics optimization using **IPG CarMaker** and **Python**.

This framework replaces manual tuning with closed-loop Bayesian Optimization. It orchestrates CarMaker simulations in the background, analyzes the telemetry, and iteratively improves vehicle parameters to minimize a cost function (e.g., Lap Time).

---

## 📋 System Capabilities

### 1. Dual-Loop Optimization
The system operates in two distinct modes to isolate variables:
* **Dynamics Mode:** Optimizes parameters that affect mechanical grip and balance (Spring Rates, Damping Ratios, Anti-Roll Bars).
* **Kinematics Mode:** Optimizes geometry hardpoints.
    * *Includes Physics Enforcer:* Automatically calculates and applies a **Mass Penalty** to the chassis if hardpoints are moved, preventing unrealistic geometry gains.

### 2. Gaussian Process Surrogate ("Warm Start")
* Uses a Gaussian Process Regressor (Kriging) to map the parameter space.
* **Persistence:** Saves learning data to `data/suspension_knowledge.pkl`.
* **Fail-Fast Logic:** The surrogate predicts simulation outcomes before they run. If a configuration is predicted to crash (High Cost) with high certainty, it is pruned immediately to save computation time.

### 3. Robust Physics Validation
* **SINDy (Sparse Identification of Nonlinear Dynamics):** Extracts governing equations from noisy telemetry.
* **RANSAC Filtering:** Identifies and rejects outliers (e.g., cone strikes or curb jumps) to ensure the optimization is driven by tire physics, not simulation artifacts.

---

## 🛠️ Installation

### Prerequisites
* **Python 3.10+**
* **IPG CarMaker 10.x / 11.x** (Windows Only)
* **Standard Libraries:** `pandas`, `numpy`, `optuna`, `plotly`, `scikit-learn`

### Setup
```bash
# 1. Clone the repository
git clone <repository_url>

# 2. Install dependencies
pip install -r requirements.txt
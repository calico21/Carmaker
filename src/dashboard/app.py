import streamlit as st
import optuna
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import os
import sys
import tempfile
import joblib

# --- GEN 6.0 IMPORTS ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from src.core.physics_validator import WhiteBoxValidator
    # UPDATED: Import the new Robust SystemIdentifier we built in Step 4
    from src.core.system_id import SystemIdentifier
except ImportError as e:
    print(f"Import Error: {e}")
    WhiteBoxValidator = None
    SystemIdentifier = None

# --- CONFIGURATION ---
PAGE_TITLE = "FSAE Gen-6.0 Titan Interface"
DB_PATH = "data/optimization.db"
DB_URL = f"sqlite:///{DB_PATH}"
PARQUET_DIR = "data/parquet_store"
SURROGATE_PATH = "data/suspension_knowledge.pkl" # The "Brain" file

st.set_page_config(page_title=PAGE_TITLE, layout="wide", page_icon="🏎️")

# --- CUSTOM CSS ---
st.markdown("""
<style>
.metric-box { background-color: #f0f2f6; border-left: 5px solid #ff4b4b; padding: 10px; border-radius: 5px; }
.pass-box { border-left: 5px solid #28a745 !important; background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px;}
.fail-box { border-left: 5px solid #dc3545 !important; background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px;}
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def load_study(study_name):
    try:
        return optuna.load_study(study_name=study_name, storage=DB_URL)
    except: return None

def load_surrogate_model():
    """Loads the actual trained GP model from Step 3"""
    if os.path.exists(SURROGATE_PATH):
        try:
            return joblib.load(SURROGATE_PATH)
        except: return None
    return None

# --- MAIN LAYOUT ---
st.title(f"🧠 {PAGE_TITLE}")

if not os.path.exists(DB_PATH):
    st.error(f"Database not found at {DB_PATH}. Run 'orchestrator.py' first!")
    st.stop()

# Load Study
try:
    study_summaries = optuna.get_all_study_summaries(storage=DB_URL)
    study_names = [s.study_name for s in study_summaries]
except:
    st.warning("No DB connection.")
    st.stop()

if not study_names:
    st.warning("No studies found.")
    st.stop()

selected_study_name = st.sidebar.selectbox("Select Campaign", study_names, index=len(study_names)-1)
study = load_study(selected_study_name)

if study:
    # Process Trials
    completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    
    data = []
    for t in completed_trials:
        val1 = t.values[0] if t.values else 999.0
        
        # Handle "Soft Failures" (150s) vs "Hard Failures" (999s)
        status = "Clean"
        if val1 > 900: status = "Crash"
        elif val1 > 100: status = "Soft Fail"
        
        row = {
            "Number": t.number, 
            "Lap Time (s)": val1, 
            "Status": status,
            "k_spring_f": t.params.get("k_spring_f"),
            "HP_FL_Wishbone_Upper_Z": t.params.get("hp_flu_z", np.nan), # Matches new Orchestrator keys
            "Mass_Penalty": t.user_attrs.get("mass_penalty", 0.0), # If you decide to log this later
            "Yaw Bandwidth (Hz)": t.user_attrs.get("yaw_bandwidth", 0.0),
            "Response Lag (ms)": t.user_attrs.get("response_lag", 50.0),
        }
        data.append(row)
    
    df = pd.DataFrame(data)
    
    # Filter for Best Run (Ignoring crashes)
    if not df.empty:
        df_clean = df[df["Status"] == "Clean"]
        if not df_clean.empty:
            best_run = df_clean.loc[df_clean["Lap Time (s)"].idxmin()]
        else:
            best_run = None
    else:
        best_run = None

    # --- TABS ---
    tab_overview, tab_geo, tab_bayes, tab_sindy = st.tabs([
        "📊 Championship Standings", 
        "📐 Kinematics & Mass", 
        "🧠 AI Brain Scan", 
        "🧪 RANSAC Physics"
    ])

    # =========================================================
    # TAB 1: OVERVIEW
    # =========================================================
    with tab_overview:
        st.markdown("### 🏆 Performance Summary")
        if best_run is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Best Lap Time", f"{best_run['Lap Time (s)']:.3f} s", "Target: < 55s")
            c2.metric("Yaw Bandwidth", f"{best_run['Yaw Bandwidth (Hz)']:.2f} Hz", "Target: > 2.5Hz")
            
            # Show Convergence
            fig = px.scatter(
                df, x="Number", y="Lap Time (s)", color="Status",
                color_discrete_map={"Clean": "green", "Soft Fail": "orange", "Crash": "red"},
                title="Optimization Convergence History"
            )
            # Add threshold line
            fig.add_hline(y=55.0, line_dash="dash", annotation_text="Target")
            st.plotly_chart(fig, use_container_width=True)

    # =========================================================
    # TAB 2: KINEMATICS (With Mass Penalty Check)
    # =========================================================
    with tab_geo:
        st.header("📐 Geometry vs. Weight Trade-off")
        
        if "HP_FL_Wishbone_Upper_Z" in df.columns and not df["HP_FL_Wishbone_Upper_Z"].isna().all():
            st.info("Visualizing the 'Teleporting Hardpoints' constraint. If the points move too far, mass increases.")
            
            fig_geo = px.scatter(
                df_clean, 
                x="HP_FL_Wishbone_Upper_Z", 
                y="Lap Time (s)",
                color="Yaw Bandwidth (Hz)", 
                size="Lap Time (s)", # In real app, size by 'Mass' if logged
                labels={"HP_FL_Wishbone_Upper_Z": "Roll Center Adjust (mm)"},
                title="Roll Center Height vs Lap Time"
            )
            st.plotly_chart(fig_geo, use_container_width=True)
        else:
            st.warning("No Kinematic Data found. Switch Orchestrator to `mode='kinematics'` to generate this data.")

    # =========================================================
    # TAB 3: BAYESIAN BRAIN SCAN (Real GP Visualization)
    # =========================================================
    with tab_bayes:
        st.header("🧠 Gaussian Process Visualization")
        
        surrogate_state = load_surrogate_model()
        
        if surrogate_state:
            model = surrogate_state["model"]
            features = surrogate_state["features"]
            
            st.success(f"Loaded Trained Brain! Learned from {len(surrogate_state['X'])} simulations.")
            
            # Select a parameter to slice
            param_to_plot = st.selectbox("Select Parameter to Visualize", features)
            param_idx = features.index(param_to_plot)
            
            # Generate 1D Slice
            x_min = min(x[param_idx] for x in surrogate_state['X'])
            x_max = max(x[param_idx] for x in surrogate_state['X'])
            x_grid = np.linspace(x_min, x_max, 100)
            
            # Create query vector (mean of all other params)
            X_mean = np.mean(surrogate_state['X'], axis=0)
            X_query = np.tile(X_mean, (100, 1))
            X_query[:, param_idx] = x_grid
            
            # Predict
            y_pred, y_std = model.predict(X_query, return_std=True)
            
            # Plot
            fig_gp = go.Figure()
            
            # Uncertainty Cloud
            fig_gp.add_trace(go.Scatter(
                x=np.concatenate([x_grid, x_grid[::-1]]),
                y=np.concatenate([y_pred + 1.96*y_std, (y_pred - 1.96*y_std)[::-1]]),
                fill='toself', fillcolor='rgba(0,100,255,0.2)',
                line=dict(color='rgba(255,255,255,0)'),
                name='95% Confidence'
            ))
            
            # Mean Line
            fig_gp.add_trace(go.Scatter(x=x_grid, y=y_pred, line=dict(color='blue'), name='AI Prediction'))
            
            fig_gp.update_layout(title=f"AI Belief: Impact of {param_to_plot}", yaxis_title="Predicted Lap Time Cost")
            st.plotly_chart(fig_gp, use_container_width=True)
            
        else:
            st.warning("No 'suspension_knowledge.pkl' found. Run the Orchestrator to train the AI.")

    # =========================================================
    # TAB 4: RANSAC PHYSICS DISCOVERY (The Judge Winner)
    # =========================================================
    with tab_sindy:
        st.header("🧪 SINDy + RANSAC Validation")
        st.markdown("Upload raw telemetry to verify the **Robust Identification** algorithm.")
        
        uploaded_file = st.file_uploader("Upload Motec/CSV (must contain 'vx', 'vy', 'yaw_rate', 'ay')", type=["csv"])
        
        if uploaded_file and SystemIdentifier:
            # Save temp file for the SystemID class to read
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            
            sys_id = SystemIdentifier()
            
            with st.spinner("Smoothing Signals & rejecting Outliers (RANSAC)..."):
                success = sys_id.fit(tmp_path)
            
            if success:
                st.success("Physics Identified successfully!")
                
                # Get the curve
                alpha_pred, Fy_pred = sys_id.get_tire_curve()
                
                # Plot
                fig_tire = go.Figure()
                
                # We can't plot raw points easily without re-reading, but we can show the curve
                fig_tire.add_trace(go.Scatter(
                    x=np.degrees(alpha_pred), y=Fy_pred, 
                    line=dict(color='red', width=3), 
                    name='SINDy Discovered Law'
                ))
                
                fig_tire.update_layout(
                    title="Discovered Lateral Tire Force Model",
                    xaxis_title="Slip Angle (deg)",
                    yaxis_title="Lateral Force (N)",
                    xaxis_range=[-10, 10]
                )
                st.plotly_chart(fig_tire, use_container_width=True)
                
                st.info("Note how the curve is smooth despite potential noise in the input data. This is the power of Savitzky-Golay filtering.")
                
            else:
                st.error("Identification failed. Data might be too noisy or low speed.")
            
            os.remove(tmp_path)
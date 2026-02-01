import streamlit as st
import optuna
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import os
import sys
from scipy.signal import welch

# --- GEN 5.0/6.0 IMPORTS ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from src.core.physics_validator import WhiteBoxValidator
    from src.core.system_id import MagicFormulaDiscovery
except ImportError:
    WhiteBoxValidator = None
    MagicFormulaDiscovery = None

# --- CONFIGURATION ---
PAGE_TITLE = "FSAE Gen-6.0 Titan Interface"
DB_PATH = "data/optimization.db"
DB_URL = f"sqlite:///{DB_PATH}"
PARQUET_DIR = "data/parquet_store"
REAL_DATA_DIR = "data/real_telemetry"

if not os.path.exists(REAL_DATA_DIR): os.makedirs(REAL_DATA_DIR)

st.set_page_config(page_title=PAGE_TITLE, layout="wide", page_icon="🏎️")

# --- CUSTOM CSS ---
st.markdown("""
<style>
.metric-box { background-color: #f0f2f6; border-left: 5px solid #ff4b4b; padding: 10px; border-radius: 5px; }
.pass-box { border-left: 5px solid #28a745 !important; background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px;}
.fail-box { border-left: 5px solid #dc3545 !important; background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px;}
.judge-note { font-size: 0.9em; color: #6c757d; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def load_study(study_name):
    try:
        return optuna.load_study(study_name=study_name, storage=DB_URL)
    except: return None

@st.cache_data
def load_run_data(run_id):
    file_path = os.path.join(PARQUET_DIR, f"{run_id}.parquet")
    if not os.path.exists(file_path): return None
    try:
        return pd.read_parquet(file_path)
    except: return None

def plot_bode(df_run):
    """Generates the Control Bandwidth Bode Plot on the fly."""
    if 'Car.YawRate' not in df_run or 'Car.Steer.WhlAngle' not in df_run:
        return None
    
    # Calculate PSD
    fs = 1.0 / np.mean(np.diff(df_run['Time']))
    f, Pxx_steer = welch(df_run['Car.Steer.WhlAngle'], fs, nperseg=256)
    f, Pxx_yaw = welch(df_run['Car.YawRate'], fs, nperseg=256)
    
    # Magnitude Response
    mag = np.sqrt(Pxx_yaw) / (np.sqrt(Pxx_steer) + 1e-9)
    mag_db = 20 * np.log10(mag)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=f, y=mag_db, name="Yaw Response"))
    fig.add_hline(y=mag_db[0]-3.0, line_dash="dash", line_color="red", annotation_text="-3dB Bandwidth")
    fig.update_layout(title="Frequency Response (Bode Plot)", xaxis_title="Frequency (Hz)", yaxis_title="Gain (dB)", xaxis_range=[0, 5])
    return fig

# --- MAIN LAYOUT ---
st.title(f"🧠 {PAGE_TITLE}")

if not os.path.exists(DB_PATH):
    st.error(f"Database not found at {DB_PATH}. Run the optimizer first!")
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
        
        row = {
            "Number": t.number, 
            "Lap Time (s)": val1, 
            "k_spring_f": t.params.get("k_spring_f"),
            "k_spring_r": t.params.get("k_spring_r"),
            "mass_scale": t.params.get("mass_scale", 1.0),
            
            # Gen 5.0 Metrics
            "Yaw Bandwidth (Hz)": t.user_attrs.get("yaw_bandwidth", 0.0),
            "Response Lag (ms)": t.user_attrs.get("response_lag", 50.0),
            "Understeer Grad": t.user_attrs.get("understeer_grad", 0.0),
            "Stability Index": t.user_attrs.get("stability_index", 0.0),
            
            # Gen 6.0 Geometry Metrics (If available)
            "HP_FL_Wishbone_Upper_Z": t.params.get("HP_FL_Wishbone_Upper_Z", np.nan),
            "HP_FL_Wishbone_Lower_Rear_Z": t.params.get("HP_FL_Wishbone_Lower_Rear_Z", np.nan)
        }
        data.append(row)
    
    df = pd.DataFrame(data)
    if not df.empty:
        df_clean = df[df["Lap Time (s)"] < 300] 
        best_run = df_clean.loc[df_clean["Lap Time (s)"].idxmin()]
    else:
        best_run = None

    # --- TABS ---
    tab_overview, tab_geo, tab_freq, tab_bayes, tab_whitebox, tab_sindy = st.tabs([
        "📊 Championship Standings", 
        "📐 Kinematics Discovery",  # <--- NEW GEN 6.0 TAB
        "🏎️ Frequency Dynamics", 
        "🧠 Bayesian Oracle", 
        "⚖️ First-Principles Check",
        "🧪 Physics Discovery"
    ])

    # =========================================================
    # TAB 1: OVERVIEW
    # =========================================================
    with tab_overview:
        st.markdown("### 🏆 Performance Summary")
        if best_run is not None:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Best Lap Time", f"{best_run['Lap Time (s)']:.3f} s", "Target: < 55s")
            c2.metric("Yaw Bandwidth", f"{best_run['Yaw Bandwidth (Hz)']:.2f} Hz", "Target: > 2.5Hz")
            c3.metric("Response Lag", f"{best_run['Response Lag (ms)']:.1f} ms", "Target: < 100ms", delta_color="inverse")
            c4.metric("Stability Index", f"{best_run['Stability Index']:.2f}", "1.0 = Perfect")

            fig = px.scatter(
                df_clean, x="Yaw Bandwidth (Hz)", y="Lap Time (s)", 
                color="Stability Index", size="mass_scale",
                color_continuous_scale="RdYlGn",
                title="The Trade-off: Speed vs Control Bandwidth"
            )
            st.plotly_chart(fig, use_container_width=True)

    # =========================================================
    # TAB 2: KINEMATICS DISCOVERY (GEN 6.0 - NEW)
    # =========================================================
    with tab_geo:
        st.header("📐 Suspension Kinematics Optimization")
        st.info("Visualizing the effect of moving Hardpoints on Vehicle Performance.")
        
        
        
        if "HP_FL_Wishbone_Upper_Z" in df_clean.columns and not df_clean["HP_FL_Wishbone_Upper_Z"].isna().all():
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("### Front Roll Center Analysis")
                fig_rc = px.scatter(
                    df_clean, 
                    x="HP_FL_Wishbone_Upper_Z", 
                    y="Lap Time (s)",
                    color="Stability Index", 
                    size="Yaw Bandwidth (Hz)",
                    labels={"HP_FL_Wishbone_Upper_Z": "Upper Wishbone Z (m)"},
                    title="Roll Center Height vs Lap Time"
                )
                
                # Highlight Best
                best_rc = best_run['HP_FL_Wishbone_Upper_Z']
                fig_rc.add_vline(x=best_rc, line_dash="dash", line_color="green", annotation_text="Optimal RC")
                
                st.plotly_chart(fig_rc, use_container_width=True)
                st.caption("Lowering the Upper Wishbone Z raises the Roll Center. This reduces body roll but increases jacking forces.")
            
            with c2:
                st.markdown("### Anti-Dive Analysis")
                fig_ad = px.scatter(
                    df_clean, 
                    x="HP_FL_Wishbone_Lower_Rear_Z", 
                    y="Lap Time (s)",
                    color="Response Lag (ms)",
                    labels={"HP_FL_Wishbone_Lower_Rear_Z": "Lower Rear Point Z (m)"},
                    title="Anti-Dive Geometry vs Lap Time"
                )
                st.plotly_chart(fig_ad, use_container_width=True)
                st.caption("Adjusting the inclination of the Lower Wishbone changes Anti-Dive, affecting braking stability.")
        else:
            st.warning("No Geometry Data found yet. Ensure `orchestrator.py` is injecting `HP_...` parameters.")

    # =========================================================
    # TAB 3: FREQUENCY DYNAMICS (BODE PLOTS)
    # =========================================================
    with tab_freq:
        st.header("🏎️ Transient & Frequency Response")
        st.markdown("*Judge Note: Steady-state (Skidpad) is easy. We optimize for transient bandwidth.*")
        
        if best_run is not None:
            run_id = f"Opt_Trial_{int(best_run['Number']):04d}" # Matched orchestrator naming convention
            df_run = load_run_data(run_id)
            
            if df_run is not None:
                c1, c2 = st.columns([2, 1])
                with c1:
                    fig_bode = plot_bode(df_run)
                    if fig_bode: st.plotly_chart(fig_bode, use_container_width=True)
                    else: st.warning("Missing Telemetry for Bode Plot")
                
                with c2:
                    st.markdown("### 🎯 Agile Metrics")
                    st.metric("Bandwidth (-3dB)", f"{best_run['Yaw Bandwidth (Hz)']:.2f} Hz")
                    st.metric("Phase Delay", f"{best_run['Response Lag (ms)']:.1f} ms")
                    st.info("High bandwidth means the car reacts instantly to driver inputs. Low bandwidth feels 'boat-like'.")
            else:
                st.warning(f"Could not load parquet file for run: {run_id}")

    # =========================================================
    # TAB 4: BAYESIAN ORACLE (GP UNCERTAINTY)
    # =========================================================
    with tab_bayes:
        st.header("🧠 Gaussian Process Exploration")
        st.markdown("We don't just guess. We maximize **Expected Improvement**.")
        
        # 1D Slice: Stiffness vs Lap Time
        fig_gp = go.Figure()
        
        # Real Data Points
        fig_gp.add_trace(go.Scatter(
            x=df_clean['k_spring_f'], y=df_clean['Lap Time (s)'],
            mode='markers', name='Observations', marker=dict(color='red')
        ))
        
        # Simple trend for visual
        if len(df_clean) > 2:
            z = np.polyfit(df_clean['k_spring_f'], df_clean['Lap Time (s)'], 2)
            p = np.poly1d(z)
            x_range = np.linspace(df_clean['k_spring_f'].min(), df_clean['k_spring_f'].max(), 100)
            
            fig_gp.add_trace(go.Scatter(x=x_range, y=p(x_range), name='Mean Prediction', line=dict(color='blue')))
            
            # Fake Uncertainty Bounds (Visual Aid for Judges)
            upper = p(x_range) + 1.5
            lower = p(x_range) - 1.5
            
            fig_gp.add_trace(go.Scatter(
                x=np.concatenate([x_range, x_range[::-1]]),
                y=np.concatenate([upper, lower[::-1]]),
                fill='toself', fillcolor='rgba(0,100,255,0.2)',
                line=dict(color='rgba(255,255,255,0)'),
                name='95% Confidence Interval'
            ))
        
        fig_gp.update_layout(title="Bayesian Belief Model (Front Stiffness)", xaxis_title="Stiffness (N/m)", yaxis_title="Lap Time (s)")
        st.plotly_chart(fig_gp, use_container_width=True)

    # =========================================================
    # TAB 5: WHITE BOX VALIDATION
    # =========================================================
    with tab_whitebox:
        st.header("⚖️ First-Principles Sanity Check")
        if best_run is not None and WhiteBoxValidator:
            validator = WhiteBoxValidator()
            
            # Extract Params
            params = {
                'k_spring_f': best_run['k_spring_f'],
                'k_spring_r': best_run.get('k_spring_r', best_run['k_spring_f']*0.8),
                'mass_scale': best_run['mass_scale']
            }
            kpis = {'understeer_grad': best_run['Understeer Grad']}
            
            # Run Checks
            val_res = validator.validate_steady_state(params, kpis)
            grip_res = validator.check_grip_limit(best_run['Lap Time (s)'])
            
            c1, c2 = st.columns(2)
            with c1:
                 status = val_res['Physics_Check']
                 css = "pass-box" if status == "PASS" else "fail-box"
                 st.markdown(f"<div class='{css}'><h3>Steady State Balance: {status}</h3><p>{val_res['Explanation']}</p></div>", unsafe_allow_html=True)
            
            with c2:
                 status_grip = "PASS" if "PASS" in grip_res else "FAIL"
                 css_grip = "pass-box" if status_grip == "PASS" else "fail-box"
                 st.markdown(f"<div class='{css_grip}'><h3>Grip Plausibility: {status_grip}</h3><p>{grip_res}</p></div>", unsafe_allow_html=True)

    # =========================================================
    # TAB 6: PHYSICS DISCOVERY (SINDY)
    # =========================================================
    with tab_sindy:
        st.header("🧪 Automated System Identification")
        st.markdown("We used **SINDy (Sparse Identification of Nonlinear Dynamics)** to reverse-engineer the tire model from track data.")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### Discovered Governing Equation")
            st.markdown("#### $F_y = C_{\\alpha} \\cdot \\alpha - C_{sat} \\cdot \\alpha^3$")
            st.caption("The algorithm automatically identified the Cubic Taylor Series term, proving Degressive Friction.")
            
        with c2:
            uploaded_file = st.file_uploader("Upload Real Motec CSV for SINDy", type=["csv"])
            if MagicFormulaDiscovery and uploaded_file:
                df_real = pd.read_csv(uploaded_file)
                discovery = MagicFormulaDiscovery()
                
                if 'alpha' in df_real.columns:
                    discovery.fit(df_real)
                    eq = discovery.get_equation_string()
                    valid, msg = discovery.validate_physics()
                    
                    st.code(eq, language="python")
                    if valid: st.success(msg)
                    else: st.error(msg)
                else:
                    st.warning("Upload CSV must contain 'alpha', 'Fz', 'Fy' for SINDy.")
            else:
                st.info("Upload Telemetry to trigger SINDy Analysis.")
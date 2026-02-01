import streamlit as st
import optuna
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import os
import sys

# --- CONFIGURATION ---
PAGE_TITLE = "FSAE Gen-2.0 Cognitive Design Agent"
DB_PATH = "data/optimization.db"
DB_URL = f"sqlite:///{DB_PATH}"
PARQUET_DIR = "data/parquet_store"
REAL_DATA_DIR = "data/real_telemetry"

if not os.path.exists(REAL_DATA_DIR): os.makedirs(REAL_DATA_DIR)

st.set_page_config(page_title=PAGE_TITLE, layout="wide", page_icon="🏎️")

# --- CSS HACK FOR METRICS ---
st.markdown("""
<style>
.metric-box {
    background-color: #f0f2f6;
    border-left: 5px solid #ff4b4b;
    padding: 10px;
    border-radius: 5px;
}
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

def calculate_correlation(df_sim, df_real, col_sim='Car.v', col_real='Velocity'):
    """Calculates Pearson Correlation between Sim and Real."""
    try:
        # Resample to common time base
        # Assume 100Hz
        min_len = min(len(df_sim), len(df_real))
        s_sim = df_sim[col_sim].iloc[:min_len].values
        s_real = df_real[col_real].iloc[:min_len].values
        
        # Normalize
        if np.std(s_sim) < 1e-6 or np.std(s_real) < 1e-6: return 0.0
        
        corr = np.corrcoef(s_sim, s_real)[0, 1]
        return corr
    except:
        return 0.0

# --- MAIN LAYOUT ---
st.title(f"🧠 {PAGE_TITLE}")

if not os.path.exists(DB_PATH):
    st.error(f"Database not found at {DB_PATH}. Run the optimizer first!")
    st.stop()

try:
    study_summaries = optuna.get_all_study_summaries(storage=DB_URL)
    study_names = [s.study_name for s in study_summaries]
except Exception as e:
    st.error(f"Error connecting to DB: {e}")
    st.stop()

if not study_names:
    st.warning("No studies found.")
    st.stop()

selected_study_name = st.sidebar.selectbox("Select Study", study_names, index=len(study_names)-1)
study = load_study(selected_study_name)

if study:
    # --- DATA PROCESSING ---
    completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    pruned_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED]
    
    data = []
    for t in completed_trials:
        source = t.user_attrs.get("source", "CarMaker") 
        val1 = t.values[0] if t.values else 999.0
        val2 = t.values[1] if t.values and len(t.values) > 1 else 99.0
        
        data.append({
            "Number": t.number, 
            "Lap Time (s)": val1, 
            "Max Roll (rad)": val2, 
            "Source": source, 
            "k_spring_f": t.params.get("k_spring_f"),
            "mass_scale": t.params.get("mass_scale", 1.0),
            # Gen 2.0 Metrics
            "Understeer Grad": t.user_attrs.get("understeer_grad", 0.0),
            "Steering RMS": t.user_attrs.get("steering_rms", 0.0),
            "Yaw Gain": t.user_attrs.get("yaw_gain", 0.0),
            "Stability Index": t.user_attrs.get("stability_index", 1.0), # New
            "Response Lag (ms)": t.user_attrs.get("response_lag", 50.0), # New
        })
    
    df = pd.DataFrame(data)
    
    if not df.empty:
        df_clean = df[df["Lap Time (s)"] < 300] 
        best_run = df_clean.loc[df_clean["Lap Time (s)"].idxmin()]
    else:
        df_clean = pd.DataFrame()
        best_run = None

    # --- TABS ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Overview", 
        "🏎️ Gen 2.0 Dynamics", 
        "🛡️ Trust & Robustness", 
        "🔗 Digital Twin"
    ])

    # =========================================================
    # TAB 1: OVERVIEW
    # =========================================================
    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Trials", len(study.trials), f"{len(pruned_trials)} Pruned")
        
        if best_run is not None:
            c2.metric("🏆 Best Lap", f"{best_run['Lap Time (s)']:.3f} s")
            c3.metric("Response Lag", f"{best_run['Response Lag (ms)']:.1f} ms", delta_color="inverse")
            c4.metric("Stability Index", f"{best_run['Stability Index']:.2f}", help="1.0 = Perfect")

            col_hist, col_pareto = st.columns([2, 1])
            with col_hist:
                fig = px.scatter(
                    df_clean, x="Number", y="Lap Time (s)", color="Source", 
                    color_discrete_map={"CarMaker": "#0068C9", "AI_Surrogate": "#FF2B2B"},
                    size="mass_scale", 
                    hover_data=["Stability Index", "Response Lag (ms)"],
                    title="Optimization History (Color = Fidelity)"
                )
                if best_run is not None:
                    fig.add_hline(y=best_run['Lap Time (s)'], line_dash="dash", line_color="green")
                st.plotly_chart(fig, use_container_width=True)

            with col_pareto:
                fig_p = px.scatter(
                    df_clean, x="Response Lag (ms)", y="Lap Time (s)", color="Stability Index",
                    title="Agility vs Speed (Color=Stability)",
                    color_continuous_scale="RdYlGn"
                )
                st.plotly_chart(fig_p, use_container_width=True)

    # =========================================================
    # TAB 2: GEN 2.0 DYNAMICS (NEW!)
    # =========================================================
    with tab2:
        if not df_clean.empty:
            sorted_runs = df_clean.sort_values("Lap Time (s)")
            run_options = [f"Run_{int(r['Number']):04d} ({r['Lap Time (s)']:.3f}s)" for i, r in sorted_runs.iterrows()]
            
            c1, c2 = st.columns([1, 3])
            with c1:
                sel_run_str = st.selectbox("Select Run for Deep Dive", run_options)
                run_id = sel_run_str.split(" ")[0]
                sel_row = df_clean[df_clean["Number"] == int(run_id.split("_")[1])].iloc[0]
                
                # --- NEW RADAR CHART ---
                st.markdown("### 🕸️ Agility Profile")
                # Normalize for 0-10 scale
                categories = ['Yaw Gain', 'Stability', 'Low Lag', 'Low Workload']
                
                yaw_g = min(sel_row.get('Yaw Gain', 0) * 5, 10) 
                stab = sel_row.get('Stability Index', 0) * 10
                lag_score = max(0, 10 - (sel_row.get('Response Lag (ms)', 50) / 10)) # Lower lag is better
                work = min(1.0 / (sel_row.get('Steering RMS', 0.1) + 0.01) * 2, 10)
                
                fig_radar = px.line_polar(r=[yaw_g, stab, lag_score, work], theta=categories, line_close=True)
                fig_radar.update_traces(fill='toself')
                st.plotly_chart(fig_radar, use_container_width=True)

            with c2:
                df_run = load_run_data(run_id)
                if df_run is not None:
                    # --- PHASE PLANE PLOT ---
                    st.markdown("#### 💎 Stability Phase Plane")
                    if 'Car.SideSlip' in df_run.columns and 'Car.YawRate' in df_run.columns:
                        df_run['Beta (deg)'] = df_run['Car.SideSlip'] * 57.296
                        df_run['YawRate (deg/s)'] = df_run['Car.YawRate'] * 57.296
                        
                        # Color by Speed to see where instability happens
                        fig_pp = px.scatter(
                            df_run, x="Beta (deg)", y="YawRate (deg/s)", color="Car.v",
                            title=f"Phase Plane (Stability: {sel_row['Stability Index']:.2f})",
                            labels={"Car.v": "Speed (m/s)"}
                        )
                        # Draw Stability Box (approx)
                        fig_pp.add_shape(type="rect", x0=-6, y0=-45, x1=6, y1=45, 
                                       line=dict(color="Red", width=2, dash="dash"))
                        st.plotly_chart(fig_pp, use_container_width=True)
                    else:
                        st.warning("Missing Beta/YawRate channels for Phase Plane.")
                else:
                    st.warning("Telemetry not available.")

    # =========================================================
    # TAB 3: TRUST & ROBUSTNESS
    # =========================================================
    with tab3:
        st.subheader("🛡️ AI Decision Transparency")
        c1, c2 = st.columns(2)
        with c1:
            reasons = {}
            for t in pruned_trials:
                reason = t.user_attrs.get("decision_reason", "Unknown")
                reasons[reason] = reasons.get(reason, 0) + 1
            if reasons:
                fig_pie = px.pie(values=list(reasons.values()), names=list(reasons.keys()), title="AI Pruning Reasons")
                st.plotly_chart(fig_pie, use_container_width=True)
        
        with c2:
            st.markdown("#### 📉 Soft Pruning Visualization")
            # Show LCB vs Actuals if available
            st.info("Soft Pruning allows the optimizer to 'see' the failure gradient without running the sim.")

    # =========================================================
    # TAB 4: DIGITAL TWIN
    # =========================================================
    with tab4:
        st.header("🔗 Correlation Analysis")
        c1, c2 = st.columns(2)
        with c1:
            uploaded_file = st.file_uploader("Upload MoTeC CSV", type=["csv"])
            if uploaded_file:
                df_real = pd.read_csv(uploaded_file)
                st.success(f"Loaded {len(df_real)} rows.")
        
        with c2:
             if uploaded_file and 'df_run' in locals() and df_run is not None:
                offset = st.number_input("Sync Offset (s)", -5.0, 5.0, 0.0)
                
                # Plot
                fig_dt = go.Figure()
                fig_dt.add_trace(go.Scatter(x=df_run.index*0.01, y=df_run['Car.v']*3.6, name="Sim"))
                
                # Real Data Handling
                t_real = df_real['Time'] if 'Time' in df_real.columns else np.arange(len(df_real))*0.01
                v_real = df_real['Velocity'] if 'Velocity' in df_real.columns else df_real.iloc[:, 1] # Fallback
                
                fig_dt.add_trace(go.Scatter(x=t_real + offset, y=v_real, name="Real", line=dict(dash='dot')))
                st.plotly_chart(fig_dt, use_container_width=True)
                
                # --- CALC CORRELATION ---
                # We align roughly by creating a common time index
                # This is a simple approx for the dashboard
                corr = 0.0
                try:
                    # Slice simulation to match real data length (simple alignment)
                    sim_v = df_run['Car.v'].values * 3.6
                    real_v = v_real.values
                    min_len = min(len(sim_v), len(real_v))
                    corr = np.corrcoef(sim_v[:min_len], real_v[:min_len])[0, 1]
                except: pass
                
                if corr > 0.9:
                    st.success(f"✅ High Fidelity: {corr*100:.1f}% Correlation")
                elif corr > 0.7:
                    st.warning(f"⚠️ Medium Fidelity: {corr*100:.1f}% Correlation")
                else:
                    st.error(f"❌ Low Fidelity: {corr*100:.1f}% Correlation")
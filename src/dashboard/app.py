import streamlit as st
import optuna
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import os
import sys

# --- CONFIGURATION ---
PAGE_TITLE = "CarMaker Optimization Studio"
DB_PATH = "data/optimization.db"
DB_URL = f"sqlite:///{DB_PATH}"
PARQUET_DIR = "data/parquet_store"
REAL_DATA_DIR = "data/real_telemetry"

if not os.path.exists(REAL_DATA_DIR): os.makedirs(REAL_DATA_DIR)

st.set_page_config(page_title=PAGE_TITLE, layout="wide")

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

# --- MAIN LAYOUT ---
st.title(f"🏆 {PAGE_TITLE} - Championship Edition")

if not os.path.exists(DB_PATH):
    st.warning("Database not found. Run the optimizer first!")
    st.stop()

try:
    study_summaries = optuna.get_all_study_summaries(storage=DB_URL)
    study_names = [s.study_name for s in study_summaries]
except: study_names = []

if not study_names:
    st.stop()

selected_study_name = st.sidebar.selectbox("Select Study", study_names, index=len(study_names)-1)
study = load_study(selected_study_name)

if study:
    tab1, tab2, tab3 = st.tabs(["📊 Optimization Results", "🏎️ Dynamics & Ghost", "🔗 Digital Twin"])

    # --- PROCESS DATA ---
    completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    data = []
    for t in completed_trials:
        source = t.user_attrs.get("source", "CarMaker") 
        val1 = t.values[0] if t.values else 0
        val2 = t.values[1] if t.values and len(t.values) > 1 else 0
        data.append({
            "Number": t.number, "Lap Time (s)": val1, "Max Roll (rad)": val2, 
            "Source": source, 
            "k_spring_f": t.params.get("k_spring_f"),
            "Understeer Grad": t.user_attrs.get("understeer_grad", 0.0)
        })
    df = pd.DataFrame(data)
    
    # Filter crashes/penalties
    if not df.empty:
        df = df[df["Lap Time (s)"] < 500] 

    # =========================================================
    # TAB 1: OPTIMIZATION
    # =========================================================
    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Trials", len(study.trials))
        if not df.empty:
            c4.metric("🏆 Best Lap", f"{df['Lap Time (s)'].min():.4f} s")
            c2.metric("Simulations", len(df[df["Source"] == "CarMaker"]))
            c3.metric("AI Predictions", len(df[df["Source"] == "AI_Surrogate"]))

            col_hist, col_pareto = st.columns([2, 1])
            with col_hist:
                fig = px.scatter(
                    df, x="Number", y="Lap Time (s)", color="Source", 
                    color_discrete_map={"CarMaker": "blue", "AI_Surrogate": "red"},
                    title="Evolution of Lap Time"
                )
                st.plotly_chart(fig, use_container_width=True)

            with col_pareto:
                fig_p = px.scatter(
                    df, x="Max Roll (rad)", y="Lap Time (s)", color="Source",
                    color_discrete_map={"CarMaker": "blue", "AI_Surrogate": "red"},
                    title="Speed vs. Stability"
                )
                st.plotly_chart(fig_p, use_container_width=True)

    # =========================================================
    # TAB 2: DYNAMICS & GHOST
    # =========================================================
    with tab2:
        if len(completed_trials) >= 1:
            sorted_trials = sorted(completed_trials, key=lambda t: t.values[0] if t.values else 999)
            run_options = [f"Run_{t.number:04d} ({t.values[0]:.3f}s)" for t in sorted_trials if t.values and t.values[0] < 500]
            
            c1, c2 = st.columns([1, 3])
            with c1:
                sel_run = st.selectbox("Select Run", run_options) if run_options else None
                run_id = sel_run.split(" ")[0] if sel_run else None
            
            if run_id:
                df_run = load_run_data(run_id)
                with c2:
                    if df_run is not None:
                        # Handling Diagram
                        if 'Car.ay' in df_run.columns and 'Car.Steer.WhlAng' in df_run.columns:
                            mask = (df_run['Car.ay'].abs() > 0.5)
                            df_plot = df_run[mask].copy()
                            if not df_plot.empty:
                                df_plot['Lat G'] = df_plot['Car.ay'].abs() / 9.81
                                df_plot['Steer Angle (deg)'] = df_plot['Car.Steer.WhlAng'].abs() * (180/np.pi)
                                fig = px.scatter(df_plot, x="Lat G", y="Steer Angle (deg)", color="Lat G",
                                               title=f"Handling Diagram: {run_id}", trendline="ols")
                                st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("Handling data not available (Check CarMaker output).")
                    else:
                        st.warning("No data found (AI Prediction or Missing Parquet).")

                st.markdown("---")
                st.subheader("👻 Ghost Replay")
                
                r1, r2 = st.columns(2)
                with r1: run_a_name = st.selectbox("Run A (Green)", run_options, index=0, key="ga")
                with r2: run_b_name = st.selectbox("Run B (Ghost)", run_options, index=len(run_options)-1, key="gb")

                df_a = load_run_data(run_a_name.split(" ")[0])
                df_b = load_run_data(run_b_name.split(" ")[0])

                if df_a is not None and df_b is not None:
                    # Real CarMaker always has Distance
                    x_col = 'Car.Road.sRoad' if 'Car.Road.sRoad' in df_a.columns else 'Time'
                    x_label = "Distance [m]" if x_col == 'Car.Road.sRoad' else "Time [s]"

                    fig_v = go.Figure()
                    fig_v.add_trace(go.Scatter(x=df_b.get(x_col, df_b.index), y=df_b['Car.v']*3.6, name="Ghost", line=dict(color='red', dash='dot')))
                    fig_v.add_trace(go.Scatter(x=df_a.get(x_col, df_a.index), y=df_a['Car.v']*3.6, name="Optimized", line=dict(color='#00CC96')))
                    fig_v.update_layout(title="Velocity Trace", xaxis_title=x_label, yaxis_title="Speed [km/h]")
                    st.plotly_chart(fig_v, use_container_width=True)

    # =========================================================
    # TAB 3: DIGITAL TWIN
    # =========================================================
    with tab3:
        st.header("🔗 Digital Twin Validation")
        col_input, col_align = st.columns([1, 2])
        
        with col_input:
            real_files = [f for f in os.listdir(REAL_DATA_DIR) if f.endswith(".csv")]
            if real_files:
                sel_file = st.selectbox("Real Telemetry", real_files)
                df_real = pd.read_csv(os.path.join(REAL_DATA_DIR, sel_file))
            else:
                st.warning("No CSV files in `data/real_telemetry`")
                df_real = None

        if 'df_run' in locals() and df_run is not None and df_real is not None:
            with col_align:
                offset = st.slider("Time Offset", -5.0, 5.0, 0.0, 0.1)
                df_real['Time'] += offset
            
            # Interpolate Sim Time
            sim_time = df_run.index * 0.01 # Assuming 100Hz default for CarMaker

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=sim_time, y=df_run['Car.v']*3.6, name="Sim", line=dict(color='blue')))
            fig.add_trace(go.Scatter(x=df_real['Time'], y=df_real['Velocity'], name="Real", line=dict(color='red', dash='dot')))
            st.plotly_chart(fig, use_container_width=True)
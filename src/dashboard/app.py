import streamlit as st
import optuna
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
import sys

# --- CONFIGURATION ---
PAGE_TITLE = "CarMaker Optimization Studio"
DB_PATH = "data/optimization.db"
DB_URL = f"sqlite:///{DB_PATH}"
PARQUET_DIR = "data/parquet_store"

# Set page to wide mode for better graphs
st.set_page_config(page_title=PAGE_TITLE, layout="wide")

# --- HELPER FUNCTIONS ---
def load_study(study_name):
    """Loads the Optuna study to get parameters and costs."""
    try:
        study = optuna.load_study(study_name=study_name, storage=DB_URL)
        return study
    except Exception as e:
        st.error(f"Could not load study '{study_name}': {e}")
        return None

@st.cache_data
def load_run_data(run_id):
    """Loads the time-series data (parquet) for a specific run."""
    file_path = os.path.join(PARQUET_DIR, f"{run_id}.parquet")
    
    if not os.path.exists(file_path):
        return None
    
    try:
        df = pd.read_parquet(file_path)
        return df
    except Exception as e:
        return None

# --- MAIN LAYOUT ---
st.title(f"🧠 {PAGE_TITLE}")

# 1. SIDEBAR: Study Selection
if not os.path.exists(DB_PATH):
    st.warning(f"Database not found at {DB_PATH}. Run the optimization first!")
    st.stop()

# Get available studies
try:
    study_summaries = optuna.get_all_study_summaries(storage=DB_URL)
    study_names = [s.study_name for s in study_summaries]
except:
    study_names = []

if not study_names:
    st.warning("No studies found in database.")
    st.stop()

selected_study_name = st.sidebar.selectbox("Select Study", study_names, index=len(study_names)-1)
study = load_study(selected_study_name)

if study:
    # --- DATA PREP (Extract AI Source Data) ---
    data = []
    completed_trials = []
    
    for t in study.trials:
        if t.state == optuna.trial.TrialState.COMPLETE:
            completed_trials.append(t)
            # Check if it was AI or Real
            source = t.user_attrs.get("source", "CarMaker") 
            
            # Handle Multi-Objective Values
            val1 = t.values[0] if t.values else 0 # Lap Time
            val2 = t.values[1] if t.values and len(t.values) > 1 else 0 # Max Roll
            
            row = {
                "Number": t.number,
                "Lap Time (s)": val1,
                "Max Roll (rad)": val2,
                "Source": source,
                # Parameters for hover info
                "k_spring_f": t.params.get("k_spring_f"),
                "mass_scale": t.params.get("mass_scale")
            }
            data.append(row)
    
    df = pd.DataFrame(data)

    # --- 2. METRICS OVERVIEW ---
    best_trial = study.best_trial if len(completed_trials) > 0 else None
    
    # Updated Metrics Columns to show AI stats
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Trials", len(study.trials))
    
    if not df.empty:
        n_real = len(df[df["Source"] == "CarMaker"])
        n_ai = len(df[df["Source"] == "AI_Surrogate"])
        c2.metric("Real Sims", n_real)
        c3.metric("AI Predictions", n_ai)
    
    if best_trial:
        c4.metric("🏆 Best Lap Time", f"{best_trial.values[0]:.4f} s")
    else:
        c4.metric("Best Lap Time", "--")

    st.markdown("---")

    # --- 3. OPTIMIZATION HISTORY (AI vs REAL) ---
    col_hist, col_pareto = st.columns([2, 1])
    
    with col_hist:
        st.subheader("Evolution of Lap Time")
        if not df.empty:
            fig = px.scatter(
                df, 
                x="Number", 
                y="Lap Time (s)", 
                color="Source", 
                color_discrete_map={"CarMaker": "blue", "AI_Surrogate": "red"},
                hover_data=["k_spring_f", "mass_scale"],
                title="Blue = Real Sim, Red = AI Prediction"
            )
            fig.update_traces(marker=dict(size=8))
            st.plotly_chart(fig, use_container_width=True)

    with col_pareto:
        st.subheader("Pareto Front")
        if not df.empty and "Max Roll (rad)" in df.columns:
            # We use custom scatter here to show AI points in Red
            fig_p = px.scatter(
                df,
                x="Max Roll (rad)",
                y="Lap Time (s)",
                color="Source",
                color_discrete_map={"CarMaker": "blue", "AI_Surrogate": "red"},
                title="Speed vs. Stability"
            )
            st.plotly_chart(fig_p, use_container_width=True)
        else:
            st.info("No data available for Pareto plot.")

    st.markdown("---")

    # --- 4. GHOST REPLAY (COMPARISON) ---
    st.header("👻 Ghost Replay Analysis")
    
    if len(completed_trials) >= 2:
        c1, c2 = st.columns(2)
        
        # Sort trials by performance
        sorted_trials = sorted(completed_trials, key=lambda t: t.values[0])
        
        with c1:
            # Default to Best Run
            run_a_idx = 0 
            run_a_name = st.selectbox(
                "Select Run A (Green)", 
                [f"Run_{t.number:04d} ({t.values[0]:.4f}s)" for t in sorted_trials],
                index=run_a_idx
            )
            id_a = run_a_name.split(" ")[0] # Extract "Run_XXXX"

        with c2:
            # Default to Worst/First Run
            run_b_idx = len(sorted_trials) - 1
            run_b_name = st.selectbox(
                "Select Run B (Red - Ghost)", 
                [f"Run_{t.number:04d} ({t.values[0]:.4f}s)" for t in sorted_trials],
                index=run_b_idx
            )
            id_b = run_b_name.split(" ")[0]

        # Load Data
        df_a = load_run_data(id_a)
        df_b = load_run_data(id_b)

        if df_a is not None and df_b is not None:
            # --- PLOT 1: Velocity vs Distance ---
            st.subheader("Velocity Trace")
            fig_v = go.Figure()
            
            # X-Axis is 'Car.Road.sRoad' (Distance along track)
            # Y-Axis is 'Car.v' (Velocity in m/s -> convert to km/h usually)
            
            # Check if columns exist (CarMaker variable names)
            x_col = 'Car.Road.sRoad' if 'Car.Road.sRoad' in df_a.columns else df_a.index
            y_col = 'Car.v'
            
            if y_col in df_a.columns:
                # Add Ghost (Run B) first so it's in background
                fig_v.add_trace(go.Scatter(
                    x=df_b[x_col], y=df_b[y_col] * 3.6, 
                    mode='lines', name=f"{id_b} (Baseline)",
                    line=dict(color='red', width=2, dash='dot')
                ))
                # Add Best (Run A)
                fig_v.add_trace(go.Scatter(
                    x=df_a[x_col], y=df_a[y_col] * 3.6, 
                    mode='lines', name=f"{id_a} (Optimized)",
                    line=dict(color='#00CC96', width=3)
                ))
                
                fig_v.update_layout(
                    xaxis_title="Distance [m]", 
                    yaxis_title="Speed [km/h]",
                    hovermode="x unified",
                    height=500
                )
                st.plotly_chart(fig_v, use_container_width=True)
            else:
                st.error("Column 'Car.v' not found in parquet file.")

            # --- PLOT 2: G-G Diagram (Stability) ---
            st.subheader("G-G Diagram (Stability)")
            col_g1, col_g2 = st.columns(2)
            
            if 'Car.ax' in df_a.columns and 'Car.ay' in df_a.columns:
                # Lat G vs Long G
                fig_gg = go.Figure()
                
                fig_gg.add_trace(go.Scatter(
                    x=df_b['Car.ay'] / 9.81, y=df_b['Car.ax'] / 9.81,
                    mode='markers', name=id_b,
                    marker=dict(color='red', size=4, opacity=0.3)
                ))
                
                fig_gg.add_trace(go.Scatter(
                    x=df_a['Car.ay'] / 9.81, y=df_a['Car.ax'] / 9.81,
                    mode='markers', name=id_a,
                    marker=dict(color='green', size=4, opacity=0.5)
                ))
                
                fig_gg.update_layout(
                    xaxis_title="Lateral G [g]", 
                    yaxis_title="Longitudinal G [g]",
                    width=600, height=600,
                    xaxis=dict(range=[-3, 3]),
                    yaxis=dict(range=[-3, 3])
                )
                st.plotly_chart(fig_gg, use_container_width=True)
            else:
                st.warning("Acceleration data (Car.ax, Car.ay) missing.")

        else:
            # If data is missing (e.g., AI run has no parquet), warn gently
            st.info(f"Parquet data not available for comparison. (AI runs do not generate trace files).")

    st.markdown("---")
    
    # --- 5. PARAMETER IMPORTANCE ---
    st.header("🧠 Parameter Analysis")
    if len(completed_trials) > 5:
        try:
            # Parallel Coordinate Plot
            st.subheader("Parallel Coordinates (What makes a fast car?)")
            fig_par = optuna.visualization.plot_parallel_coordinate(study, target_name="Lap Time")
            st.plotly_chart(fig_par, use_container_width=True)
            
            # Importance Bar Chart
            st.subheader("Hyperparameter Importance")
            fig_imp = optuna.visualization.plot_param_importances(study, target_name="Lap Time")
            st.plotly_chart(fig_imp, use_container_width=True)
        except:
            st.warning("Not enough data for importance analysis yet.")
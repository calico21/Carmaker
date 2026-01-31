import streamlit as st
import optuna
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import logging

# Configuration
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
DB_URL = "sqlite:///" + os.path.join(PROJECT_ROOT, "optimization.db")
PARQUET_DIR = os.path.join(PROJECT_ROOT, "data", "parquet_store")

st.set_page_config(page_title="Sim Optimization Dashboard", layout="wide")

# --- Helper Functions ---
@st.cache_resource
def load_study(study_name):
    """Loads the Optuna study. Cached to prevent reloading on every interaction."""
    try:
        return optuna.load_study(study_name=study_name, storage=DB_URL)
    except Exception as e:
        st.error(f"Could not load study: {e}")
        return None

def get_trial_data(study):
    """Extracts trial data into a clean Pandas DataFrame."""
    df = study.trials_dataframe()
    # Clean up column names (remove 'params_', 'user_attrs_')
    df.columns = [col.replace("params_", "").replace("user_attrs_", "") for col in df.columns]
    # Create the 'Run_ID' to match our Parquet filenames (e.g., Run_0042)
    df["Run_ID"] = df["number"].apply(lambda x: f"Run_{x:04d}")
    return df

def load_time_series(run_id):
    """Loads the high-frequency signal data for a specific run."""
    file_path = os.path.join(PARQUET_DIR, f"{run_id}.parquet")
    if os.path.exists(file_path):
        return pd.read_parquet(file_path)
    return None

# --- Layout & Logic ---
st.title("🏎️ Black-Box Optimization Dashboard")

# 1. Sidebar: Study Selection
st.sidebar.header("Configuration")
# In a real app, you might list all available studies from the DB
study = load_study("Vehicle_Dynamics_Opt_v1")

if study:
    df_trials = get_trial_data(study)
    
    # Filter: Only show completed trials
    df_trials = df_trials[df_trials["state"] == "COMPLETE"]
    
    st.sidebar.metric("Total Trials", len(df_trials))
    if "value" in df_trials.columns:
        best_val = df_trials["value"].min()
        st.sidebar.metric("Best Cost", f"{best_val:.4f}")

    # --- Section A: Scalar Analysis (The "Optimization View") ---
    st.subheader("1. Optimization Landscape")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Scatter Plot: Parameter vs Objective
        # Detect numeric columns for dropdowns
        numeric_cols = df_trials.select_dtypes(include=['float', 'int']).columns.tolist()
        
        # User controls
        x_axis = st.selectbox("X Axis", numeric_cols, index=numeric_cols.index("number") if "number" in numeric_cols else 0)
        y_axis = st.selectbox("Y Axis (Cost)", numeric_cols, index=numeric_cols.index("value") if "value" in numeric_cols else 0)
        c_axis = st.selectbox("Color By", numeric_cols, index=numeric_cols.index("k_spring_f") if "k_spring_f" in numeric_cols else 0)

        fig_scatter = px.scatter(
            df_trials, 
            x=x_axis, 
            y=y_axis, 
            color=c_axis,
            hover_data=["Run_ID"],
            title=f"{y_axis} vs {x_axis}",
            template="plotly_dark"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col2:
        st.write("### Top 5 Runs")
        # Show top 5 sorted by cost (value)
        if "value" in df_trials.columns:
            top_5 = df_trials.sort_values("value").head(5)[["Run_ID", "value"] + [c for c in df_trials.columns if c not in ["Run_ID", "value", "state", "datetime_start", "datetime_complete"]]]
            st.dataframe(top_5, hide_index=True)

    # --- Section B: Time-Series Deep Dive (The "Physics View") ---
    st.markdown("---")
    st.subheader("2. Time-Series Trajectory Analysis")

    # Multi-Select to compare runs
    selected_runs = st.multiselect(
        "Select Runs to Compare (Select from dropdown or type 'Run_00XX')", 
        df_trials["Run_ID"].tolist(),
        default=df_trials.sort_values("value").head(2)["Run_ID"].tolist() if "value" in df_trials.columns else []
    )

    if selected_runs:
        ts_fig = go.Figure()
        
        # We need to know which signals are available. 
        # Load the first one to get columns.
        first_data = load_time_series(selected_runs[0])
        
        if first_data is not None:
            signals = first_data.select_dtypes(include=['float32', 'float64']).columns.tolist()
            selected_signal = st.selectbox("Signal to Plot", signals, index=0)

            for run_id in selected_runs:
                data = load_time_series(run_id)
                if data is not None and selected_signal in data.columns:
                    # Downsample for speed if needed (e.g., plot every 10th point)
                    ts_fig.add_trace(go.Scatter(
                        y=data[selected_signal],
                        mode='lines',
                        name=run_id
                    ))
                else:
                    st.warning(f"Data missing for {run_id}")

            ts_fig.update_layout(
                title=f"Comparison: {selected_signal}",
                xaxis_title="Time / Index",
                yaxis_title=selected_signal,
                template="plotly_dark"
            )
            st.plotly_chart(ts_fig, use_container_width=True)
        else:
            st.error("Could not load data for the selected run. Check Parquet store.")
    else:
        st.info("Select runs above to visualize time-series data.")

else:
    st.warning("No study found. Run the orchestrator first.")
import streamlit as st
import optuna
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import os
import sys
import glob

# --- CONFIGURATION ---
PAGE_TITLE = "FSAE OPTIMIZER"
BASE_OUTPUT_DIR = "Output"

st.set_page_config(
    page_title=PAGE_TITLE, 
    layout="wide", 
    page_icon="🏎️",
    initial_sidebar_state="expanded"
)

# --- RACE CONTROL THEME (CSS) ---
# This forces the text to be visible and gives a professional dark mode look
st.markdown("""
<style>
    /* Dark Theme Tweaks */
    .stApp {
        background-color: #0e1117;
    }
    .metric-card {
        background-color: #262730;
        border: 1px solid #464b5d;
        padding: 15px;
        border-radius: 8px;
        color: white;
    }
    h1, h2, h3 {
        color: #e0e0e0 !important;
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 700;
    }
    /* Metric Colors - Neon Green for Speed */
    [data-testid="stMetricValue"] {
        color: #00ff41 !important; 
        font-family: 'Courier New', monospace;
        font-weight: bold;
    }
    [data-testid="stMetricDelta"] svg {
        fill: #00ff41 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def get_campaigns():
    """Scans the Output directory for Campaign folders."""
    if not os.path.exists(BASE_OUTPUT_DIR):
        return []
    folders = glob.glob(os.path.join(BASE_OUTPUT_DIR, "Campaign_*"))
    folders.sort(key=os.path.getmtime, reverse=True)
    return [os.path.basename(f) for f in folders]

def load_study_data(db_path, selected_mode):
    """Loads specific study mode (Dynamics or Kinematics) to avoid NaN issues."""
    storage_url = f"sqlite:///{os.path.abspath(db_path)}"
    try:
        summaries = optuna.get_all_study_summaries(storage=storage_url)
        all_dfs = []
        
        for summary in summaries:
            # Filter: Only load the mode the user asked for
            if selected_mode.lower() not in summary.study_name.lower():
                continue
                
            study = optuna.load_study(study_name=summary.study_name, storage=storage_url)
            df = study.trials_dataframe()
            
            # Clean columns: "params_k_spring_f" -> "k_spring_f"
            df.columns = [col.replace("user_attrs_", "").replace("params_", "") for col in df.columns]
            
            # Filter for completed trials
            if "state" in df.columns:
                df = df[df["state"] == "COMPLETE"]
            
            # Ensure Lap Time exists
            if "value" in df.columns:
                df = df.dropna(subset=["value"])
                df.rename(columns={"value": "Lap Time"}, inplace=True)
                all_dfs.append(df)
        
        if not all_dfs:
            return pd.DataFrame()
            
        return pd.concat(all_dfs, ignore_index=True)

    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame()

# --- SIDEBAR ---
st.sidebar.title(f"🛠️ {PAGE_TITLE}")
st.sidebar.header("Data Source")

campaigns = get_campaigns()
if not campaigns:
    st.error("No Campaigns found. Run the optimizer!")
    st.stop()

selected_campaign = st.sidebar.selectbox("Select Campaign", campaigns)
db_path = os.path.join(BASE_OUTPUT_DIR, selected_campaign, "optimization.db")

st.sidebar.markdown("---")
st.sidebar.header("Filter Mode")
# Critical: Selecting mode prevents mixing "Springs" with "Hardpoints" which causes invisible graphs
mode = st.sidebar.radio("View Results For:", ["Dynamics", "Kinematics"])

# --- DATA LOADING ---
df = load_study_data(db_path, mode)

if df.empty:
    st.info(f"No completed data found for **{mode}** in this campaign.")
    st.stop()

# --- PRE-PROCESSING ---
# Get parameter columns (numeric only, excluding metadata)
meta_cols = ["number", "Lap Time", "datetime_start", "datetime_complete", "duration", "state", "system_attrs_nsga2:generation", "mass_penalty"]
param_cols = [c for c in df.columns if c not in meta_cols and df[c].dtype in [float, int]]

# --- DASHBOARD HEADER ---
best_run = df.loc[df["Lap Time"].idxmin()]
best_time = best_run["Lap Time"]
avg_time = df["Lap Time"].mean()

col1, col2, col3, col4 = st.columns(4)
col1.metric("🏆 Best Lap Time", f"{best_time:.3f} s", delta=f"-{(avg_time - best_time):.2f} s")
col2.metric("💾 Valid Trials", len(df))
col3.metric("🏎️ Simulated Dist", f"{len(df) * 1.2:.1f} km")

# Mass Penalty Display
mass_pen = best_run.get("mass_penalty", 0.0)
col4.metric("⚖️ Weight Penalty", f"{mass_pen:.1f} kg", delta_color="inverse")

# --- TABBED VIEW ---
tab_overview, tab_3d, tab_par, tab_data = st.tabs(["📉 Overview", "🌐 3D Map", "🕸️ Trade-offs", "📄 Data"])

with tab_overview:
    st.markdown("### Optimization Convergence")
    
    # 2D Scatter with Trendline
    # We force the template to 'plotly_dark' to ensure points are visible
    fig_conv = px.scatter(
        df, x="number", y="Lap Time",
        color="Lap Time",
        color_continuous_scale="Turbo_r", # Red=Slow, Blue=Fast
        title="Lap Time History (Lower is Better)",
        hover_data=param_cols
    )
    
    # Add "Best So Far" line
    df_sorted = df.sort_values("number")
    df_sorted["Best So Far"] = df_sorted["Lap Time"].cummin()
    fig_conv.add_trace(go.Scatter(
        x=df_sorted["number"], y=df_sorted["Best So Far"],
        mode='lines', name='Best Record',
        line=dict(color='white', width=2, dash='dash')
    ))
    
    fig_conv.update_layout(template="plotly_dark", height=450)
    st.plotly_chart(fig_conv, use_container_width=True)

with tab_3d:
    st.markdown("### Performance Landscape")
    
    if len(param_cols) >= 2:
        c1, c2 = st.columns([1, 4])
        with c1:
            x_ax = st.selectbox("X Axis", param_cols, index=0)
            y_ax = st.selectbox("Y Axis", param_cols, index=1)
        with c2:
            # 3D Plot
            fig_3d = px.scatter_3d(
                df, x=x_ax, y=y_ax, z="Lap Time",
                color="Lap Time",
                color_continuous_scale="Turbo_r",
                title=f"Interaction: {x_ax} vs {y_ax}",
                opacity=0.8
            )
            fig_3d.update_traces(marker=dict(size=6, line=dict(width=1, color='DarkSlateGrey')))
            fig_3d.update_layout(template="plotly_dark", height=600)
            st.plotly_chart(fig_3d, use_container_width=True)
    else:
        st.warning("Not enough parameters to plot 3D map.")

with tab_par:
    st.markdown("### Parameter Sensitivity (Parallel Coordinates)")
    st.caption("Drag the vertical axes to filter for the fastest laps.")
    
    # Filter to numeric only for this chart
    plot_cols = param_cols + ["Lap Time"]
    
    fig_par = px.parallel_coordinates(
        df[plot_cols],
        color="Lap Time",
        color_continuous_scale="Turbo_r",
    )
    fig_par.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig_par, use_container_width=True)

with tab_data:
    st.dataframe(df.sort_values("Lap Time"), use_container_width=True)
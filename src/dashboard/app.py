import streamlit as st
import optuna
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import os
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

# --- THEME ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="metric-container"] {
        background-color: #262730; 
        border: 1px solid #464b5d;
        border-radius: 10px;
        color: white;
    }
    p, h1, h2, h3, li { color: #e0e0e0 !important; }
    [data-testid="stMetricValue"] {
        color: #00ff41 !important;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def get_campaigns():
    if not os.path.exists(BASE_OUTPUT_DIR):
        return []
    folders = glob.glob(os.path.join(BASE_OUTPUT_DIR, "Campaign_*"))
    folders.sort(key=os.path.getmtime, reverse=True)
    return [os.path.basename(f) for f in folders]

def load_study_data(db_path, selected_mode):
    """
    NUCLEAR OPTION: Drops datetime columns entirely to prevent INT64 Overflow.
    """
    storage_url = f"sqlite:///{os.path.abspath(db_path)}"
    try:
        summaries = optuna.get_all_study_summaries(storage=storage_url)
        all_dfs = []
        
        for summary in summaries:
            if selected_mode.lower() not in summary.study_name.lower():
                continue
                
            study = optuna.load_study(study_name=summary.study_name, storage=storage_url)
            df = study.trials_dataframe()
            
            # 1. Clean Column Names
            df.columns = [col.replace("user_attrs_", "").replace("params_", "") for col in df.columns]
            
            # 2. Filter Completed
            if "state" in df.columns:
                df = df[df["state"] == "COMPLETE"]
            
            # 3. Rename Target
            if "value" in df.columns:
                df.rename(columns={"value": "Lap Time"}, inplace=True)
            
            # --- THE FIX: DELETE THE TIMESTAMPS ---
            # Do not try to convert them. Just drop them. 
            # These are the columns causing the 177007... overflow error.
            cols_to_drop = ["datetime_start", "datetime_complete", "duration"]
            df.drop(columns=[c for c in cols_to_drop if c in df.columns], inplace=True)
            
            # 4. Force everything else to Numeric
            # If it can't be a number, coerce it to NaN, then drop the column if it's all NaN
            df = df.apply(pd.to_numeric, errors='coerce')
            df = df.dropna(axis=1, how='all') # Drop columns that failed completely (like 'state' string)
            df = df.dropna(subset=["Lap Time"]) # Drop rows with no result
            
            all_dfs.append(df)
        
        if not all_dfs:
            return pd.DataFrame()
            
        return pd.concat(all_dfs, ignore_index=True)

    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame()

# --- SIDEBAR ---
st.sidebar.title(f"🛠️ {PAGE_TITLE}")
campaigns = get_campaigns()
if not campaigns:
    st.error("No Data Found.")
    st.stop()

selected_campaign = st.sidebar.selectbox("Select Campaign", campaigns)
db_path = os.path.join(BASE_OUTPUT_DIR, selected_campaign, "optimization.db")

st.sidebar.markdown("---")
mode = st.sidebar.radio("Optimization Mode", ["Dynamics", "Kinematics"])

# --- DATA LOADING ---
df = load_study_data(db_path, mode)

if df.empty:
    st.warning(f"⚠️ No completed trials found for **{mode}**.")
    st.stop()

# Determine Parameters (Anything that isn't metadata)
# We already dropped datetimes, so this is safer
meta_cols = ["number", "Lap Time", "mass_penalty", "state"]
param_cols = [c for c in df.columns if c not in meta_cols]

# --- HEADER ---
best_run = df.loc[df["Lap Time"].idxmin()]
c1, c2, c3, c4 = st.columns(4)
c1.metric("🏆 Fastest Lap", f"{best_run['Lap Time']:.3f} s")
c2.metric("💾 Trials", len(df))
c3.metric("🏎️ Distance", f"{len(df) * 1.2:.1f} km")
c4.metric("⚖️ Weight Pen.", f"{best_run.get('mass_penalty', 0):.1f} kg")

# --- DEBUGGER (Hidden) ---
with st.expander("Debug Data (Cleaned)"):
    st.dataframe(df.head())

# --- PLOTS ---
tab1, tab2, tab3 = st.tabs(["📉 Convergence", "🌐 3D Map", "🕸️ Trade-offs"])

with tab1:
    st.markdown("### Lap Time History")
    fig_conv = px.scatter(
        df, x="number", y="Lap Time",
        color="Lap Time",
        color_continuous_scale="Plasma_r",
        size_max=15,
        hover_data=param_cols
    )
    fig_conv.update_traces(marker=dict(size=12, line=dict(width=2, color='White')))
    fig_conv.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig_conv, use_container_width=True)

with tab2:
    st.markdown("### Parameter Interaction")
    if len(param_cols) >= 2:
        c1, c2 = st.columns([1, 4])
        with c1:
            x_ax = st.selectbox("X Axis", param_cols, index=0)
            y_ax = st.selectbox("Y Axis", param_cols, index=1)
        with c2:
            fig_3d = px.scatter_3d(
                df, x=x_ax, y=y_ax, z="Lap Time",
                color="Lap Time",
                color_continuous_scale="Plasma_r"
            )
            fig_3d.update_traces(marker=dict(size=6, line=dict(width=1, color='White')))
            fig_3d.update_layout(template="plotly_dark", height=600)
            st.plotly_chart(fig_3d, use_container_width=True)
    else:
        st.info("Not enough parameters for 3D plot.")

with tab3:
    st.markdown("### Sensitivity Analysis")
    if len(df) > 1:
        plot_cols = param_cols + ["Lap Time"]
        fig_par = px.parallel_coordinates(
            df, 
            color="Lap Time",
            dimensions=plot_cols,
            color_continuous_scale="Plasma_r"
        )
        fig_par.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_par, use_container_width=True)
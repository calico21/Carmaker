# Black-Box Simulation Optimization Framework

An industrial-grade architecture for automating vehicle dynamics optimization using **IPG CarMaker** and **Python**.

## 🏗 Architecture
This project uses a modular "Black Box" approach:
- **Core Orchestrator:** Manages the optimization loop (Optuna).
- **Service Layer:** Handles headless CarMaker execution and license management.
- **Data Layer:** Extracts binary results (.erg) and converts them to Parquet/SQL.
- **Dashboard:** Real-time TUI (Terminal UI) and Streamlit visualizations.

## 📂 Project Structure
```text
├── data/              # Stores SQL database and Parquet time-series
├── logs/              # Execution logs
├── src/               
│   ├── core/          # Master logic (Orchestrator, Resource Manager)
│   ├── database/      # Data parsers (ERG -> Parquet)
│   ├── dashboard/     # UI code (Terminal & Streamlit)
│   └── interface/     # IPG CarMaker interaction logic
├── templates/         # Master .testrun files
├── run_real_optimization.py   # PRODUCTION runner
└── run_with_tui.py            # MOCK runner (for testing logic)
import time
from rich.live import Live
from rich.layout import Layout
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
import optuna

class TerminalDashboard:
    """
    Adapts your previous 'Rich' UI to work with the new Architecture.
    """
    def __init__(self, study_name, n_trials, storage_url):
        self.study_name = study_name
        self.n_trials = n_trials
        self.storage_url = storage_url
        self.start_time = time.time()

    def make_layout(self):
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="leaderboard", ratio=1),
            Layout(name="recent", ratio=1)
        )
        return layout

    def generate_header(self, study):
        if not study:
            return Panel("Initializing Storage...", style="white on blue")
        
        best_val = study.best_value if len(study.trials) > 0 and study.best_trial else float('inf')
        total = len(study.trials)
        complete = len([t for t in study.trials if t.state.name == "COMPLETE"])
        
        # Sparkline logic from your code
        return Panel(
            f"[bold]Study:[/bold] {self.study_name} | [bold green]Best Cost: {best_val:.4f}[/bold green] | [bold]Completed:[/bold] {complete}/{self.n_trials}",
            style="white on black"
        )

    def generate_leaderboard(self, study):
        table = Table(title="🏆 Hall of Fame", expand=True, border_style="bright_yellow")
        table.add_column("#", style="dim", width=4)
        table.add_column("Cost", style="bold magenta", width=10)
        table.add_column("Parameters", style="white")

        if study:
            # Sort by value (minimize cost)
            completed = [t for t in study.trials if t.state.name == "COMPLETE" and t.value is not None]
            best = sorted(completed, key=lambda t: t.value)[:8]
            
            for i, t in enumerate(best):
                params_str = ", ".join([f"{k}={v:.2f}" for k, v in t.params.items()][:2]) # Show first 2 params
                style = "bold gold1" if i == 0 else "cyan"
                table.add_row(f"#{t.number}", f"{t.value:.4f}", params_str, style=style)
                
        return table

    def generate_recent(self, study):
        table = Table(title="⏱️ Recent Activity", expand=True, border_style="blue")
        table.add_column("Trial", width=6)
        table.add_column("Status", style="bold")
        table.add_column("Cost")

        if study:
            # Show last 8 trials
            recent = sorted(study.trials, key=lambda t: t.number, reverse=True)[:8]
            for t in recent:
                color = "green" if t.state.name == "COMPLETE" else "yellow"
                val = f"{t.value:.4f}" if t.value else "..."
                table.add_row(f"#{t.number}", f"[{color}]{t.state.name}[/{color}]", val)

        return table

    def run_monitor(self, stop_event):
        """
        Runs the UI loop in a separate thread/process so it doesn't block optimization.
        """
        layout = self.make_layout()
        
        # We need to reload the study object inside the loop to get fresh DB data
        
        with Live(layout, refresh_per_second=2, screen=True) as live:
            while not stop_event.is_set():
                try:
                    # Connect to DB to get latest stats (Read-Only)
                    study = optuna.load_study(study_name=self.study_name, storage=self.storage_url)
                    
                    layout["header"].update(self.generate_header(study))
                    layout["leaderboard"].update(self.generate_leaderboard(study))
                    layout["recent"].update(self.generate_recent(study))
                    
                except Exception:
                    pass # Ignore DB lock issues during reads
                
                time.sleep(0.5)
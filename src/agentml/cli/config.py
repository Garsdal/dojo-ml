"""CLI config commands — init and show configuration."""

from pathlib import Path

import typer
from rich.console import Console

console = Console()

config_app = typer.Typer(help="Configuration management")


@config_app.command("init")
def config_init() -> None:
    """Initialize a default configuration file."""
    config_dir = Path(".agentml")
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "config.yaml"

    if config_path.exists():
        console.print("  [yellow]Config already exists:[/yellow] .agentml/config.yaml")
        return

    default_config = """\
api:
  host: "127.0.0.1"
  port: 8000

llm:
  provider: "stub"
  model: "stub"

sandbox:
  timeout: 30.0

storage:
  base_dir: ".agentml"

tracking:
  backend: "file"             # "file" or "mlflow"
  enabled: true
  mlflow_tracking_uri: "file:./mlruns"
  mlflow_experiment_name: "agentml"

memory:
  backend: "local"
  search_limit: 10
"""
    config_path.write_text(default_config)
    console.print("  [green]✓[/green] Created .agentml/config.yaml")


@config_app.command("show")
def config_show() -> None:
    """Show the current configuration."""
    from agentml.config.settings import Settings

    settings = Settings.load()
    console.print_json(data=settings.model_dump(mode="json"))

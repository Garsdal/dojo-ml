"""Default configuration values."""

DEFAULTS = {
    "api": {
        "host": "127.0.0.1",
        "port": 8000,
    },
    "storage": {
        "base_dir": ".agentml",
    },
    "sandbox": {
        "timeout": 30.0,
    },
    "llm": {
        "provider": "stub",
        "model": "stub",
    },
    "tracking": {
        "backend": "file",
        "enabled": True,
        "mlflow_tracking_uri": "file:./mlruns",
        "mlflow_experiment_name": "agentml",
    },
    "memory": {
        "backend": "local",
        "search_limit": 10,
    },
    "frontend": {
        "enabled": True,
        "port": 5173,
    },
}

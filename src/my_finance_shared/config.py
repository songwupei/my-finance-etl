"""Shared project configuration — DB path, project root."""

from pathlib import Path

import yaml

_proj_dir = Path(__file__).resolve().parent.parent.parent


def get_db_path() -> str:
    """Resolve DuckDB path from Kedro parameters or fall back to default."""
    params_path = _proj_dir / "conf/base/parameters.yml"
    if params_path.exists():
        with open(params_path) as f:
            params = yaml.safe_load(f)
        return str(_proj_dir / params["database"]["path"])
    return str(_proj_dir / "data/warehouse/finance.duckdb")


DB_PATH = get_db_path()

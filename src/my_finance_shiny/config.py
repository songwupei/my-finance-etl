from pathlib import Path

import yaml

_proj_dir = Path(__file__).resolve().parent.parent.parent


def get_db_path():
    params_path = _proj_dir / "conf/base/parameters.yml"
    if params_path.exists():
        with open(params_path) as f:
            params = yaml.safe_load(f)
        return str(_proj_dir / params["database"]["path"])
    return str(_proj_dir / "data/warehouse/finance.duckdb")


DB_PATH = get_db_path()

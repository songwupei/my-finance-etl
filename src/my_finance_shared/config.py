"""Shared project configuration — DB path, project root."""

import os
from pathlib import Path

import yaml

# 仓库根目录。两台机器上位置不同，但都指向本仓库自己：
#   外网 /home/song/NutstoreFiles/projects/my-finance-etl
#   内网 /home/songwp/projects/my-finance-etl
_proj_dir = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = _proj_dir

# 同级项目（SionTiles / filepulse / PrettyDoc）所在目录。
# 两台机器上本仓库都直接位于 projects/ 下，因此从仓库位置推导即可；
# 也允许用环境变量 PROJECTS_ROOT 覆盖（start.sh 会导出）。
PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT") or _proj_dir.parent)

# 坚果云挂载的数据/代码区。这一层两台机器路径一致，
# 因此可以作为常量固定下来，需要时可用环境变量覆盖。
NUTSTORE_ROOT = Path(os.environ.get("NUTSTORE_ROOT", "/home/song/NutstoreFiles"))

# 报告输出目录（quarto 渲染产物）
GENERATED_REPORTS_DIR = _proj_dir / "generated_reports"

# quarto 渲染时需要挂到 PYTHONPATH 的工具库
PYBOX_DIR = NUTSTORE_ROOT / "2-Code/1-MyPython/pybox"


def get_db_path() -> str:
    """Resolve DuckDB path from Kedro parameters or fall back to default."""
    params_path = _proj_dir / "conf/base/parameters.yml"
    if params_path.exists():
        with open(params_path) as f:
            params = yaml.safe_load(f)
        return str(_proj_dir / params["database"]["path"])
    return str(_proj_dir / "data/warehouse/finance.duckdb")


DB_PATH = get_db_path()

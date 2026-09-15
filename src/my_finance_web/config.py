import re
import tomllib
from pathlib import Path

import yaml

from ..my_finance_shared import (
    DB_PATH,
    PROJECTS_ROOT,
    _proj_dir,
    get_db_path as _get_db_path,
)

# YAML mapping for /api/node_data validation
_yaml_mapping_path = _proj_dir / "conf/base/finance_mapping_standard.yaml"
_yaml_lookup = {}


def _init_yaml_lookup():
    if not _yaml_mapping_path.exists():
        return
    with open(_yaml_mapping_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for row in data.get("row_mappings", []):
        if row.get("匹配状态") == "MATCHED" and row.get("标准科目代码"):
            raw_key = re.sub(r'\s+', ' ', row.get("原始项目", "").strip())
            if raw_key and raw_key not in _yaml_lookup:
                _yaml_lookup[raw_key] = {
                    "code": row["标准科目代码"],
                    "path": row.get("标准科目路径", ""),
                    "category": row.get("报表分区", ""),
                }


_init_yaml_lookup()


def _get_email_config():
    params_path = _proj_dir / "conf/base/parameters.yml"
    if params_path.exists():
        with open(params_path) as f:
            params = yaml.safe_load(f)
        return params.get("email", {})
    return {}


_QUARTO_PDF = PROJECTS_ROOT / "PrettyDoc/_output/reports/SiKuReport/daily_report/daily_report_account-gb.pdf"

_TREASURY_CONFIG = PROJECTS_ROOT / "filepulse/config_treasury.toml"


def _get_send_script() -> Path:
    """从 filepulse config_treasury.toml 读取 on_after_process 路径。"""
    if _TREASURY_CONFIG.exists():
        with open(_TREASURY_CONFIG, "rb") as f:
            cfg = tomllib.load(f)
        for entry in cfg.get("archives", []):
            if entry.get("name") == "siku_account" and entry.get("on_after_process"):
                return Path(entry["on_after_process"])
    # fallback 路径
    return PROJECTS_ROOT / "filepulse/hooks/treasury_daily.sh"


_SEND_SCRIPT = _get_send_script()

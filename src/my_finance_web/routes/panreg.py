"""穿透监管报告路由 — 支持按日期存档、多版本可选。"""

import re
from pathlib import Path

from flask import Blueprint, abort, send_file

from ..config import _proj_dir

panreg_bp = Blueprint("panreg", __name__)

REPORT_DIR = _proj_dir / "data/01_raw"


def _find_report(prefix: str, date: str | None = None) -> Path | None:
    """查找指定日期的报告文件。

    Args:
        prefix: 文件名前缀，如 "account_PanReg_report"
        date: 日期 YYYY-MM，为 None 则取最新（无日期后缀的默认文件）

    Returns:
        文件 Path，未找到返回 None
    """
    if date:
        path = REPORT_DIR / f"{prefix}_{date}.html"
        return path if path.exists() else None
    else:
        # 最新：优先取无后缀默认文件，否则取日期后缀文件中最新的
        default = REPORT_DIR / f"{prefix}.html"
        if default.exists():
            return default
        # 查找带日期后缀的最新文件
        pattern = re.compile(rf"{re.escape(prefix)}_(\d{{4}}-\d{{2}})\.html$")
        candidates = []
        for f in REPORT_DIR.glob(f"{prefix}_*.html"):
            if pattern.match(f.name):
                candidates.append(f)
        if candidates:
            return sorted(candidates, reverse=True)[0]
        return None


def _list_dates(prefix: str) -> list[str]:
    """列出某前缀报告的全部可用日期。"""
    pattern = re.compile(rf"{re.escape(prefix)}_(\d{{4}}-\d{{2}})\.html$")
    dates = []
    for f in REPORT_DIR.glob(f"{prefix}_*.html"):
        m = pattern.match(f.name)
        if m:
            dates.append(m.group(1))
    return sorted(dates, reverse=True)


# ── 逃逸账户检测报告 ──
@panreg_bp.route("/panreg-report")
@panreg_bp.route("/panreg-report/<path:filename>")
def panreg_report(filename: str | None = None):
    if filename:
        # 指定文件名：account_PanReg_report_2026-07.html
        path = REPORT_DIR / filename
    else:
        # 无参数：取最新
        path = _find_report("account_PanReg_report")
    if path is None or not path.exists():
        abort(404)
    return send_file(str(path))


# ── 账户数量异常检测报告 ──
@panreg_bp.route("/panreg-report1")
@panreg_bp.route("/panreg-report1/<path:filename>")
def panreg_report1(filename: str | None = None):
    if filename:
        path = REPORT_DIR / filename
    else:
        path = _find_report("accountpro_PanReg_report")
    if path is None or not path.exists():
        abort(404)
    return send_file(str(path))


# ── 报告日期列表 API ──
@panreg_bp.route("/panreg-dates")
def panreg_dates():
    """返回可用报告日期列表（JSON）。"""
    import json
    from flask import Response

    escape_dates = _list_dates("account_PanReg_report")
    anomaly_dates = _list_dates("accountpro_PanReg_report")
    all_dates = sorted(set(escape_dates + anomaly_dates), reverse=True)

    return Response(
        json.dumps({"dates": all_dates, "escape": escape_dates, "anomaly": anomaly_dates},
                   ensure_ascii=False),
        mimetype="application/json",
    )

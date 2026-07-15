"""穿透监管 — 列出所有 PanReg 报告链接。"""

import re
from pathlib import Path

from shiny import ui

from ..config import _proj_dir

REPORT_DIR = _proj_dir / "data/01_raw"
FLASK_BASE = "http://localhost:5001"

_REPORT_TYPES = [
    ("account_PanReg_report", "panreg-report", "逃逸账户检测报告"),
    ("accountpro_PanReg_report", "panreg-report1", "账户数量异常检测报告"),
]


def _scan():
    """扫描报告目录，返回 [(label, url), ...] 列表。"""
    links = []
    for prefix, route, title in _REPORT_TYPES:
        pattern = re.compile(rf"{re.escape(prefix)}_(\d{{4}}-\d{{2}})\.html$")
        dated = []
        for f in sorted(REPORT_DIR.glob(f"{prefix}_*.html")):
            m = pattern.match(f.name)
            if m:
                dated.append((m.group(1), f.name))
        if dated:
            for d, fn in dated:
                links.append((f"{title}（{d}）", f"{FLASK_BASE}/{route}/{fn}"))
        else:
            # fallback: 无日期的最新文件
            default = REPORT_DIR / f"{prefix}.html"
            if default.exists():
                links.append((title, f"{FLASK_BASE}/{route}"))
    return links


_links = _scan()


def page():
    if not _links:
        return ui.card(
            ui.card_header("穿透监管报告"),
            ui.markdown("暂无可用报告。请先生成 PanReg 报告。"),
        )

    cards = []
    for label, url in _links:
        cards.append(
            ui.card(
                ui.card_header(label),
                ui.tags.a(
                    "打开完整报告（新标签页）",
                    href=url,
                    target="_blank",
                    style="font-weight: bold; font-size: 16px;",
                ),
            )
        )

    return ui.TagList(*cards)

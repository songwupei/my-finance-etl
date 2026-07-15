"""FinForge-style Shiny Web 应用。

启动:
    shiny run --host 0.0.0.0 --port 8000 src.my_finance_shiny.app
"""

from __future__ import annotations

from shiny import App, ui
from shiny.ui import Theme

# ── Pages ──
from .pages import (
    home, smart_query, china_map, enterprise_map,
    monitor, account_map, account_detail, panreg,
    balance_overview, balance_subgroup, balance_bank,
    balance_geo, balance_cross,
)


def _app_ui() -> ui.Tag:
    """主界面 — 双层导航。"""
    return ui.page_navbar(
        # ── 顶层导航 ──
        ui.nav_panel("🏠 首页", home.page()),
        ui.nav_panel("🤖 智能查询", smart_query.page()),
        ui.nav_panel("🗺️ 资产地图", china_map.page()),
        ui.nav_panel("📍 资金地图", enterprise_map.page()),

        # ── 穿透监控 ──
        ui.nav_menu(
            "🔍 穿透监控",
            ui.nav_panel("监控大屏", monitor.page()),
            ui.nav_panel("账户地图", account_map.page()),
        ),

        # ── 账户分析 ──
        ui.nav_menu(
            "📊 账户分析",
            ui.nav_panel("账户明细", account_detail.page()),
            ui.nav_panel("监管报告", panreg.page()),
        ),

        # ── 余额统计 ──
        ui.nav_menu(
            "💰 余额统计",
            ui.nav_panel("整体概况", balance_overview.page()),
            ui.nav_panel("子集团维度", balance_subgroup.page()),
            ui.nav_panel("银行维度", balance_bank.page()),
            ui.nav_panel("地理维度", balance_geo.page()),
            ui.nav_panel("交叉分析", balance_cross.page()),
        ),

        title="FinForge — AI 财务监管平台",
        id="navbar",
        sidebar=None,
        header=ui.input_dark_mode(mode="light"),
        theme=Theme(preset="flatly"),
    )


def server(input, output, session):
    """Shiny server 函数 — 注册所有页面 server。"""
    account_detail.server(input, output, session)
    account_map.server(input, output, session)
    monitor.server(input, output, session)
    china_map.server(input, output, session)
    balance_overview.server(input, output, session)
    balance_subgroup.server(input, output, session)
    balance_bank.server(input, output, session)
    balance_geo.server(input, output, session)
    balance_cross.server(input, output, session)
    smart_query.server(input, output, session)


app = App(_app_ui(), server)


# ── CLI entry ──

def main():
    """启动 Shiny 服务。"""
    import sys
    import subprocess
    port = "8000"
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = sys.argv[1]
    subprocess.run([
        "shiny", "run",
        "--host", "0.0.0.0",
        "--port", port,
        "src.my_finance_shiny.app",
    ])

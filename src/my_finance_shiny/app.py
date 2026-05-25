"""Shiny dashboard app — 14-page financial data visualization platform."""
from shiny import App, ui
from shiny.ui import Theme

from .pages import (
    home,
    panreg,
    account_detail,
    account_map,
    monitor,
    china_map,
    balance_overview,
    balance_subgroup,
    balance_bank,
    balance_geo,
    balance_cross,
    smart_query,
)
from .components.fallback import fallback_card


def _placeholder_ui(name: str):
    return fallback_card(f"{name} — 内容待开发")


app_ui = ui.page_navbar(
    # ---- Top level ----
    ui.nav_panel("首页", home.home_ui()),
    ui.nav_panel("智能查询", smart_query.smart_query_ui()),
    ui.nav_panel("地理分布", china_map.china_map_ui()),
    # ---- 穿透监控 ----
    ui.nav_menu(
        "穿透监控",
        ui.nav_panel("监控大屏", monitor.monitor_ui()),
        ui.nav_panel("账户地图", account_map.account_map_ui()),
    ),
    # ---- 账户分析 ----
    ui.nav_menu(
        "账户分析",
        ui.nav_panel("关系分析", _placeholder_ui("关系分析")),
        ui.nav_panel("账户明细表", account_detail.account_detail_ui()),
        ui.nav_panel("概览", _placeholder_ui("概览")),
        ui.nav_panel("穿透监管", panreg.panreg_ui()),
    ),
    # ---- 余额统计分析 ----
    ui.nav_menu(
        "余额统计分析",
        ui.nav_panel("整体情况", balance_overview.balance_overview_ui()),
        ui.nav_panel("子集团维度", balance_subgroup.balance_subgroup_ui()),
        ui.nav_panel("所属银行维度", balance_bank.balance_bank_ui()),
        ui.nav_panel("地理维度", balance_geo.balance_geo_ui()),
        ui.nav_panel("交叉维度", balance_cross.balance_cross_ui()),
    ),
    title="财务数据分析平台",
    id="main_nav",
    theme=Theme(preset="flatly"),
)


def server(input, output, session):
    account_detail.account_detail_server(input, output, session)
    account_map.account_map_server(input, output, session)
    monitor.monitor_server(input, output, session)
    china_map.china_map_server(input, output, session)
    balance_overview.balance_overview_server(input, output, session)
    balance_subgroup.balance_subgroup_server(input, output, session)
    balance_bank.balance_bank_server(input, output, session)
    balance_geo.balance_geo_server(input, output, session)
    balance_cross.balance_cross_server(input, output, session)
    smart_query.smart_query_server(input, output, session)


app = App(app_ui, server)

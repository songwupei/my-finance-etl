"""余额统计分析 — 整体情况。"""

from shiny import reactive, render, ui
from shinywidgets import render_plotly, output_widget

from ..data import balance_base, balance_tiers, balance_by_subgroup, balance_period
from ..figures.balance import (
    balance_overview_histogram, balance_overview_tier_pie,
    balance_overview_top10_bar,
)
from ..components.kpi_card import kpi_card


def page():
    return ui.TagList(
        ui.output_ui("overview_kpi"),
        ui.card(ui.card_header("余额分布"), output_widget("overview_histogram", fill=True)),
        ui.card(ui.card_header("余额层级"), output_widget("overview_tier_pie", fill=True)),
        ui.card(ui.card_header("Top 10 子集团"), output_widget("overview_top10_bar", fill=True)),
    )


def server(input, output, session):
    @reactive.calc
    def _base():
        return balance_base.clone()

    @reactive.calc
    def _tier():
        return balance_tiers.clone()

    @reactive.calc
    def _top10():
        return balance_by_subgroup.head(10).clone() if balance_by_subgroup.height > 0 else balance_by_subgroup.clone()

    @render.ui
    def overview_kpi():
        df = _base()
        if df.height == 0: return None
        return kpi_card(f"账户余额总览（截至 {balance_period}）", {
            "总余额": f"{df['balance_amount'].sum():,.0f} 元",
            "账户总数": f"{df['account_id'].n_unique():,}",
            "子集团数": f"{df['sub_group_name'].n_unique()}",
            "中位数余额": f"{df['balance_amount'].median():,.0f} 元",
        })

    @render_plotly
    def overview_histogram():
        df = _base()
        if df.height == 0: return None
        return balance_overview_histogram(df)

    @render_plotly
    def overview_tier_pie():
        df = _tier()
        if df.height == 0: return None
        return balance_overview_tier_pie(df)

    @render_plotly
    def overview_top10_bar():
        df = _top10()
        if df.height == 0: return None
        return balance_overview_top10_bar(df)

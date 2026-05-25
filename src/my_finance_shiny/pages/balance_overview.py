"""余额统计分析 — 整体情况."""
from shiny import reactive, render, ui
from shinywidgets import render_plotly, output_widget

from ..data import _balance_base_data, _tier_data, _top10_sg
from ..figures.balance import (
    balance_overview_histogram,
    balance_overview_tier_pie,
    balance_overview_top10_bar,
)
from ..components.kpi_card import kpi_card


def balance_overview_ui():
    return ui.TagList(
        ui.output_ui("overview_kpi"),
        ui.card(
            ui.card_header("余额分布"),
            output_widget("overview_histogram"),
        ),
        ui.card(
            ui.card_header("余额层级"),
            output_widget("overview_tier_pie"),
        ),
        ui.card(
            ui.card_header("Top 10 子集团"),
            output_widget("overview_top10_bar"),
        ),
    )


def balance_overview_server(input, output, session):
    @reactive.calc
    def _base():
        return _balance_base_data.clone()

    @reactive.calc
    def _tier():
        return _tier_data.clone()

    @reactive.calc
    def _top10():
        return _top10_sg.clone()

    @render.ui
    def overview_kpi():
        df = _base()
        if df.height == 0:
            return None
        total_bal = df["balance_amount"].sum()
        total_accts = df["account_id"].n_unique()
        total_sg = df["sub_group_name"].n_unique()
        median_bal = df["balance_amount"].median()
        return kpi_card("账户余额总览", {
            "总余额": f"{total_bal:,.0f} 元",
            "账户总数": f"{total_accts:,}",
            "子集团数": f"{total_sg}",
            "中位数余额": f"{median_bal:,.0f} 元",
        })

    @render_plotly
    def overview_histogram():
        df = _base()
        if df.height == 0:
            return None
        return balance_overview_histogram(df)

    @render_plotly
    def overview_tier_pie():
        df = _tier()
        if df.height == 0:
            return None
        return balance_overview_tier_pie(df)

    @render_plotly
    def overview_top10_bar():
        df = _top10()
        if df.height == 0:
            return None
        return balance_overview_top10_bar(df)

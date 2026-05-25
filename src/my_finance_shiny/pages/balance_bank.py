"""余额统计分析 — 所属银行维度."""
from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import _bank_data_for_chart, _bank_usage_pivot
from ..figures.balance import bank_bar, bank_pie, bank_usage_stacked


def balance_bank_ui():
    return ui.TagList(
        ui.card(
            ui.card_header("银行余额排名"),
            output_widget("bank_bar"),
        ),
        ui.card(
            ui.card_header("银行余额占比"),
            output_widget("bank_pie"),
        ),
        ui.card(
            ui.card_header("银行 × 账户用途"),
            output_widget("bank_usage_stacked"),
        ),
    )


def balance_bank_server(input, output, session):
    @reactive.calc
    def _bank_data():
        return _bank_data_for_chart.clone()

    @reactive.calc
    def _pivot():
        return _bank_usage_pivot.clone()

    @render_plotly
    def bank_bar():
        df = _bank_data()
        if df.height == 0:
            return None
        return bank_bar(df)

    @render_plotly
    def bank_pie():
        df = _bank_data()
        if df.height == 0:
            return None
        return bank_pie(df.head(10))

    @render_plotly
    def bank_usage_stacked():
        df = _pivot()
        if df.height == 0:
            return None
        return bank_usage_stacked(df)

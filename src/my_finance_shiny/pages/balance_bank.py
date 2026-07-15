"""余额统计分析 — 所属银行维度。"""

from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import balance_by_bank, bank_usage_pivot
from ..figures.balance import bank_bar, bank_pie, bank_usage_stacked


def page():
    return ui.TagList(
        ui.card(ui.card_header("银行余额排名"), output_widget("bank_bar_plot", fill=True)),
        ui.card(ui.card_header("银行余额占比"), output_widget("bank_pie_plot", fill=True)),
        ui.card(ui.card_header("银行 × 账户用途"), output_widget("bank_usage_stacked_plot", fill=True)),
    )


def server(input, output, session):
    @reactive.calc
    def _bank_data():
        df = balance_by_bank.clone()
        return df.filter(df["financial_institution"] != "财务公司") if df.height > 0 else df

    @reactive.calc
    def _pivot():
        return bank_usage_pivot.clone()

    @render_plotly
    def bank_bar_plot():
        df = _bank_data()
        if df.height == 0: return None
        return bank_bar(df)

    @render_plotly
    def bank_pie_plot():
        df = _bank_data()
        if df.height == 0: return None
        return bank_pie(df.head(10))

    @render_plotly
    def bank_usage_stacked_plot():
        df = _pivot()
        if df.height == 0: return None
        return bank_usage_stacked(df)

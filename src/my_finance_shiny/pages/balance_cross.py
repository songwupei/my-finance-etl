"""余额统计分析 — 交叉维度."""
from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import _cross_data, _box_data, _top8_banks
from ..figures.balance import cross_scatter, cross_box


def balance_cross_ui():
    return ui.TagList(
        ui.card(
            ui.card_header("账户数 vs 平均余额"),
            output_widget("cross_scatter"),
        ),
        ui.card(
            ui.card_header("余额分布 by 银行"),
            output_widget("cross_box"),
        ),
    )


def balance_cross_server(input, output, session):
    @reactive.calc
    def _cross():
        return _cross_data.clone()

    @reactive.calc
    def _box():
        return _box_data.clone()

    @reactive.calc
    def _banks():
        return list(_top8_banks)

    @render_plotly
    def cross_scatter():
        df = _cross()
        if df.height == 0:
            return None
        return cross_scatter(df)

    @render_plotly
    def cross_box():
        df = _box()
        banks = _banks()
        if df.height == 0 or len(banks) == 0:
            return None
        return cross_box(df, banks)

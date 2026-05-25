"""余额统计分析 — 子集团维度."""
from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import _balance_by_subgroup, _top20_sg
from ..figures.balance import subgroup_bar, subgroup_treemap


def balance_subgroup_ui():
    return ui.TagList(
        ui.card(
            ui.card_header("Top 20 子集团余额排名"),
            output_widget("subgroup_bar"),
        ),
        ui.card(
            ui.card_header("子集团余额占比"),
            output_widget("subgroup_treemap"),
        ),
    )


def balance_subgroup_server(input, output, session):
    @reactive.calc
    def _top20():
        return _top20_sg.clone()

    @reactive.calc
    def _by_sg():
        return _balance_by_subgroup.clone()

    @render_plotly
    def subgroup_bar():
        df = _top20()
        if df.height == 0:
            return None
        return subgroup_bar(df)

    @render_plotly
    def subgroup_treemap():
        df = _by_sg()
        if df.height == 0:
            return None
        head30 = df.head(30)
        return subgroup_treemap(head30)

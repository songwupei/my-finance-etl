"""余额统计分析 — 子集团维度。"""

from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import balance_by_subgroup
from ..figures.balance import subgroup_bar, subgroup_treemap


def page():
    return ui.TagList(
        ui.card(ui.card_header("Top 20 子集团余额排名"), output_widget("subgroup_bar_plot", fill=True)),
        ui.card(ui.card_header("子集团余额占比"), output_widget("subgroup_treemap_plot", fill=True)),
    )


def server(input, output, session):
    @reactive.calc
    def _top20():
        return balance_by_subgroup.head(20).clone() if balance_by_subgroup.height > 0 else balance_by_subgroup.clone()

    @reactive.calc
    def _by_sg():
        return balance_by_subgroup.clone()

    @render_plotly
    def subgroup_bar_plot():
        df = _top20()
        if df.height == 0: return None
        return subgroup_bar(df)

    @render_plotly
    def subgroup_treemap_plot():
        df = _by_sg()
        if df.height == 0: return None
        return subgroup_treemap(df.head(30))

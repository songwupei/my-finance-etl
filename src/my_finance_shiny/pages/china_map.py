"""地理分布 — China geo scattermap (全屏)."""

from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import china_geo
from ..figures.map import geo_map


def page():
    return ui.div(
        output_widget("china_map_plot", fill=True, height="100%"),
        style="height: calc(100vh - 58px); width: 100%; margin: 0; padding: 0;",
    )


def server(input, output, session):
    @reactive.calc
    def _data():
        return china_geo.clone()

    @render_plotly
    def china_map_plot():
        df = _data()
        if df.height == 0:
            return None
        fig = geo_map(df)
        fig.update_layout(
            autosize=True,
            height=None,
            margin=dict(l=0, r=0, t=0, b=0),
        )
        return fig

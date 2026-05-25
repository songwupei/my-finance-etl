"""地理分布 — China geo scattermap."""
from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import _vizro_geo_data
from ..figures.map import geo_map


def china_map_ui():
    return ui.card(
        ui.card_header("成员单位地理分布"),
        output_widget("china_map_plot"),
    )


def china_map_server(input, output, session):
    @reactive.calc
    def _data():
        return _vizro_geo_data.clone()

    @render_plotly
    def china_map_plot():
        df = _data()
        if df.height == 0:
            return None
        return geo_map(df)

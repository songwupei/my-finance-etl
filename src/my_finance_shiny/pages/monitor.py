"""穿透监控大屏 — 2 Plotly figures."""
from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import _vizro_df1
from ..figures.home import asset_liability_bubble, leverage_vs_accounts


def monitor_ui():
    return ui.TagList(
        ui.card(
            ui.card_header("资产负债结构气泡图"),
            output_widget("monitor_bubble"),
        ),
        ui.card(
            ui.card_header("杠杆率 vs 账户规模"),
            output_widget("monitor_leverage"),
        ),
    )


def monitor_server(input, output, session):
    @reactive.calc
    def _data():
        return _vizro_df1.clone()

    @render_plotly
    def monitor_bubble():
        df = _data()
        if df.height == 0:
            return None
        return asset_liability_bubble(df)

    @render_plotly
    def monitor_leverage():
        df = _data()
        if df.height == 0:
            return None
        return leverage_vs_accounts(df)

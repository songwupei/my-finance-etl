"""余额统计分析 — 地理维度."""
from shiny import reactive, render, ui
from shinywidgets import render_plotly, output_widget

from ..data import _balance_base_data, _top20_city
from ..figures.balance import city_bar
from ..components.kpi_card import kpi_card


def balance_geo_ui():
    return ui.TagList(
        ui.output_ui("geo_kpi"),
        ui.card(
            ui.card_header("Top 20 城市余额排名"),
            output_widget("geo_city_bar"),
        ),
    )


def balance_geo_server(input, output, session):
    @reactive.calc
    def _base():
        return _balance_base_data.clone()

    @reactive.calc
    def _top20():
        return _top20_city.clone()

    @render.ui
    def geo_kpi():
        df = _base()
        if df.height == 0:
            return None
        city_pct = df["bank_city"].ne("未知城市").mean() * 100
        return kpi_card("地理覆盖", {
            "已定位城市账户占比": f"{city_pct:.1f}%",
        })

    @render_plotly
    def geo_city_bar():
        df = _top20()
        if df.height == 0:
            return None
        return city_bar(df)

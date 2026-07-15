"""余额统计分析 — 地理维度。"""

from shiny import reactive, render, ui
from shinywidgets import render_plotly, output_widget

from ..data import balance_base, balance_by_city
from ..figures.balance import city_bar
from ..components.kpi_card import kpi_card


def page():
    return ui.TagList(
        ui.output_ui("geo_kpi"),
        ui.card(ui.card_header("Top 20 城市余额排名"), output_widget("geo_city_bar", fill=True)),
    )


def server(input, output, session):
    @reactive.calc
    def _base():
        return balance_base.clone()

    @reactive.calc
    def _top20():
        city = balance_by_city.clone()
        known = city.filter(city["bank_city"] != "未知城市") if city.height > 0 else city
        return known.head(20) if known.height > 0 else known

    @render.ui
    def geo_kpi():
        df = _base()
        if df.height == 0: return None
        pct = df["bank_city"].ne("未知城市").mean() * 100
        return kpi_card("地理覆盖", {"已定位城市账户占比": f"{pct:.1f}%"})

    @render_plotly
    def geo_city_bar():
        df = _top20()
        if df.height == 0: return None
        return city_bar(df)

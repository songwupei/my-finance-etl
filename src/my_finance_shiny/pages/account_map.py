"""账户地图 — 银行账户地理分布 + 5 维级联筛选。"""

import polars as pl
from shiny import reactive, render, ui
from shinywidgets import render_plotly, output_widget

from ..data import bank_map_account
from ..figures.account_map import bank_account_map


def page():
    return ui.TagList(
        ui.card(
            ui.card_header("筛选条件"),
            ui.layout_column_wrap(
                ui.input_selectize("prov_filter", "省份", choices=[], multiple=True, width="100%"),
                ui.input_selectize("city_filter", "城市", choices=[], multiple=True, width="100%"),
                ui.input_selectize("bank_filter", "所属银行", choices=[], multiple=True, width="100%"),
                ui.input_selectize("sg_filter", "子集团", choices=[], multiple=True, width="100%"),
                ui.input_selectize("branch_filter", "开户网点", choices=[], multiple=True, width="100%"),
                width="20%",
            ),
        ),
        ui.card(
            ui.card_header("银行账户地理分布"),
            output_widget("account_map_plot", fill=True),
        ),
        ui.card(
            ui.card_header("点击气泡筛选此表"),
            ui.output_data_frame("account_map_table"),
        ),
    )


def server(input, output, session):
    @reactive.calc
    def prov():
        return input.prov_filter() or []

    @reactive.calc
    def city():
        return input.city_filter() or []

    @reactive.calc
    def bank():
        return input.bank_filter() or []

    @reactive.calc
    def sg():
        return input.sg_filter() or []

    @reactive.calc
    def branch():
        return input.branch_filter() or []

    @reactive.calc
    def _master():
        return bank_map_account.clone()

    @reactive.calc
    def filtered_data():
        df = _master()
        if df.height == 0:
            return df
        for col, vals in [
            ("province", prov()), ("bank_city", city()),
            ("financial_institution", bank()), ("sub_group_name", sg()),
            ("branch_name", branch()),
        ]:
            if vals:
                df = df.filter(pl.col(col).is_in(vals))
        return df

    @reactive.effect
    def _init_options():
        df = _master()
        if df.height == 0:
            return
        for col, wid in [
            ("province", "prov_filter"), ("bank_city", "city_filter"),
            ("financial_institution", "bank_filter"), ("sub_group_name", "sg_filter"),
            ("branch_name", "branch_filter"),
        ]:
            choices = sorted(df[col].unique().to_list())
            ui.update_selectize(wid, choices=choices)

    @reactive.effect
    @reactive.event(prov, bank, sg)
    def update_city():
        df = _master()
        if df.height == 0:
            return
        for col, vals in [("province", prov()), ("financial_institution", bank()), ("sub_group_name", sg())]:
            if vals:
                df = df.filter(pl.col(col).is_in(vals))
        choices = sorted(df["bank_city"].unique().to_list())
        ui.update_selectize("city_filter", choices=choices, selected=city())

    @reactive.effect
    @reactive.event(prov, city, sg)
    def update_bank():
        df = _master()
        if df.height == 0:
            return
        for col, vals in [("province", prov()), ("bank_city", city()), ("sub_group_name", sg())]:
            if vals:
                df = df.filter(pl.col(col).is_in(vals))
        choices = sorted(df["financial_institution"].unique().to_list())
        ui.update_selectize("bank_filter", choices=choices, selected=bank())

    @reactive.effect
    @reactive.event(prov, city, bank)
    def update_sg():
        df = _master()
        if df.height == 0:
            return
        for col, vals in [("province", prov()), ("bank_city", city()), ("financial_institution", bank())]:
            if vals:
                df = df.filter(pl.col(col).is_in(vals))
        choices = sorted(df["sub_group_name"].unique().to_list())
        ui.update_selectize("sg_filter", choices=choices, selected=sg())

    @reactive.effect
    @reactive.event(prov, city, bank, sg)
    def update_branch():
        df = _master()
        if df.height == 0:
            return
        for col, vals in [("province", prov()), ("bank_city", city()),
                          ("financial_institution", bank()), ("sub_group_name", sg())]:
            if vals:
                df = df.filter(pl.col(col).is_in(vals))
        choices = sorted(df["branch_name"].unique().to_list())
        ui.update_selectize("branch_filter", choices=choices, selected=branch())

    @render_plotly
    def account_map_plot():
        df = filtered_data()
        if df.height == 0:
            return None
        return bank_account_map(df)

    @render.data_frame
    def account_map_table():
        df = filtered_data()
        if df.height == 0:
            return None
        display = df.select([
            "sub_group_name", "account_name", "financial_institution",
            "bank_city", "province", "branch_name", "balance_amount",
        ]).sort("balance_amount", descending=True)
        return render.DataGrid(display.to_pandas(), height=400, filters=True)

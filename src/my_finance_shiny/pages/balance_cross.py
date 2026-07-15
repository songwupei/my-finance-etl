"""余额统计分析 — 交叉维度。"""

from shiny import reactive, ui
from shinywidgets import render_plotly, output_widget

from ..data import balance_by_subgroup, balance_by_bank, balance_base
from ..figures.balance import cross_scatter, cross_box


def page():
    return ui.TagList(
        ui.card(ui.card_header("账户数 vs 平均余额"), output_widget("cross_scatter_plot", fill=True)),
        ui.card(ui.card_header("余额分布 by 银行"), output_widget("cross_box_plot", fill=True)),
    )


def server(input, output, session):
    @reactive.calc
    def _cross():
        df = balance_by_subgroup.clone()
        if df.height == 0: return df
        return df.with_columns(
            df["avg_balance"].clip(1, None).log10().alias("log10_avg_balance"),
            df["account_count"].clip(1, None).log10().alias("log10_account_count"),
            (df["total_balance"].clip(1, None).log10() * 4).alias("size_scaled"),
        )

    @reactive.calc
    def _box():
        bank = balance_by_bank.clone()
        if bank.height == 0: return (bank, [])
        top8 = bank.head(8)["financial_institution"].to_list()
        base = balance_base.clone()
        if base.height == 0: return (base, top8)
        return (base.filter(base["financial_institution"].is_in(top8)), top8)

    @render_plotly
    def cross_scatter_plot():
        df = _cross()
        if df.height == 0: return None
        return cross_scatter(df)

    @render_plotly
    def cross_box_plot():
        df, banks = _box()
        if df.height == 0 or len(banks) == 0: return None
        return cross_box(df, banks)

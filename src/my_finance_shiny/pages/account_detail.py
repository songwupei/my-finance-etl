"""账户明细表 — DataGrid table page."""
from shiny import reactive, render, ui

from ..data import _account_detail_df


def account_detail_ui():
    return ui.card(
        ui.card_header("账户明细表"),
        ui.output_data_frame("account_detail_table"),
    )


def account_detail_server(input, output, session):
    @reactive.calc
    def _data():
        return _account_detail_df.clone()

    @render.data_frame
    def account_detail_table():
        df = _data()
        if df.height == 0:
            return None
        return render.DataGrid(
            df.to_pandas(),
            height=600,
            filters=True,
        )

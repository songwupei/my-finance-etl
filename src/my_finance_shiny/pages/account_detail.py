"""账户明细表 — DataGrid 交互式表格。"""

from shiny import reactive, render, ui

from ..data import account_detail


def page():
    return ui.card(
        ui.card_header("账户明细表"),
        ui.output_data_frame("account_detail_table"),
    )


def server(input, output, session):
    @reactive.calc
    def _data():
        return account_detail.clone()

    @render.data_frame
    def account_detail_table():
        df = _data()
        if df.height == 0:
            return None
        return render.DataGrid(df.to_pandas(), height=600, filters=True)

"""账户明细表页面."""
import vizro.models as vm
from vizro.tables import dash_ag_grid

from .data import _account_detail_column_defs, _account_detail_df

_vizro_page_account_detail = vm.Page(
    id="account-detail",
    title="账户明细表",
    components=[
        vm.AgGrid(
            figure=dash_ag_grid(
                data_frame=_account_detail_df,
                dashGridOptions={"pagination": True, "domLayout": "autoHeight",
                                 "columnDefs": _account_detail_column_defs},
            ),
            title="账户明细表",
        ),
    ],
)

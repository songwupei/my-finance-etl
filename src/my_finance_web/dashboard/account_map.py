"""账户地图 + AgGrid — 账户地理分布气泡图."""
import numpy as np
import yaml
import vizro.actions as va
import vizro.models as vm
from vizro.models.types import capture
from vizro.tables import dash_ag_grid

from map_utils.china_map import create_china_map_figure, add_scattermap

from ..config import _proj_dir
from .data import _account_detail_column_defs, _account_detail_df, _bank_map_account_data

_map_cfg = yaml.safe_load(open(_proj_dir / "conf/base/parameters.yml")).get("map", {})


@capture("graph")
def bank_account_map(data_frame=None):
    if data_frame is None:
        data_frame = _bank_map_account_data
    data_frame = data_frame.copy()

    agg = data_frame.groupby([
        "institution_code", "branch_name", "financial_institution",
        "longitude", "latitude", "formatted_address"
    ], dropna=False).agg(
        total_balance=("balance_amount", "sum"),
        account_count=("balance_amount", "count"),
    ).reset_index()

    sg_agg = data_frame.groupby(["institution_code", "sub_group_name"], dropna=False).agg(
        sg_balance=("balance_amount", "sum")
    ).reset_index()
    sg_agg["sg_text"] = (
        sg_agg["sub_group_name"] + ": "
        + (sg_agg["sg_balance"] / 10000).apply(lambda x: f"{x:,.0f}万元")
    )
    sg_order = sg_agg.sort_values(
        ["institution_code", "sg_balance"], ascending=[True, False]
    )
    sg_breakdown = sg_order.groupby("institution_code", sort=False).agg(
        subgroup_breakdown=("sg_text", lambda x: "<br>".join(x))
    ).reset_index()

    agg = agg.merge(sg_breakdown, on="institution_code", how="left")
    agg["subgroup_breakdown"] = agg["subgroup_breakdown"].fillna("")

    _max = agg["total_balance"].max() if agg.shape[0] > 0 else 1
    agg["size_scaled"] = np.log10(agg["total_balance"].clip(lower=1))**2 * 2
    agg["hover_text"] = (
        agg["branch_name"] + "<br>"
        + "所属银行: " + agg["financial_institution"] + "<br>"
        + "账户数: " + agg["account_count"].apply(lambda x: f"{x:,}个")
        + " | 合计余额: " + agg["total_balance"].apply(lambda x: f"{x/10000:,.0f}万元")
        + "<br><br><b>子集团余额明细:</b><br>" + agg["subgroup_breakdown"]
    )

    provider = _map_cfg.get("provider", "gaode")
    fig = create_china_map_figure(
        provider=provider, tile_type="vec",
        center_lon=_map_cfg.get("center_lon", 104.195),
        center_lat=_map_cfg.get("center_lat", 35.675),
        zoom=_map_cfg.get("zoom", 3),
        height=_map_cfg.get("height", 800),
        title="银行账户地理分布")

    _step = _max / 5 if _max > 0 else 1
    _ticks = [_step * i for i in range(6)]
    add_scattermap(
        fig, provider,
        lat=agg["latitude"].to_list(),
        lon=agg["longitude"].to_list(),
        mode="markers",
        marker=dict(
            size=agg["size_scaled"].clip(lower=3),
            color=agg["total_balance"],
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(
                title="合计余额 (万元)",
                tickvals=_ticks,
                ticktext=[f"{v/10000:,.0f}" for v in _ticks],
            ),
            sizemin=3, sizemode="area",
            opacity=0.7, symbol="circle",
        ),
        text=agg["hover_text"].to_list(),
        hoverinfo="text",
    )
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig


_vizro_page_bank_map = vm.Page(
    id="bank-account-map",
    title="账户地图",
    components=[
        vm.Graph(
            id="bank-map-graph",
            figure=bank_account_map(data_frame=_bank_map_account_data),
        ),
        vm.AgGrid(
            id="clicked-branch-table",
            figure=dash_ag_grid(
                data_frame=_account_detail_df,
                dashGridOptions={"pagination": True, "domLayout": "autoHeight",
                                 "columnDefs": _account_detail_column_defs,
                                 "defaultColDef": {"filter": True, "resizable": True}},
            ),
            title="账户明细表",
        ),
        vm.Button(text="📥 导出 CSV", actions=va.export_data(targets=["clicked-branch-table"])),
    ],
    controls=[
        vm.Filter(column="sub_group_name",
                  selector=vm.Dropdown(id="sg-filter", title="子集团", multi=True)),
        vm.Filter(column="financial_institution",
                  selector=vm.Dropdown(id="bank-filter", title="所属银行", multi=True)),
        vm.Filter(column="province",
                  selector=vm.Dropdown(id="prov-filter", title="省份", multi=True)),
        vm.Filter(column="bank_city",
                  selector=vm.Dropdown(id="city-filter", title="城市", multi=True)),
        vm.Filter(column="branch_name",
                  selector=vm.Dropdown(id="branch-filter", title="开户网点", multi=True)),
    ],
)

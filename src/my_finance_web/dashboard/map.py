"""图3：中国地图 — 单位地理分布 + 资产规模."""
import numpy as np
import yaml
import vizro.models as vm
from vizro.models.types import capture

import plotly.graph_objects as go
from map_utils.china_map import create_china_map_figure, add_scattermap

from ..config import _proj_dir
from .data import _vizro_geo_data

_map_cfg = yaml.safe_load(open(_proj_dir / "conf/base/parameters.yml")).get("map", {})


@capture("graph")
def geo_map(data_frame=_vizro_geo_data):
    data_frame = data_frame.copy()
    data_frame["size_scaled"] = data_frame["total_assets"] / 10000
    data_frame["hover_text"] = (
        data_frame["unit_name"] + "<br>" +
        data_frame["enterprise_address"].fillna("").str.strip() + "<br>" +
        "资产总额: " + data_frame["total_assets"].apply(lambda x: f"{x:,.0f}万元")
    )
    provider = _map_cfg.get("provider", "gaode")
    fig = create_china_map_figure(
        provider=provider,
        tile_type="vec",
        center_lon=_map_cfg.get("center_lon", 104.195),
        center_lat=_map_cfg.get("center_lat", 35.675),
        zoom=_map_cfg.get("zoom", 3),
        height=_map_cfg.get("height", 800),
        title="成员单位地理分布")
    add_scattermap(
        fig, provider,
        lat=data_frame["latitude"].to_list(),
        lon=data_frame["longitude"].to_list(),
        mode="markers",
        marker=dict(
            size=data_frame["size_scaled"].clip(lower=3),
            color=np.log10(data_frame["total_assets"].clip(lower=1)),
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(
                title="资产总额 (人民币元)",
                tickvals=[1, 2, 3, 4, 5, 6],
                ticktext=["10", "100", "1,000", "1万", "10万", "100万"],
            ),
            sizemin=3, sizemode="area",
            opacity=0.7, symbol="circle",
        ),
        text=data_frame["hover_text"].to_list(),
        hoverinfo="text",
    )
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig


_vizro_geo_fig = geo_map(data_frame=_vizro_geo_data) if _vizro_geo_data.shape[0] > 0 else None

_vizro_page_map_components = [vm.Graph(figure=_vizro_geo_fig)] if _vizro_geo_fig is not None else [vm.Card(text="地理分布 — 等待地理编码数据")]

_vizro_page_map = vm.Page(
    id="china-map",
    title="地理分布",
    components=_vizro_page_map_components,
)

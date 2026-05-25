"""China geo map figure builder."""
import polars as pl
import yaml
from map_utils.china_map import create_china_map_figure, add_scattermap

from ..config import _proj_dir

_map_cfg = yaml.safe_load(open(_proj_dir / "conf/base/parameters.yml")).get("map", {})


def geo_map(data_frame):
    df = data_frame.clone()
    df = df.with_columns((pl.col("total_assets") / 10000).alias("size_scaled"))
    assets = df["total_assets"]
    _log10 = assets.clip(1).log10()

    hover_text = [
        f"{n}<br>{a.strip() if a else ''}<br>资产总额: {t:,.0f}万元"
        for n, a, t in zip(
            df["unit_name"].to_list(),
            df["enterprise_address"].fill_null("").to_list(),
            assets.to_list(),
        )
    ]

    provider = _map_cfg.get("provider", "gaode")
    fig = create_china_map_figure(
        provider=provider,
        tile_type="vec",
        center_lon=_map_cfg.get("center_lon", 104.195),
        center_lat=_map_cfg.get("center_lat", 35.675),
        zoom=_map_cfg.get("zoom", 3),
        height=_map_cfg.get("height", 800),
        title="成员单位地理分布",
    )
    add_scattermap(
        fig, provider,
        lat=df["latitude"].to_list(),
        lon=df["longitude"].to_list(),
        mode="markers",
        marker=dict(
            size=df["size_scaled"].clip(3).to_list(),
            color=_log10.to_list(),
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
        text=hover_text,
        hoverinfo="text",
    )
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig

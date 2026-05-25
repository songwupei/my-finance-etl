"""Bank account map figure builder."""
import polars as pl
import yaml
from map_utils.china_map import create_china_map_figure, add_scattermap

from ..config import _proj_dir

_map_cfg = yaml.safe_load(open(_proj_dir / "conf/base/parameters.yml")).get("map", {})


def bank_account_map(data_frame):
    df = data_frame.clone()

    # Aggregate by institution_code + branch
    agg = df.group_by([
        "institution_code", "branch_name", "financial_institution",
        "longitude", "latitude", "formatted_address",
    ]).agg(
        pl.col("balance_amount").sum().alias("total_balance"),
        pl.col("balance_amount").len().alias("account_count"),
    )

    # Sub-group breakdown
    sg_agg = df.group_by(["institution_code", "sub_group_name"]).agg(
        pl.col("balance_amount").sum().alias("sg_balance"),
    )
    sg_agg = sg_agg.with_columns(
        (pl.col("sub_group_name")
         + ": "
         + (pl.col("sg_balance") / 10000).round(0).cast(pl.Utf8)
         + "万元").alias("sg_text")
    )
    sg_order = sg_agg.sort(["institution_code", "sg_balance"], descending=[False, True])
    sg_breakdown = sg_order.group_by("institution_code", maintain_order=True).agg(
        pl.col("sg_text").str.join("<br>").alias("subgroup_breakdown"),
    )

    agg = agg.join(sg_breakdown, on="institution_code", how="left")
    agg = agg.with_columns(pl.col("subgroup_breakdown").fill_null(""))

    _max = agg["total_balance"].max() if agg.height > 0 else 1
    agg = agg.with_columns(
        (pl.col("total_balance").clip(1).log10().pow(2) * 2).alias("size_scaled"),
    )

    # Build hover text
    branches = agg["branch_name"].to_list()
    fin_insts = agg["financial_institution"].to_list()
    acct_counts = agg["account_count"].to_list()
    total_bals = agg["total_balance"].to_list()
    breakdowns = agg["subgroup_breakdown"].to_list()

    hover_text = [
        f"{b}<br>所属银行: {f}<br>账户数: {c:,}个 | 合计余额: {t/10000:,.0f}万元<br><br><b>子集团余额明细:</b><br>{d}"
        for b, f, c, t, d in zip(branches, fin_insts, acct_counts, total_bals, breakdowns)
    ]

    provider = _map_cfg.get("provider", "gaode")
    fig = create_china_map_figure(
        provider=provider, tile_type="vec",
        center_lon=_map_cfg.get("center_lon", 104.195),
        center_lat=_map_cfg.get("center_lat", 35.675),
        zoom=_map_cfg.get("zoom", 3),
        height=_map_cfg.get("height", 800),
        title="银行账户地理分布",
    )

    _step = _max / 5 if _max > 0 else 1
    _ticks = [_step * i for i in range(6)]
    add_scattermap(
        fig, provider,
        lat=agg["latitude"].to_list(),
        lon=agg["longitude"].to_list(),
        mode="markers",
        marker=dict(
            size=agg["size_scaled"].clip(3).to_list(),
            color=agg["total_balance"].to_list(),
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
        text=hover_text,
        hoverinfo="text",
    )
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig

"""HOME, 穿透监控, 关系分析, 概览 页面."""
import numpy as np
import vizro.models as vm
from vizro.models.types import capture

import plotly.graph_objects as go

from .data import _vizro_df1

_vizro_page_home = vm.Page(
    id="home",
    title="首页",
    components=[
        vm.Card(text="""
        # 集团财务数据平台

        穿透监管 · 账户地图 · 余额分析 · 日报生成

        ---

        **穿透监控** — 资产负债气泡图、杠杆率与账户规模散点分析

        **地理分布** — 成员单位及银行账户全国地图可视化

        **账户地图** — 银行网点气泡图，支持多级联动筛选与明细导出

        **余额统计分析** — 子集团 / 银行 / 城市 / 交叉维度多视角分析

        **日报生成** — 组织树逐级钻取，一键生成并发送财务日报
        """),
    ],
)


@capture("graph")
def asset_liability_bubble(data_frame=_vizro_df1):
    df = data_frame
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["log10_资产总额"],
        y=df["log10_负债总额"],
        mode='markers',
        marker=dict(
            size=df["log10_账户数"].clip(lower=1) * 3,
            color=df["资产负债率"].clip(0, 1),
            colorscale='RdYlGn_r',
            showscale=True,
            colorbar=dict(title="资产负债率"),
            cmin=0, cmax=1,
            opacity=0.5,
            line=dict(width=0.5, color='white'),
        ),
        text=(
            df["单位名称"] + "<br>" +
            "资产: " + df["资产总额"].apply(lambda x: f"{x:,.0f}万元") + "<br>" +
            "负债: " + df["负债总额"].apply(lambda x: f"{x:,.0f}万元") + "<br>" +
            "账户: " + df["账户数"].apply(lambda x: f"{x:,}个") + "<br>" +
            "负债率: " + (df["资产负债率"] * 100).apply(lambda x: f"{x:.1f}%")
        ),
        hoverinfo='text',
    ))
    fig.update_layout(
        title="资产负债结构气泡图（气泡大小=账户数）",
        xaxis=dict(
            title="资产总额（万元，对数尺度）",
            tickvals=[0, 1, 2, 3, 4, 5, 6, 7],
            ticktext=["1", "10", "100", "1千", "1万", "10万", "100万", "1000万"],
        ),
        yaxis=dict(
            title="负债总额（万元，对数尺度）",
            tickvals=[0, 1, 2, 3, 4, 5, 6, 7],
            ticktext=["1", "10", "100", "1千", "1万", "10万", "100万", "1000万"],
        ),
    )
    _max_val = max(df["log10_资产总额"].max(), df["log10_负债总额"].max())
    _min_val = min(df["log10_资产总额"].min(), df["log10_负债总额"].min())
    fig.add_trace(go.Scatter(
        x=[_min_val, _max_val], y=[_min_val, _max_val],
        mode='lines', line=dict(dash='dash', color='gray', width=1),
        name='资产负债率=100%', showlegend=False,
    ))
    return fig


@capture("graph")
def leverage_vs_accounts(data_frame=_vizro_df1):
    df = data_frame
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["资产负债率"] * 100,
        y=df["账户数"],
        mode='markers',
        marker=dict(
            size=8,
            color=df["log10_资产总额"],
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title="log10(资产)"),
            opacity=0.5,
            line=dict(width=0.5, color='white'),
        ),
        text=(
            df["单位名称"] + "<br>" +
            "负债率: " + (df["资产负债率"] * 100).apply(lambda x: f"{x:.1f}%") + "<br>" +
            "账户: " + df["账户数"].apply(lambda x: f"{x:,}个")
        ),
        hoverinfo='text',
    ))
    fig.update_layout(
        title="杠杆率 vs 账户规模（正常区间 30-80%）",
        xaxis=dict(title="资产负债率 (%)", range=[0, 100]),
        yaxis=dict(title="账户数量"),
        shapes=[dict(
            type='rect', x0=30, x1=80, y0=0, y1=df["账户数"].max() * 1.1,
            fillcolor='green', opacity=0.05, line_width=0, layer='below',
        )],
    )
    return fig


_vizro_page_monitor = vm.Page(
    id="penetration-monitor",
    title="穿透监控大屏",
    components=[
        vm.Graph(figure=asset_liability_bubble(data_frame=_vizro_df1)),
        vm.Graph(figure=leverage_vs_accounts(data_frame=_vizro_df1)),
    ],
)

_vizro_page_relationship = vm.Page(
    id="relationship-analysis",
    title="关系分析",
    components=[
        vm.Card(text="关系分析页面 — 内容待开发"),
    ],
)

_vizro_page_overview = vm.Page(
    id="overview",
    title="概览",
    components=[
        vm.Card(text="概览页面 — 内容待开发"),
    ],
)

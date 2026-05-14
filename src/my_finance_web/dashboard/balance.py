"""余额统计分析 5 页面 (整体/子集团/银行/地理/交叉)."""
import numpy as np
import vizro.models as vm
from vizro.models.types import capture

import plotly.graph_objects as go

from .data import (
    _balance_base_data,
    _balance_by_subgroup,
    _balance_by_bank,
    _balance_by_city,
    _bank_data_for_chart,
    _bank_usage_pivot,
    _box_data,
    _city_known,
    _cross_data,
    _tier_data,
    _top10_sg,
    _top20_city,
    _top20_sg,
    _top8_banks,
)

# ---------- Page 1: 整体情况 ----------
_vizro_page_balance_overview_components = []
if _balance_base_data.shape[0] > 0:
    _total_bal = _balance_base_data["balance_amount"].sum()
    _total_accts = _balance_base_data["account_id"].nunique()
    _total_sg = _balance_base_data["sub_group_name"].nunique()
    _median_bal = _balance_base_data["balance_amount"].median()
    _overview_kpi = vm.Card(text=f"""
## 账户余额总览

| 指标 | 数值 |
|------|------|
| 总余额 | **{_total_bal:,.0f} 元** |
| 账户总数 | **{_total_accts:,}** |
| 子集团数 | **{_total_sg}** |
| 中位数余额 | **{_median_bal:,.0f} 元** |
""")


    @capture("graph")
    def balance_overview_histogram(data_frame=_balance_base_data):
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=data_frame["log10_balance"], nbinsx=40,
                                   marker=dict(color="#5470c6", line=dict(width=0.5, color="white")),
                                   hovertemplate="log10(余额): %{x:.1f}<br>账户数: %{y:,}<extra></extra>"))
        fig.update_layout(title="余额分布 (log10 尺度)", xaxis_title="log10(余额)", yaxis_title="账户数", bargap=0.05)
        return fig


    @capture("graph")
    def balance_overview_tier_pie(data_frame=_tier_data):
        fig = go.Figure()
        fig.add_trace(go.Pie(labels=data_frame["tier"], values=data_frame["account_count"],
                             hole=0.4, textinfo="label+percent",
                             hovertemplate="层级: %{label}<br>账户数: %{value:,}<br>占比: %{percent}<extra></extra>"))
        fig.update_layout(title="余额层级分布 (账户数)")
        return fig


    @capture("graph")
    def balance_overview_top10_bar(data_frame=_top10_sg):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=data_frame["sub_group_name"], y=data_frame["total_balance"],
                             marker=dict(color="#91cc75"), name="总余额",
                             hovertemplate="%{x}<br>总余额: %{y:,.0f}元<extra></extra>"))
        fig.update_layout(title="Top 10 子集团余额", xaxis_title="子集团", yaxis_title="总余额 (元)")
        return fig


    _vizro_page_balance_overview_components = [
        _overview_kpi,
        vm.Graph(figure=balance_overview_histogram(data_frame=_balance_base_data)),
        vm.Graph(figure=balance_overview_tier_pie(data_frame=_tier_data)),
        vm.Graph(figure=balance_overview_top10_bar(data_frame=_top10_sg)),
    ]
else:
    _vizro_page_balance_overview_components = [vm.Card(text="整体情况 — 等待数据")]

_vizro_page_balance_overview = vm.Page(
    id="balance-overview",
    title="整体情况",
    components=_vizro_page_balance_overview_components,
)

# ---------- Page 2: 子集团维度 ----------
_vizro_page_balance_subgroup_components = []
if _balance_by_subgroup is not None:

    @capture("graph")
    def subgroup_bar(data_frame=_top20_sg):
        fig = go.Figure()
        fig.add_trace(go.Bar(y=data_frame["sub_group_name"][::-1], x=data_frame["total_balance"][::-1],
                             orientation="h", marker=dict(color="#5470c6"),
                             hovertemplate="%{y}<br>总余额: %{x:,.0f}元<extra></extra>"))
        fig.update_layout(title="Top 20 子集团余额排名", yaxis_title="", xaxis_title="总余额 (元)", height=600)
        return fig


    @capture("graph")
    def subgroup_treemap(data_frame=_balance_by_subgroup.head(30)):
        fig = go.Figure()
        fig.add_trace(go.Treemap(labels=data_frame["sub_group_name"],
                                 parents=[""] * len(data_frame),
                                 values=data_frame["total_balance"],
                                 textinfo="label+value+percent root",
                                 hovertemplate="%{label}<br>总余额: %{value:,.0f}元<extra></extra>"))
        fig.update_layout(title="子集团余额占比 Treemap (Top 30)")
        return fig


    _vizro_page_balance_subgroup_components = [
        vm.Graph(figure=subgroup_bar(data_frame=_top20_sg)),
        vm.Graph(figure=subgroup_treemap(data_frame=_balance_by_subgroup.head(30))),
    ]
else:
    _vizro_page_balance_subgroup_components = [vm.Card(text="子集团维度 — 等待数据")]

_vizro_page_balance_subgroup = vm.Page(
    id="balance-subgroup",
    title="子集团维度",
    components=_vizro_page_balance_subgroup_components,
)

# ---------- Page 3: 所属银行维度 ----------
_vizro_page_balance_bank_components = []
if _balance_by_bank is not None:

    @capture("graph")
    def bank_bar(data_frame=_bank_data_for_chart):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=data_frame["financial_institution"], y=data_frame["total_balance"],
                             marker=dict(color="#ee6666"),
                             hovertemplate="%{x}<br>总余额: %{y:,.0f}元<extra></extra>"))
        fig.update_layout(title="银行余额排名 (剔除财务公司)", xaxis_title="银行", yaxis_title="总余额 (元)")
        fig.update_xaxes(tickangle=45)
        return fig


    @capture("graph")
    def bank_pie(data_frame=_bank_data_for_chart.head(10)):
        fig = go.Figure()
        fig.add_trace(go.Pie(labels=data_frame["financial_institution"], values=data_frame["total_balance"],
                             hole=0.4, textinfo="label+percent",
                             hovertemplate="%{label}<br>总余额: %{value:,.0f}元<extra></extra>"))
        fig.update_layout(title="银行余额占比 (Top 10, 剔除财务公司)")
        return fig


    @capture("graph")
    def bank_usage_stacked(data_frame=_bank_usage_pivot):
        fig = go.Figure()
        for col in data_frame.columns:
            fig.add_trace(go.Bar(name=col, x=data_frame.index, y=data_frame[col],
                                 hovertemplate="%{x}<br>" + col + ": %{y:,.0f}元<extra></extra>"))
        fig.update_layout(title="Top 10 银行 × 账户用途堆叠", barmode="stack", xaxis_title="银行", yaxis_title="总余额 (元)")
        fig.update_xaxes(tickangle=45)
        return fig


    _vizro_page_balance_bank_components = [
        vm.Graph(figure=bank_bar(data_frame=_bank_data_for_chart)),
        vm.Graph(figure=bank_pie(data_frame=_bank_data_for_chart.head(10))),
        vm.Graph(figure=bank_usage_stacked(data_frame=_bank_usage_pivot)),
    ]
else:
    _vizro_page_balance_bank_components = [vm.Card(text="所属银行维度 — 等待数据")]

_vizro_page_balance_bank = vm.Page(
    id="balance-bank",
    title="所属银行维度",
    components=_vizro_page_balance_bank_components,
)

# ---------- Page 4: 地理维度 ----------
_vizro_page_balance_geo_components = []
if _balance_by_city is not None:
    _city_pct = _balance_base_data["bank_city"].ne("未知城市").mean() * 100

    _geo_kpi = vm.Card(text=f"""
### 地理覆盖

已定位城市账户占比: **{_city_pct:.1f}%**
""")


    @capture("graph")
    def city_bar(data_frame=_top20_city):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=data_frame["bank_city"], y=data_frame["total_balance"],
                             marker=dict(color="#73c0de"),
                             hovertemplate="%{x}<br>总余额: %{y:,.0f}元<extra></extra>"))
        fig.update_layout(title="Top 20 城市余额排名", xaxis_title="城市", yaxis_title="总余额 (元)")
        fig.update_xaxes(tickangle=45)
        return fig


    _vizro_page_balance_geo_components = [
        _geo_kpi,
        vm.Graph(figure=city_bar(data_frame=_top20_city)),
    ]
else:
    _vizro_page_balance_geo_components = [vm.Card(text="地理维度 — 等待数据")]

_vizro_page_balance_geo = vm.Page(
    id="balance-geo",
    title="地理维度",
    components=_vizro_page_balance_geo_components,
)

# ---------- Page 5: 交叉维度 ----------
_vizro_page_balance_cross_components = []
if _balance_by_subgroup is not None and _balance_by_bank is not None:

    @capture("graph")
    def cross_scatter(data_frame=_cross_data):
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=data_frame["log10_account_count"], y=data_frame["log10_avg_balance"],
            mode="markers",
            marker=dict(size=data_frame["size_scaled"].clip(lower=3), color=data_frame["log10_avg_balance"],
                        colorscale="Viridis", showscale=True, colorbar=dict(title="log10(平均余额)"),
                        opacity=0.6, line=dict(width=0.5, color="white")),
            text=(data_frame["sub_group_name"] + "<br>账户数: " + data_frame["account_count"].apply(lambda x: f"{x:,}") +
                  "<br>平均余额: " + data_frame["avg_balance"].apply(lambda x: f"{x:,.0f}元") +
                  "<br>总余额: " + data_frame["total_balance"].apply(lambda x: f"{x:,.0f}元")),
            hoverinfo="text",
        ))
        fig.update_layout(title="子集团: 账户数 vs 平均余额 (气泡=总余额)", xaxis_title="log10(账户数)", yaxis_title="log10(平均余额)")
        return fig


    @capture("graph")
    def cross_box(data_frame=_box_data):
        fig = go.Figure()
        for bank in _top8_banks:
            bank_vals = data_frame[data_frame["financial_institution"] == bank]["log10_balance"]
            fig.add_trace(go.Box(y=bank_vals, name=bank, boxmean=True,
                                 hovertemplate="%{y:.1f}<extra></extra>"))
        fig.update_layout(title="余额分布 by 所属银行 (log10 尺度, Top 8)", yaxis_title="log10(余额)", showlegend=False)
        return fig


    _vizro_page_balance_cross_components = [
        vm.Graph(figure=cross_scatter(data_frame=_cross_data)),
        vm.Graph(figure=cross_box(data_frame=_box_data)),
    ]
else:
    _vizro_page_balance_cross_components = [vm.Card(text="交叉维度 — 等待数据")]

_vizro_page_balance_cross = vm.Page(
    id="balance-cross",
    title="交叉维度",
    components=_vizro_page_balance_cross_components,
)

"""Balance analysis figure builders (11 figures across 5 pages)."""
import plotly.graph_objects as go


# ---- Page 1: 整体情况 ----

def balance_overview_histogram(data_frame):
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=data_frame["log10_balance"].to_list(), nbinsx=40,
        marker=dict(color="#5470c6", line=dict(width=0.5, color="white")),
        hovertemplate="log10(余额): %{x:.1f}<br>账户数: %{y:,}<extra></extra>",
    ))
    fig.update_layout(
        title="余额分布 (log10 尺度)",
        xaxis_title="log10(余额)", yaxis_title="账户数",
        bargap=0.05,
    )
    return fig


def balance_overview_tier_pie(data_frame):
    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=data_frame["tier"].to_list(),
        values=data_frame["account_count"].to_list(),
        hole=0.4, textinfo="label+percent",
        hovertemplate="层级: %{label}<br>账户数: %{value:,}<br>占比: %{percent}<extra></extra>",
    ))
    fig.update_layout(title="余额层级分布 (账户数)")
    return fig


def balance_overview_top10_bar(data_frame):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=data_frame["sub_group_name"].to_list(),
        y=data_frame["total_balance"].to_list(),
        marker=dict(color="#91cc75"), name="总余额",
        hovertemplate="%{x}<br>总余额: %{y:,.0f}元<extra></extra>",
    ))
    fig.update_layout(title="Top 10 子集团余额", xaxis_title="子集团", yaxis_title="总余额 (元)")
    return fig


# ---- Page 2: 子集团维度 ----

def subgroup_bar(data_frame):
    df = data_frame
    names = df["sub_group_name"].to_list()[::-1]
    vals = df["total_balance"].to_list()[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names, x=vals, orientation="h", marker=dict(color="#5470c6"),
        hovertemplate="%{y}<br>总余额: %{x:,.0f}元<extra></extra>",
    ))
    fig.update_layout(
        title="Top 20 子集团余额排名",
        yaxis_title="", xaxis_title="总余额 (元)", height=600,
    )
    return fig


def subgroup_treemap(data_frame):
    df = data_frame
    fig = go.Figure()
    fig.add_trace(go.Treemap(
        labels=df["sub_group_name"].to_list(),
        parents=[""] * df.height,
        values=df["total_balance"].to_list(),
        textinfo="label+value+percent root",
        hovertemplate="%{label}<br>总余额: %{value:,.0f}元<extra></extra>",
    ))
    fig.update_layout(title="子集团余额占比 Treemap (Top 30)")
    return fig


# ---- Page 3: 所属银行维度 ----

def bank_bar(data_frame):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=data_frame["financial_institution"].to_list(),
        y=data_frame["total_balance"].to_list(),
        marker=dict(color="#ee6666"),
        hovertemplate="%{x}<br>总余额: %{y:,.0f}元<extra></extra>",
    ))
    fig.update_layout(
        title="银行余额排名 (剔除财务公司)",
        xaxis_title="银行", yaxis_title="总余额 (元)",
    )
    fig.update_xaxes(tickangle=45)
    return fig


def bank_pie(data_frame):
    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=data_frame["financial_institution"].to_list(),
        values=data_frame["total_balance"].to_list(),
        hole=0.4, textinfo="label+percent",
        hovertemplate="%{label}<br>总余额: %{value:,.0f}元<extra></extra>",
    ))
    fig.update_layout(title="银行余额占比 (Top 10, 剔除财务公司)")
    return fig


def bank_usage_stacked(data_frame):
    df = data_frame
    fig = go.Figure()
    # Pivot: columns = account_usage values, rows = financial_institution
    # data_frame is a pivot table: rows=financial_institution, cols=account_usage
    cols = [c for c in df.columns if c != "financial_institution"]
    institutions = df["financial_institution"].to_list()
    for col in cols:
        vals = df[col].to_list()
        fig.add_trace(go.Bar(
            name=col, x=institutions, y=vals,
            hovertemplate="%{x}<br>" + col + ": %{y:,.0f}元<extra></extra>",
        ))
    fig.update_layout(
        title="Top 10 银行 × 账户用途堆叠",
        barmode="stack", xaxis_title="银行", yaxis_title="总余额 (元)",
    )
    fig.update_xaxes(tickangle=45)
    return fig


# ---- Page 4: 地理维度 ----

def city_bar(data_frame):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=data_frame["bank_city"].to_list(),
        y=data_frame["total_balance"].to_list(),
        marker=dict(color="#73c0de"),
        hovertemplate="%{x}<br>总余额: %{y:,.0f}元<extra></extra>",
    ))
    fig.update_layout(
        title="Top 20 城市余额排名",
        xaxis_title="城市", yaxis_title="总余额 (元)",
    )
    fig.update_xaxes(tickangle=45)
    return fig


# ---- Page 5: 交叉维度 ----

def cross_scatter(data_frame):
    df = data_frame
    fig = go.Figure()
    sizes = df["size_scaled"].clip(3).to_list()
    names = df["sub_group_name"].to_list()
    counts = df["account_count"].to_list()
    avgs = df["avg_balance"].to_list()
    totals = df["total_balance"].to_list()
    fig.add_trace(go.Scatter(
        x=df["log10_account_count"].to_list(),
        y=df["log10_avg_balance"].to_list(),
        mode="markers",
        marker=dict(
            size=sizes,
            color=df["log10_avg_balance"].to_list(),
            colorscale="Viridis", showscale=True,
            colorbar=dict(title="log10(平均余额)"),
            opacity=0.6, line=dict(width=0.5, color="white"),
        ),
        text=[
            f"{n}<br>账户数: {c:,}<br>平均余额: {a:,.0f}元<br>总余额: {t:,.0f}元"
            for n, c, a, t in zip(names, counts, avgs, totals)
        ],
        hoverinfo="text",
    ))
    fig.update_layout(
        title="子集团: 账户数 vs 平均余额 (气泡=总余额)",
        xaxis_title="log10(账户数)", yaxis_title="log10(平均余额)",
    )
    return fig


def cross_box(data_frame, top8_banks):
    fig = go.Figure()
    for bank in top8_banks:
        bank_vals = data_frame.filter(data_frame["financial_institution"] == bank)
        fig.add_trace(go.Box(
            y=bank_vals["log10_balance"].to_list(), name=bank,
            boxmean=True, hovertemplate="%{y:.1f}<extra></extra>",
        ))
    fig.update_layout(
        title="余额分布 by 所属银行 (log10 尺度, Top 8)",
        yaxis_title="log10(余额)", showlegend=False,
    )
    return fig

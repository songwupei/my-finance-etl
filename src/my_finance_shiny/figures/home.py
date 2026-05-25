"""HOME page figure builders — asset-liability bubble + leverage scatter."""
import plotly.graph_objects as go


def asset_liability_bubble(data_frame):
    df = data_frame
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["log10_资产总额"].to_list(),
        y=df["log10_负债总额"].to_list(),
        mode='markers',
        marker=dict(
            size=(df["log10_账户数"].clip(1) * 3).to_list(),
            color=df["资产负债率"].clip(0, 1).to_list(),
            colorscale='RdYlGn_r',
            showscale=True,
            colorbar=dict(title="资产负债率"),
            cmin=0, cmax=1,
            opacity=0.5,
            line=dict(width=0.5, color='white'),
        ),
        text=[
            f"{n}<br>资产: {a:,.0f}万元<br>负债: {l:,.0f}万元<br>账户: {c:,}个<br>负债率: {r*100:.1f}%"
            for n, a, l, c, r in zip(
                df["单位名称"].to_list(),
                df["资产总额"].to_list(),
                df["负债总额"].to_list(),
                df["账户数"].to_list(),
                df["资产负债率"].to_list(),
            )
        ],
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


def leverage_vs_accounts(data_frame):
    df = data_frame
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=(df["资产负债率"] * 100).to_list(),
        y=df["账户数"].to_list(),
        mode='markers',
        marker=dict(
            size=8,
            color=df["log10_资产总额"].to_list(),
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title="log10(资产)"),
            opacity=0.5,
            line=dict(width=0.5, color='white'),
        ),
        text=[
            f"{n}<br>负债率: {r*100:.1f}%<br>账户: {c:,}个"
            for n, r, c in zip(
                df["单位名称"].to_list(),
                df["资产负债率"].to_list(),
                df["账户数"].to_list(),
            )
        ],
        hoverinfo='text',
    ))
    max_accts = df["账户数"].max()
    fig.update_layout(
        title="杠杆率 vs 账户规模（正常区间 30-80%）",
        xaxis=dict(title="资产负债率 (%)", range=[0, 100]),
        yaxis=dict(title="账户数量"),
        shapes=[dict(
            type='rect', x0=30, x1=80, y0=0, y1=max_accts * 1.1,
            fillcolor='green', opacity=0.05, line_width=0, layer='below',
        )],
    )
    return fig

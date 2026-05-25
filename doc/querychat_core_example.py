"""
She Scores QueryChat — Shiny Core 版本
来源: https://shiny.posit.co/blog/posts/querychat-python-r/

运行方式:
    shiny run --reload --launch-browser path/to/app.py

架构说明:
    - Shiny Core 模式: 显式定义 app_ui 和 server 函数
    - QueryChat: 封装了 LLM 对话 + 数据过滤的组件，用户用自然语言查询，自动生成 pandas 过滤代码
    - qc.server(): 返回 reactive.Value 包装的过滤后数据 (Server 端使用)
    - qc.sidebar(): 返回侧边栏 UI 组件 (Server 端在 ui.page_sidebar 中使用)

Express vs Core 对比:
    - Express: 简洁，顶层代码直接执行，适合快速原型和简单应用
    - Core: 显式分离 UI/Server，更适合复杂应用和需要精细控制生命周期的场景

依赖:
    - shiny, shinywidgets
    - querychat (pip install querychat)
    - pandas, plotly, numpy
    - python-dotenv (用于加载 API key)
"""

from shiny import App, render, ui
from dotenv import load_dotenv
from querychat import QueryChat  # Core 版本从 querychat 直接导入
from pathlib import Path
import pandas as pd
import plotly.express as px
from shinywidgets import output_widget, render_widget
import numpy as np

load_dotenv()  # 从 .env 文件加载 ANTHROPIC_API_KEY 等环境变量

# ===============================
# 数据加载与清洗
# ===============================
results_with_scorers = pd.read_csv(
    Path(__file__).parent.parent / "data/results_with_scorers.csv"
)

results_with_scorers["date"] = pd.to_datetime(results_with_scorers["date"])

# 过滤：排除友谊赛 + 仅保留 2000 年后的数据
results_with_scorers = results_with_scorers[
    (results_with_scorers["tournament"] != "Friendly")
    & (results_with_scorers["date"] >= "2000-01-01")
]

# ===============================
# QueryChat 初始化 (在 UI/Server 外部)
# ===============================
shescores_greeting = Path(__file__).parent / "shescores_greeting.md"
shescores_data_description = Path(__file__).parent / "shescores_data_description.md"
shescores_extra_instructions = Path(__file__).parent / "shescores_extra_instructions.md"

qc = QueryChat(
    results_with_scorers,
    "results_with_scorers",  # 在 LLM 提示词中使用的表名
    client="anthropic/claude-sonnet-4-5",
    greeting=shescores_greeting,
    data_description=shescores_data_description,
    extra_instructions=shescores_extra_instructions,
)

# ===============================
# UI — 显式定义布局
# ===============================
app_ui = ui.page_sidebar(
    # 侧边栏: QueryChat 聊天控件
    qc.sidebar(),

    # 第1行: 3 个概览指标卡
    ui.layout_columns(
        ui.value_box(title="Top scoring country", value=ui.output_text("top_country")),
        ui.value_box(
            "Top scorer",
            ui.output_text("top_scorer"),
            ui.output_text("top_scorer_missing"),
        ),
        ui.value_box(title="Total countries", value=ui.output_text("total_countries")),
    ),
    ui.br(),

    # 第2行: 地图 + 折线图
    ui.layout_columns(
        ui.card(output_widget("map"), min_height="500px"),
        ui.card(output_widget("overview"), min_height="500px"),
    ),
    ui.br(),

    # 第3行: 详细比赛表格
    ui.layout_columns(
        ui.card(
            ui.output_data_frame("results_table"),
            min_height="600px",
        )
    ),

    # 页面标题和设置
    title="She Scores ⚽️: Women's International Soccer Matches",
    fillable=False,
    theme=ui.Theme.from_brand(__file__),
)


# ===============================
# Server — 显式定义 server 函数
# ===============================
def server(input, output, session):
    # Core 模式: qc.server() 返回一个 reactive.Value，
    # 当用户在聊天中输入查询后，数据会被 LLM 生成的代码过滤
    filtered_data = qc.server()

    @render.text
    def top_country():
        df = filtered_data.df()  # 获取当前过滤后的数据
        if df.empty:
            return "No matches found"

        home = (
            df.groupby(["date", "home_team", "tournament"])
            .agg(
                country=("home_team", "first"),
                matches=("tournament", lambda x: x.nunique()),
                goals=("home_score", "first"),
                country_flag=("country_flag_home", "first"),
            )
            .reset_index(drop=True)
        )

        away = (
            df.groupby(["date", "away_team", "tournament"])
            .agg(
                country=("away_team", "first"),
                matches=("tournament", lambda x: x.nunique()),
                goals=("away_score", "first"),
                country_flag=("country_flag_away", "first"),
            )
            .reset_index(drop=True)
        )

        combined = pd.concat([home, away], ignore_index=True)

        top_country = (
            combined.groupby("country")
            .agg(
                matches=("matches", "sum"),
                goals=("goals", "sum"),
                country_flag=("country_flag", "first"),
            )
            .reset_index()
            .sort_values("goals", ascending=False)
            .head(1)
        )

        result_string = (
            top_country["country"].iloc[0] + top_country["country_flag"].iloc[0]
        )
        return result_string

    @render.text
    def top_scorer():
        df = filtered_data.df()
        if df.empty or df["scorer"].notna().sum() == 0:
            return "No scorers found"

        top_scorer = (
            df[df["scorer"].notna()]
            .assign(
                country_flag=lambda x: np.where(
                    x["team"] == x["home_team"],
                    x["country_flag_home"],
                    x["country_flag_away"],
                )
            )
            .groupby(["scorer", "country_flag"])
            .size()
            .reset_index(name="goals")
            .sort_values("goals", ascending=False)
            .head(1)
        )

        result_string = (
            top_scorer["scorer"].iloc[0] + " " + top_scorer["country_flag"].iloc[0]
        )
        return result_string

    @render.text
    def top_scorer_missing():
        df = filtered_data.df()
        if df.empty:
            return ""

        missing = df["scorer"].isna().sum()
        total = len(df)
        missing_scorer_pct = missing / total * 100
        result_string = (
            "Missing scorer data: " + str(round(missing_scorer_pct, 2)) + "%"
        )
        return result_string

    @render.text
    def total_countries():
        df = filtered_data.df()
        if df.empty:
            return "0"

        total_countries = (
            df[["home_team", "away_team"]]
            .melt(value_name="country")
            .drop_duplicates(subset=["country"])
            .shape[0]
        )
        return total_countries

    @render_widget
    def overview():
        df = filtered_data.df()
        if df.empty:
            return px.scatter(title="No matches available for selected filters")

        overview_df = (
            df.groupby(df["date"].dt.year)
            .size()
            .reset_index(name="match_count")
            .rename(columns={"date": "year"})
        )

        fig = px.line(
            overview_df,
            x="year",
            y="match_count",
            title="Matches over time",
            labels={"year": "", "match_count": ""},
            markers=True,
        )

        fig.update_traces(
            line=dict(width=3, color="#0f0437"),
            marker=dict(size=6, color="white", line=dict(width=2, color="#5470C6")),
        )

        fig.update_layout(
            font=dict(family="Oswald, sans-serif", size=12, color="#343A40"),
            title=dict(font=dict(size=22)),
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, zeroline=False),
            yaxis=dict(showgrid=True, gridcolor="lightgrey", zeroline=False),
        )

        return fig

    @render_widget
    def map():
        df = filtered_data.df()
        df = df.dropna(subset=["latitude", "longitude"]).copy()
        df["year"] = pd.to_datetime(df["date"]).dt.year.astype(str)

        grouped = (
            df.groupby(["tournament", "latitude", "longitude", "city"])["year"]
            .apply(lambda x: ", ".join(sorted(x.unique())))
            .reset_index()
            .rename(columns={"year": "years"})
        )

        grouped["hover_text"] = (
            "<b>"
            + grouped["tournament"]
            + "</b><br>"
            + grouped["city"]
            + "<br>"
            + "Years: "
            + grouped["years"]
        )

        fig = px.scatter_map(
            grouped,
            lat="latitude",
            lon="longitude",
            hover_name="tournament",
            hover_data={},
            custom_data=["hover_text"],
            zoom=1,
            height=600,
        )

        fig.update_layout(
            autosize=True,
            mapbox_style="carto-positron",
        )

        fig.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",
            cluster=dict(enabled=True),
            marker=dict(size=20, symbol="circle", color="#5d923f"),
        )

        return fig

    @render.data_frame
    def results_table():
        df = filtered_data.df()
        if df.empty:
            return pd.DataFrame()

        def summarize_scorers(group):
            if group["scorer"].isna().all():
                return np.nan

            parts = (
                group.dropna(subset=["scorer"])
                .apply(lambda r: f"{r.scorer} ({r.team} at {r.minute}')", axis=1)
                .tolist()
            )
            return ", ".join(parts)

        table_data = (
            df.groupby(
                [
                    "date", "tournament",
                    "home_team", "country_flag_home", "home_score",
                    "away_score", "away_team", "country_flag_away",
                ],
                dropna=False,
            )
            .apply(summarize_scorers, include_groups=False)
            .reset_index(name="scorers")
        )

        display_df = table_data.copy()
        display_df["home_team"] = (
            display_df["home_team"] + " " + display_df["country_flag_home"]
        )
        display_df["away_team"] = (
            display_df["away_team"] + " " + display_df["country_flag_away"]
        )
        display_df = display_df.drop(columns=["country_flag_home", "country_flag_away"])
        display_df = display_df.rename(
            columns={
                "date": "Date",
                "tournament": "Tournament",
                "home_team": "Home Team",
                "home_score": "Home Score",
                "away_score": "Away Score",
                "away_team": "Away Team",
                "scorers": "Scorers",
            }
        )

        display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")
        display_df = display_df.sort_values("Date", ascending=False)

        return render.DataTable(
            display_df,
            styles=[
                {"cols": [0], "style": {"min-width": "100px", "width": "100px"}},
                {"cols": [1], "style": {"min-width": "200px"}},
                {"cols": [2], "style": {"min-width": "150px"}},
                {"cols": [3], "style": {"min-width": "100px"}},
                {"cols": [4], "style": {"min-width": "100px"}},
                {"cols": [5], "style": {"min-width": "150px"}},
                {"cols": [6], "style": {"min-width": "300px", "white-space": "normal"}},
                {
                    "rows": list(range(0, 10_000, 2)),
                    "style": {"background-color": "#e0e1e2"},
                },
            ],
        )


# ===============================
# 创建 App 实例 (Core 模式的关键步骤)
# ===============================
# Core 模式需要显式组合 UI 和 Server
app = App(app_ui, server)

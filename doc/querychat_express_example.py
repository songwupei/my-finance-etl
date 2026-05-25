"""
She Scores QueryChat — Shiny Express 版本
来源: https://posit-dev.github.io/querychat/py/index.html

运行方式:
    shiny run --reload --launch-browser Python/shescores-querychat-app-express.py

架构说明:
    - Shiny Express 模式: 顶层直接使用 @render 装饰器，无需显式定义 server 函数
    - QueryChat: 封装了 LLM 对话 + 数据过滤的组件，用户用自然语言查询，自动生成 pandas 过滤代码
    - qc.df(): 获取当前过滤后的 DataFrame
    - qc.sidebar(): 在侧边栏渲染聊天控件

依赖:
    - shiny, shinywidgets
    - querychat (pip install querychat)
    - pandas, plotly, numpy
    - python-dotenv (用于加载 API key)
"""

from shiny.express import render, ui
from dotenv import load_dotenv
from querychat.express import QueryChat
from pathlib import Path
import pandas as pd
import plotly.express as px
from shinywidgets import render_widget
import numpy as np

_ = load_dotenv()  # 从 .env 文件加载 ANTHROPIC_API_KEY 等环境变量

# ===============================
# 数据加载与清洗
# ===============================
# 读取 CSV 数据（比赛结果 + 射手信息）
results_with_scorers = pd.read_csv(
    Path(__file__).parent.parent / "data/results_with_scorers.csv"
)

# 转换日期列
results_with_scorers["date"] = pd.to_datetime(results_with_scorers["date"])

# 过滤：排除友谊赛 + 仅保留 2000 年后的数据
results_with_scorers = results_with_scorers[
    (results_with_scorers["tournament"] != "Friendly")
    & (results_with_scorers["date"] >= "2000-01-01")
]

# ===============================
# QueryChat 初始化
# ===============================
# 自定义 Markdown 文件用于个性化 LLM 行为
# - greeting: 首次打开显示的欢迎消息
# - data_description: 数据集的列说明，帮助 LLM 理解字段含义
# - extra_instructions: 额外的提示词约束
shescores_greeting = Path(__file__).parent / "shescores_greeting.md"
shescores_data_description = Path(__file__).parent / "shescores_data_description.md"
shescores_extra_instructions = Path(__file__).parent / "shescores_extra_instructions.md"

# QueryChat 核心组件:
#   参数1: DataFrame
#   参数2: 在提示词中使用的表名
#   client: LLM 客户端，格式为 "provider/model"，如 "anthropic/claude-sonnet-4-5"
#   greeting/data_description/extra_instructions: 可选的 Markdown 文件路径
qc = QueryChat(
    results_with_scorers,
    "results_with_scorers",
    client="anthropic/claude-sonnet-4-5",
    greeting=shescores_greeting,
    data_description=shescores_data_description,
    extra_instructions=shescores_extra_instructions,
)

# 在侧边栏中添加聊天 UI
qc.sidebar()

# ===============================
# 主页面 — 3 个 value_box 指标卡
# ===============================
with ui.layout_columns():
    with ui.value_box():
        "Top scoring country"

        @render.text
        def top_country():
            df = qc.df()  # 获取当前 QueryChat 过滤后的 DataFrame
            if df.empty:
                return "No matches found"

            # 主队统计
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

            # 客队统计
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

            # 合并主客队
            combined = pd.concat([home, away], ignore_index=True)

            # 按国家汇总，取进球最多
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

            # 返回: 国家名 + 国旗 emoji
            result_string = (
                top_country["country"].iloc[0] + top_country["country_flag"].iloc[0]
            )
            return result_string

    with ui.value_box():
        "Top scorer"

        @render.text
        def top_scorer():
            df = qc.df()
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
            """显示缺失射手数据的比例"""
            df = qc.df()
            if df.empty:
                return ""

            missing = df["scorer"].isna().sum()
            total = len(df)
            missing_scorer_pct = missing / total * 100
            result_string = (
                "Missing scorer data: " + str(round(missing_scorer_pct, 2)) + "%"
            )
            return result_string

    with ui.value_box():
        "Total countries"

        @render.text
        def total_countries():
            df = qc.df()
            if df.empty:
                return "0"

            # 统计主客队中出现的唯一国家数
            total_countries = (
                df[["home_team", "away_team"]]
                .melt(value_name="country")
                .drop_duplicates(subset=["country"])
                .shape[0]
            )
            return total_countries


ui.br()

# ===============================
# 地图 + 折线图 卡片行
# ===============================
with ui.layout_columns():
    with ui.card(min_height="500px"):

        @render_widget
        def map():
            """比赛举办城市散点地图"""
            df = qc.df()

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

    with ui.card(min_height="500px"):

        @render_widget
        def overview():
            """按年份统计比赛数量的折线图"""
            df = qc.df()
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


ui.br()

# ===============================
# 比赛结果详细表格
# ===============================
with ui.layout_columns():
    with ui.card(min_height="600px"):

        @render.data_frame
        def results_table():
            """交互式比赛结果表格"""
            df = qc.df()
            if df.empty:
                return pd.DataFrame()

            def summarize_scorers(group):
                """将每场比赛的射手汇总为一个字符串，格式: 'Name (Team at minute')'"""
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
            # 国旗 emoji 放在国家名后面
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
                    # 偶数行背景色（斑马条纹）
                    {
                        "rows": list(range(0, 10_000, 2)),
                        "style": {"background-color": "#e0e1e2"},
                    },
                ],
            )


# ===============================
# 页面全局配置
# ===============================
ui.page_opts(
    fillable=False,  # 非填充模式，允许页面滚动
    title="She Scores ⚽️: Women's International Soccer Matches",
    theme=ui.Theme.from_brand(__file__),  # 从 __file__ 推断品牌主题
)

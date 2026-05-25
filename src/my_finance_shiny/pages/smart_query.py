"""智能查询 — AI-powered natural language query for treasury account data."""
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import plotly.express as px
from dotenv import load_dotenv
from great_tables import GT, loc, style
from querychat import QueryChat
from shiny import render, ui
from shinywidgets import output_widget, render_widget

from ..data import _querychat_data, _querychat_finance_by_subgroup, _querychat_finance_period_label

_ = load_dotenv()

_pages_dir = Path(__file__).parent

# ============================================================
# QueryChat initialization (shared across sessions)
# ============================================================

qc = QueryChat(
    _querychat_data,
    "treasury_accounts",
    client="anthropic/claude-sonnet-4-5",
    greeting=_pages_dir / "smart_query_greeting.md",
    data_description=_pages_dir / "smart_query_data_description.md",
    extra_instructions=_pages_dir / "smart_query_extra_instructions.md",
)

# ============================================================
# Country centroid lookup for overseas geo visualization
# ============================================================
_COUNTRY_COORDS = {
    "香港": (22.3, 114.2), "澳门": (22.2, 113.55),
    "津巴布韦": (-19.0, 29.15), "阿曼": (21.5, 55.97),
    "塞尔维亚": (44.0, 21.0), "墨西哥": (23.0, -102.0),
    "南非": (-30.0, 25.0), "德国": (51.0, 9.0),
    "几内亚": (11.0, -10.0), "刚果（金）": (0.0, 25.0),
    "埃及": (27.0, 30.0), "利比里亚": (6.5, -9.5),
    "俄罗斯联邦": (60.0, 100.0), "摩洛哥": (32.0, -5.0),
    "西班牙": (40.0, -4.0), "东帝汶": (-8.87, 125.73),
    "卢森堡": (49.75, 6.17), "苏丹": (15.0, 30.0),
    "伊拉克": (33.0, 44.0), "意大利": (42.83, 12.83),
    "波兰": (52.0, 20.0), "沙特阿拉伯": (25.0, 45.0),
    "巴基斯坦": (30.0, 70.0), "蒙古": (46.0, 105.0),
    "印度尼西亚": (-5.0, 120.0), "缅甸": (22.0, 98.0),
    "波黑": (44.0, 18.0), "阿联酋": (24.0, 54.0),
    "法国": (46.0, 2.0), "匈牙利": (47.0, 20.0),
    "纳米比亚": (-22.0, 17.0), "加纳": (8.0, -2.0),
    "新加坡": (1.35, 103.82), "美国": (38.0, -97.0),
    "毛里求斯": (-20.3, 57.55), "英国": (54.0, -2.0),
    "巴西": (-10.0, -55.0),
}

_FINANCE_PERIOD = _querychat_finance_period_label

_BALANCE_PERIOD = ""
if _querychat_data.height > 0 and "balance_date" in _querychat_data.columns:
    _max_dt = _querychat_data["balance_date"].max()
    if _max_dt is not None:
        _BALANCE_PERIOD = str(_max_dt)[:10]

# ============================================================
# UI
# ============================================================


def smart_query_ui():
    return ui.layout_sidebar(
        qc.sidebar(),
        # Row 1: KPI cards
        ui.layout_columns(
            ui.value_box("账户总数", ui.output_text("sq_total_accounts")),
            ui.value_box("余额合计", ui.output_text("sq_total_balance")),
            ui.value_box("银行类型分布", ui.output_ui("sq_bank_breakdown")),
        ),
        ui.br(),
        # Row 2: Geo map (full width)
        ui.card(
            ui.card_header("账户地理分布"),
            output_widget("sq_geo_map"),
            min_height="500px",
        ),
        ui.br(),
        # Row 3: Sub-group summary table with export
        ui.card(
            ui.card_header(
                ui.row(
                    ui.span("子集团细分维度"),
                    ui.download_button("sq_export_summary", "导出 CSV"),
                    class_="d-flex justify-content-between align-items-center",
                )
            ),
            ui.output_ui("sq_summary_table"),
            min_height="500px",
        ),
        ui.br(),
        # Row 4: Detail table with export
        ui.card(
            ui.card_header(
                ui.row(
                    ui.span("账户明细"),
                    ui.download_button("sq_export_detail", "导出 CSV"),
                    class_="d-flex justify-content-between align-items-center",
                )
            ),
            ui.output_data_frame("sq_detail_table"),
            min_height="600px",
        ),
    )


# ============================================================
# Server
# ============================================================


def smart_query_server(input, output, session):
    data = qc.server()

    # ---- KPI cards ----

    @render.text
    def sq_total_accounts():
        df = data.df()
        if df is None:
            return "0"
        pl_df = _to_polars(df)
        if pl_df.height == 0:
            return "0"
        return f"{pl_df.height:,}"

    @render.text
    def sq_total_balance():
        df = data.df()
        if df is None:
            return "0 亿"
        pl_df = _to_polars(df)
        if pl_df.height == 0:
            return "0 亿"
        total = pl_df["balance_amount"].sum()
        if total is None:
            return "0 亿"
        yi = total / 1e8
        if yi >= 1:
            return f"{yi:,.2f} 亿"
        wan = total / 1e4
        return f"{wan:,.2f} 万"

    @render.ui
    def sq_bank_breakdown():
        df = data.df()
        if df is None:
            return ui.HTML("")
        pl_df = _to_polars(df)
        if pl_df.height == 0:
            return ui.HTML("")

        partner_n = pl_df.filter(pl.col("is_partner_bank") == "合作银行").height
        finance_n = pl_df.filter(pl.col("financial_institution") == "财务公司").height
        non_partner_n = pl_df.filter(
            (pl.col("is_partner_bank") == "非合作银行")
            & (pl.col("financial_institution") != "财务公司")
        ).height

        def _badge(label: str, value: str, color: str) -> ui.Tag:
            return ui.div(
                ui.div(label, style="font-size: 11px; color: #6c757d; margin-bottom: 2px;"),
                ui.div(value, style=f"font-size: 20px; font-weight: 700; color: {color};"),
                style="text-align: center; flex: 1;",
            )

        return ui.div(
            _badge("合作银行", f"{partner_n:,}", "#5470C6"),
            ui.div(style="width: 1px; background: #dee2e6; margin: 0 8px;"),
            _badge("非合作银行", f"{non_partner_n:,}", "#fc8452"),
            ui.div(style="width: 1px; background: #dee2e6; margin: 0 8px;"),
            _badge("财务公司", f"{finance_n:,}", "#5d923f"),
            style="display: flex; align-items: center; justify-content: space-around; padding: 8px 0;",
        )

    # ---- Geo map ----

    @render_widget
    def sq_geo_map():
        df = data.df()
        if df is None:
            return px.scatter_map(lat=[], lon=[], title="暂无数据")
        pl_df = _to_polars(df)
        if pl_df.height == 0:
            return px.scatter_map(lat=[], lon=[], title="暂无数据")

        domestic = pl_df.filter(pl.col("country_region") == "中国").filter(
            pl.col("longitude").is_not_null() & pl.col("latitude").is_not_null()
        )
        domestic_pts = []
        if domestic.height > 0:
            domestic_agg = domestic.group_by("bank_city").agg(
                pl.col("balance_amount").sum().alias("total_balance"),
                pl.col("account_name").len().alias("account_count"),
                pl.col("latitude").mean(),
                pl.col("longitude").mean(),
            )
            for row in domestic_agg.iter_rows(named=True):
                domestic_pts.append({
                    "name": row["bank_city"],
                    "lat": row["latitude"],
                    "lon": row["longitude"],
                    "balance": row["total_balance"],
                    "count": row["account_count"],
                    "region": "国内",
                })

        overseas = pl_df.filter(pl.col("country_region") != "中国")
        overseas_pts = []
        if overseas.height > 0:
            overseas_agg = overseas.group_by("country_region").agg(
                pl.col("balance_amount").sum().alias("total_balance"),
                pl.col("account_name").len().alias("account_count"),
            )
            for row in overseas_agg.iter_rows(named=True):
                coords = _COUNTRY_COORDS.get(row["country_region"])
                if coords is None:
                    continue
                overseas_pts.append({
                    "name": row["country_region"],
                    "lat": coords[0],
                    "lon": coords[1],
                    "balance": row["total_balance"],
                    "count": row["account_count"],
                    "region": "境外",
                })

        all_pts = domestic_pts + overseas_pts
        if not all_pts:
            return px.scatter_map(lat=[], lon=[], title="无地理坐标数据")
        pts_df = pd.DataFrame(all_pts)

        pts_df["hover_text"] = pts_df.apply(
            lambda r: (
                f"<b>{r['name']}</b> ({r['region']})<br>"
                f"余额: {r['balance']/1e8:,.2f} 亿<br>"
                f"账户数: {r['count']:,}"
            ),
            axis=1,
        )
        pts_df["size"] = pts_df["balance"].clip(1, None).apply(
            lambda x: max(10, min(40, np.log10(x) * 4))
        )

        color_map = {"国内": "#5470C6", "境外": "#ee6666"}

        fig = px.scatter_map(
            pts_df,
            lat="lat",
            lon="lon",
            hover_name="name",
            hover_data={"hover_text": True, "region": False, "lat": False, "lon": False, "size": False},
            custom_data=["hover_text"],
            zoom=2,
            height=500,
            color="region",
            color_discrete_map=color_map,
            size="size",
            size_max=30,
        )

        fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")
        fig.update_layout(
            autosize=True,
            margin={"t": 0, "r": 0, "b": 0, "l": 0},
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        )

        return fig

    # ---- Sub-group summary table (great_tables) ----

    @render.ui
    def sq_summary_table():
        df = data.df()
        if df is None:
            return ui.HTML("<p>暂无数据</p>")
        pl_df = _to_polars(df)
        if pl_df.height == 0:
            return ui.HTML("<p>暂无数据</p>")

        summary = _build_subgroup_summary(pl_df)
        if summary.empty:
            return ui.HTML("<p>暂无数据</p>")

        gt = _render_gt_table(summary)
        return ui.HTML(gt.as_raw_html())

    # ---- Detail table ----

    @render.data_frame
    def sq_detail_table():
        df = data.df()
        if df is None:
            return render.DataTable(pd.DataFrame())

        pd_df = df if isinstance(df, pd.DataFrame) else df.to_pandas()

        display_cols = {
            "sub_group_name": "子集团",
            "account_name": "账户户名",
            "financial_institution": "所属银行",
            "bank_city": "开户城市",
            "country_region": "国家/地区",
            "is_partner_bank": "合作银行",
            "currency": "币种",
            "balance_amount": "余额",
        }
        available = [c for c in display_cols if c in pd_df.columns]
        display_df = pd_df[available].copy()
        display_df = display_df.rename(columns={c: display_cols[c] for c in available})  # type: ignore[call-overload]

        if "余额" in display_df.columns:
            display_df["余额"] = display_df["余额"].apply(
                lambda x: f"{x:,.2f}" if pd.notna(x) else ""
            )

        display_df = display_df.sort_values("余额", ascending=False) if "余额" in display_df.columns else display_df

        return render.DataTable(
            display_df.head(500),
            styles=[
                {"cols": [i], "style": {"min-width": "120px"}}
                for i in range(min(len(display_df.columns), 8))
            ],
        )

    # ---- Export handlers ----

    @render.download(filename=_export_filename("子集团细分维度"))
    def sq_export_summary():
        df = data.df()
        if df is None:
            yield ""
            return
        pl_df = _to_polars(df)
        summary = _build_subgroup_summary(pl_df)
        yield summary.to_csv(index=False).encode("utf-8")

    @render.download(filename=_export_filename("账户明细"))
    def sq_export_detail():
        df = data.df()
        if df is None:
            yield ""
            return
        pd_df = df if isinstance(df, pd.DataFrame) else df.to_pandas()
        yield pd_df.to_csv(index=False).encode("utf-8")


# ============================================================
# Helpers
# ============================================================


def _to_polars(df):
    """Convert pandas or polars DataFrame to polars."""
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df


def _export_filename(module: str):
    """Generate export filename: 智能查询_模块名_时间戳.csv"""
    def _make():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"智能查询_{module}_{ts}.csv"
    return _make


def _build_subgroup_summary(pl_df: pl.DataFrame) -> pd.DataFrame:
    """Build sub-group level summary from filtered data, joined with financial report data."""

    agg = pl_df.group_by("sub_group_name").agg([
        pl.col("account_name").len().alias("账户数"),
        (pl.col("balance_amount").sum() / 1e8).alias("余额合计"),
        pl.col("account_name").filter(pl.col("is_partner_bank") == "合作银行").len().alias("合作银行"),
        pl.col("account_name").filter(
            (pl.col("is_partner_bank") == "非合作银行") & (pl.col("financial_institution") != "财务公司")
        ).len().alias("非合作银行"),
        pl.col("account_name").filter(pl.col("financial_institution") == "财务公司").len().alias("财务公司"),
        pl.col("account_name").filter(pl.col("is_overseas") == "境内").len().alias("境内"),
        pl.col("account_name").filter(pl.col("is_overseas") == "境外").len().alias("境外"),
    ]).sort("余额合计", descending=True)

    # Join with pre-computed financial report data
    fin = _querychat_finance_by_subgroup
    if fin.height > 0:
        agg = agg.join(
            fin.select([
                pl.col("sub_group_name"),
                (pl.col("fin_company_deposit") / 1e4).alias("财务公司存款(快报)"),
                (pl.col("commercial_bank_deposit") / 1e4).alias("商业银行存款(快报)"),
            ]),
            on="sub_group_name",
            how="left",
        ).with_columns([
            pl.col("财务公司存款(快报)").fill_null(0),
            pl.col("商业银行存款(快报)").fill_null(0),
        ])
    else:
        agg = agg.with_columns([
            pl.lit(0.0).alias("财务公司存款(快报)"),
            pl.lit(0.0).alias("商业银行存款(快报)"),
        ])

    # Rename columns for display
    agg = agg.rename({"sub_group_name": "子集团"})

    # Add ranking
    agg = agg.with_columns(pl.int_range(1, agg.height + 1).alias("排名"))

    # Reorder columns
    col_order = [
        "排名", "子集团", "账户数", "余额合计",
        "合作银行", "非合作银行", "财务公司",
        "境内", "境外", "财务公司存款(快报)", "商业银行存款(快报)",
    ]
    result = agg.select([c for c in col_order if c in agg.columns])
    return result.to_pandas()


def _render_gt_table(df: pd.DataFrame):
    """Render a great_tables GT object with formatting."""
    balance_cols = ["余额合计", "财务公司存款(快报)", "商业银行存款(快报)"]
    finance_cols = ["财务公司存款(快报)", "商业银行存款(快报)"]
    available_balance_cols = [c for c in balance_cols if c in df.columns]
    available_finance_cols = [c for c in finance_cols if c in df.columns]

    gt = (
        GT(df)
        .tab_header(
            title="子集团账户余额细分",
            subtitle=(
                f"司库数据截至 {_BALANCE_PERIOD}　　财务快报数据截至 {_FINANCE_PERIOD}"
                if _BALANCE_PERIOD and _FINANCE_PERIOD else ""
            ),
        )
        .tab_source_note(source_note="数据来源：司库账户数据 + 财务快报资产负债表")
        .cols_align(align="center", columns="排名")
        .cols_align(align="left", columns="子集团")
        .tab_style(
            style=style.text(weight="bold"),
            locations=loc.body(columns="排名"),
        )
        .tab_style(
            style=style.text(weight="bold"),
            locations=loc.body(columns="子集团"),
        )
    )

    # Number formatting + gradient for balance columns
    for col in available_balance_cols:
        gt = gt.fmt_number(columns=col, decimals=2, pattern="{x} 亿")

    if available_balance_cols:
        gt = gt.data_color(
            columns=available_balance_cols,
            domain=[0, df[available_balance_cols].max().max()],
            palette=["#f7fbff", "#08306b"],
            na_color="#ffffff",
        )

    # Compact width for financial report columns
    if available_finance_cols:
        width_map = {c: "90px" for c in available_finance_cols}
        gt = gt.cols_width(width_map)

    gt = gt.tab_options(
        table_font_size="13px",
        heading_title_font_size="18px",
        heading_subtitle_font_size="13px",
        source_notes_font_size="11px",
        table_width="100%",
        container_height="100%",
        data_row_padding="4px",
    )

    return gt

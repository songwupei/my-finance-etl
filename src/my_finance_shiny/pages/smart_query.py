"""智能查询 — AI 自然语言查司库数据。

核心: QueryChat + Claude LLM → 自动过滤数据框 → 联动 4 个可视化组件。
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import plotly.express as px
from dotenv import load_dotenv
from great_tables import GT, loc, style
from shiny import render, ui
from shinywidgets import output_widget, render_widget

from ..data import querychat_data, finance_by_subgroup, finance_period, balance_period

_ = load_dotenv()
_pages_dir = Path(__file__).parent

# ── Country centroid lookup ──
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

_QC_AVAILABLE = False
try:
    from querychat import QueryChat
    qc = QueryChat(
        querychat_data,
        "treasury_accounts",
        client="anthropic/claude-sonnet-4-5",
        greeting=_pages_dir / "smart_query_greeting.md",
        data_description=_pages_dir / "smart_query_data_description.md",
        extra_instructions=_pages_dir / "smart_query_extra_instructions.md",
    )
    _QC_AVAILABLE = True
except Exception:
    qc = None


# ── UI ──

def page():
    if not _QC_AVAILABLE:
        return ui.card(
            ui.card_header("智能查询"),
            ui.markdown("""
            ### QueryChat 未安装

            安装方法: `pip install my-finance-etl[web]`
            """),
        )

    return ui.layout_sidebar(
        qc.sidebar(),
        ui.layout_columns(
            ui.value_box("账户总数", ui.output_text("sq_total_accounts")),
            ui.value_box("余额合计", ui.output_text("sq_total_balance")),
            ui.value_box("银行类型分布", ui.output_ui("sq_bank_breakdown")),
        ),
        ui.br(),
        ui.card(ui.card_header("账户地理分布"), output_widget("sq_geo_map", fill=True), min_height="500px"),
        ui.br(),
        ui.card(
            ui.card_header(
                ui.row(ui.span("子集团细分维度"), ui.download_button("sq_export_summary", "导出 CSV"),
                       class_="d-flex justify-content-between align-items-center")
            ),
            ui.output_ui("sq_summary_table"), min_height="500px",
        ),
        ui.br(),
        ui.card(
            ui.card_header(
                ui.row(ui.span("账户明细"), ui.download_button("sq_export_detail", "导出 CSV"),
                       class_="d-flex justify-content-between align-items-center")
            ),
            ui.output_data_frame("sq_detail_table"), min_height="600px",
        ),
    )


# ── Server ──

def server(input, output, session):
    if not _QC_AVAILABLE:
        return

    data = qc.server()

    @render.text
    def sq_total_accounts():
        df = data.df()
        if df is None: return "0"
        pl_df = _to_polars(df)
        return f"{pl_df.height:,}" if pl_df.height > 0 else "0"

    @render.text
    def sq_total_balance():
        df = data.df()
        if df is None: return "0 亿"
        pl_df = _to_polars(df)
        if pl_df.height == 0: return "0 亿"
        total = pl_df["balance_amount"].sum() or 0
        yi = total / 1e8
        return f"{yi:,.2f} 亿" if yi >= 1 else f"{total / 1e4:,.2f} 万"

    @render.ui
    def sq_bank_breakdown():
        df = data.df()
        if df is None: return ui.HTML("")
        pl_df = _to_polars(df)
        if pl_df.height == 0: return ui.HTML("")
        partner_n = pl_df.filter(pl.col("is_partner_bank") == "合作银行").height
        finance_n = pl_df.filter(pl.col("financial_institution") == "财务公司").height
        non_partner_n = pl_df.filter(
            (pl.col("is_partner_bank") == "非合作银行") & (pl.col("financial_institution") != "财务公司")
        ).height
        def _badge(label, value, color):
            return ui.div(
                ui.div(label, style="font-size:11px;color:#6c757d;margin-bottom:2px"),
                ui.div(str(value), style=f"font-size:20px;font-weight:700;color:{color}"),
                style="text-align:center;flex:1",
            )
        return ui.div(
            _badge("合作银行", f"{partner_n:,}", "#5470C6"),
            ui.div(style="width:1px;background:#dee2e6;margin:0 8px"),
            _badge("非合作银行", f"{non_partner_n:,}", "#fc8452"),
            ui.div(style="width:1px;background:#dee2e6;margin:0 8px"),
            _badge("财务公司", f"{finance_n:,}", "#5d923f"),
            style="display:flex;align-items:center;justify-content:space-around;padding:8px 0",
        )

    @render_widget
    def sq_geo_map():
        df = data.df()
        if df is None: return _empty_map()
        pl_df = _to_polars(df)
        if pl_df.height == 0: return _empty_map()

        domestic = pl_df.filter(pl.col("country_region") == "中国").filter(
            pl.col("longitude").is_not_null() & pl.col("latitude").is_not_null())
        pts = []
        if domestic.height > 0:
            d_agg = domestic.group_by("bank_city").agg(
                pl.col("balance_amount").sum().alias("tb"),
                pl.col("account_name").len().alias("cnt"),
                pl.col("latitude").mean(), pl.col("longitude").mean(),
            )
            for r in d_agg.iter_rows(named=True):
                pts.append({"name": r["bank_city"], "lat": r["latitude"], "lon": r["longitude"],
                           "balance": r["tb"], "count": r["cnt"], "region": "国内"})

        overseas = pl_df.filter(pl.col("country_region") != "中国")
        if overseas.height > 0:
            o_agg = overseas.group_by("country_region").agg(
                pl.col("balance_amount").sum().alias("tb"), pl.col("account_name").len().alias("cnt"))
            for r in o_agg.iter_rows(named=True):
                coords = _COUNTRY_COORDS.get(r["country_region"])
                if coords:
                    pts.append({"name": r["country_region"], "lat": coords[0], "lon": coords[1],
                               "balance": r["tb"], "count": r["cnt"], "region": "境外"})

        if not pts: return _empty_map()
        pts_df = pd.DataFrame(pts)
        pts_df["hover_text"] = pts_df.apply(
            lambda r: f"<b>{r['name']}</b> ({r['region']})<br>余额: {r['balance']/1e8:,.2f} 亿<br>账户数: {r['count']:,}",
            axis=1)
        pts_df["size"] = pts_df["balance"].clip(1, None).apply(lambda x: max(10, min(40, np.log10(x) * 4)))

        fig = px.scatter_map(pts_df, lat="lat", lon="lon", hover_name="name",
            hover_data={"hover_text": True, "region": False, "lat": False, "lon": False, "size": False},
            custom_data=["hover_text"], zoom=2, height=500,
            color="region", color_discrete_map={"国内": "#5470C6", "境外": "#ee6666"},
            size="size", size_max=30)
        fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>")
        center_lat = float(pts_df["lat"].mean()) if len(pts_df) > 0 else 35.675
        center_lon = float(pts_df["lon"].mean()) if len(pts_df) > 0 else 104.195
        fig.update_layout(
            autosize=True,
            margin={"t":0,"r":0,"b":0,"l":0},
            map=dict(center=dict(lat=center_lat, lon=center_lon), zoom=2),
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        )
        return fig

    @render.ui
    def sq_summary_table():
        df = data.df()
        if df is None: return ui.HTML("<p>暂无数据</p>")
        pl_df = _to_polars(df)
        if pl_df.height == 0: return ui.HTML("<p>暂无数据</p>")
        summary = _build_subgroup_summary(pl_df)
        if summary.empty: return ui.HTML("<p>暂无数据</p>")
        return ui.HTML(_render_gt_table(summary).as_raw_html())

    @render.data_frame
    def sq_detail_table():
        df = data.df()
        if df is None: return render.DataTable(pd.DataFrame())
        pd_df = df if isinstance(df, pd.DataFrame) else df.to_pandas()
        cols = {"sub_group_name": "子集团", "account_name": "账户户名",
                "financial_institution": "所属银行", "bank_city": "开户城市",
                "country_region": "国家/地区", "is_partner_bank": "合作银行",
                "currency": "币种", "balance_amount": "余额"}
        avail = [c for c in cols if c in pd_df.columns]
        display = pd_df[avail].rename(columns={c: cols[c] for c in avail})
        if "余额" in display.columns:
            display["余额"] = display["余额"].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "")
        display = display.sort_values("余额", ascending=False) if "余额" in display.columns else display
        return render.DataTable(display.head(500))

    @render.download(filename=_export_filename("子集团细分维度"))
    def sq_export_summary():
        df = data.df()
        if df is None: return ""
        summary = _build_subgroup_summary(_to_polars(df))
        return summary.to_csv(index=False).encode("utf-8")

    @render.download(filename=_export_filename("账户明细"))
    def sq_export_detail():
        df = data.df()
        if df is None: return ""
        pd_df = df if isinstance(df, pd.DataFrame) else df.to_pandas()
        return pd_df.to_csv(index=False).encode("utf-8")


# ── Helpers ──

def _to_polars(df):
    if isinstance(df, pd.DataFrame): return pl.from_pandas(df)
    return df

def _export_filename(module):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"智能查询_{module}_{ts}.csv"

def _empty_map():
    """返回安全的空地图（避免 Plotly 空数据产生 NaN center 导致 JSON 序列化失败）。"""
    fig = px.scatter_map(lat=[0], lon=[0], title="暂无数据")
    fig.update_layout(
        map=dict(center=dict(lat=35.675, lon=104.195), zoom=1),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    fig.update_traces(marker=dict(size=0, opacity=0), showlegend=False)
    return fig

def _build_subgroup_summary(pl_df):
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

    fin = finance_by_subgroup
    if fin.height > 0:
        agg = agg.join(
            fin.select([pl.col("sub_group_name"),
                (pl.col("fin_company_deposit") / 1e4).alias("财务公司存款(快报)"),
                (pl.col("commercial_bank_deposit") / 1e4).alias("商业银行存款(快报)")]),
            on="sub_group_name", how="left",
        ).with_columns([
            pl.col("财务公司存款(快报)").fill_null(0),
            pl.col("商业银行存款(快报)").fill_null(0)])
    else:
        agg = agg.with_columns([
            pl.lit(0.0).alias("财务公司存款(快报)"), pl.lit(0.0).alias("商业银行存款(快报)")])

    agg = agg.rename({"sub_group_name": "子集团"})
    agg = agg.with_columns(pl.int_range(1, agg.height + 1).alias("排名"))
    col_order = ["排名", "子集团", "账户数", "余额合计", "合作银行", "非合作银行",
                 "财务公司", "境内", "境外", "财务公司存款(快报)", "商业银行存款(快报)"]
    return agg.select([c for c in col_order if c in agg.columns]).to_pandas()

def _render_gt_table(df):
    balance_cols = ["余额合计", "财务公司存款(快报)", "商业银行存款(快报)"]
    finance_cols = ["财务公司存款(快报)", "商业银行存款(快报)"]
    avail_bal = [c for c in balance_cols if c in df.columns]
    avail_fin = [c for c in finance_cols if c in df.columns]

    _fin_p = str(finance_period) if finance_period else ""
    _bal_p = str(balance_period) if balance_period else ""
    subtitle = f"司库数据截至 {_bal_p}　　财务快报数据截至 {_fin_p}" if _bal_p and _fin_p else ""

    gt = (GT(df)
        .tab_header(title="子集团账户余额细分", subtitle=subtitle)
        .tab_source_note(source_note="数据来源：司库账户数据 + 财务快报资产负债表")
        .cols_align(align="center", columns="排名")
        .cols_align(align="left", columns="子集团")
        .tab_style(style=style.text(weight="bold"), locations=loc.body(columns="排名"))
        .tab_style(style=style.text(weight="bold"), locations=loc.body(columns="子集团")))

    for col in avail_bal:
        gt = gt.fmt_number(columns=col, decimals=2, pattern="{x} 亿")

    if avail_bal:
        gt = gt.data_color(columns=avail_bal, domain=[0, df[avail_bal].max().max()],
                           palette=["#f7fbff", "#08306b"], na_color="#ffffff")

    if avail_fin:
        gt = gt.cols_width({c: "90px" for c in avail_fin})

    return gt.tab_options(table_font_size="13px", heading_title_font_size="18px",
                          heading_subtitle_font_size="13px", source_notes_font_size="11px",
                          table_width="100%", container_height="100%", data_row_padding="4px")

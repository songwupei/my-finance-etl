import os
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file, url_for
import duckdb
import yaml
import subprocess
import shutil
import time
import re
import polars as pl
import vizro.plotly.express as px
from vizro import Vizro
import vizro.models as vm
from map_utils.china_map import create_china_map_figure, add_scattermap
import numpy as np
from vizro.models.types import capture

app = Flask(__name__)

_proj_dir = Path(__file__).parent


def _get_db_path():
    params_path = _proj_dir / "conf/base/parameters.yml"
    if params_path.exists():
        with open(params_path) as f:
            params = yaml.safe_load(f)
        return str(_proj_dir / params["database"]["path"])
    return str(_proj_dir / "data/warehouse/finance.duckdb")


DB_PATH = _get_db_path()

# YAML 映射查表 — 用于 /api/node_data 匹配验证
_yaml_mapping_path = _proj_dir / "conf/base/finance_mapping_standard.yaml"
_yaml_lookup = {}  # (清理后名称, 报表分区) → {code, path, category}


def _init_yaml_lookup():
    if not _yaml_mapping_path.exists():
        return
    with open(_yaml_mapping_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for row in data.get("row_mappings", []):
        if row.get("匹配状态") == "MATCHED" and row.get("标准科目代码"):
            raw_key = re.sub(r'\s+', ' ', row.get("原始项目", "").strip())
            if raw_key and raw_key not in _yaml_lookup:
                _yaml_lookup[raw_key] = {
                    "code": row["标准科目代码"],
                    "path": row.get("标准科目路径", ""),
                    "category": row.get("报表分区", ""),
                }


_init_yaml_lookup()


def db_conn():
    return duckdb.connect(DB_PATH, read_only=True)


def _table_exists(conn, schema: str, table: str) -> bool:
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=? AND table_name=?",
            [schema, table],
        ).fetchone()
        return rows[0] > 0
    except Exception:
        return False


def _resolve_entity_id(conn, node_id, tree_period):
    row = conn.execute(
        "SELECT entity_report_id FROM finance_data.dim_organization_tree WHERE node_id = ? AND period = ?",
        [node_id, tree_period],
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT entity_report_id FROM finance_data.dim_organization_tree WHERE node_id = ? LIMIT 1",
        [node_id],
    ).fetchone()
    return row[0] if row else None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/periods")
def get_periods():
    try:
        conn = db_conn()
        periods = []
        if _table_exists(conn, "finance_data", "dim_period"):
            df = conn.execute(
                "SELECT DISTINCT period_id, period_name FROM finance_data.dim_period ORDER BY period_id DESC"
            ).fetchdf()
            for _, r in df.iterrows():
                periods.append({"period_id": r["period_id"], "period_name": r["period_name"]})
        if _table_exists(conn, "finance_data", "fact_treasury_account_balance"):
            df = conn.execute(
                "SELECT DISTINCT period, period AS period_name FROM finance_data.fact_treasury_account_balance ORDER BY period DESC"
            ).fetchdf()
            for _, r in df.iterrows():
                if r["period"] and not any(p["period_id"] == r["period"] for p in periods):
                    periods.append({"period_id": r["period"], "period_name": r["period"]})
        return jsonify(periods)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tree_periods")
def get_tree_periods():
    try:
        conn = db_conn()
        if not _table_exists(conn, "finance_data", "dim_organization_tree"):
            return jsonify([])
        df = conn.execute(
            "SELECT DISTINCT period AS period_id, period AS period_name FROM finance_data.dim_organization_tree ORDER BY period DESC"
        ).fetchdf()
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/report_categories")
def get_report_categories():
    try:
        conn = db_conn()
        if _table_exists(conn, "finance_data", "dim_standard_account"):
            df = conn.execute(
                "SELECT DISTINCT report_category FROM finance_data.dim_standard_account ORDER BY report_category"
            ).fetchdf()
            return jsonify(df.to_dict(orient="records"))
        return jsonify([])
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tree")
def get_tree():
    period = request.args.get("period")
    if not period:
        return jsonify([])
    try:
        conn = db_conn()
        if not _table_exists(conn, "finance_data", "dim_organization_tree"):
            return jsonify([])
        df = conn.execute(
            "SELECT node_id AS id, parent_id AS parent, node_name AS text FROM finance_data.dim_organization_tree WHERE period = ?",
            [period],
        ).fetchdf()
        if df.empty:
            df = conn.execute(
                "SELECT node_id AS id, parent_id AS parent, node_name AS text FROM finance_data.dim_organization_tree WHERE period = (SELECT MAX(period) FROM finance_data.dim_organization_tree)"
            ).fetchdf()
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/node_data")
def get_node_data():
    node_id = request.args.get("node_id")
    tree_period = request.args.get("tree_period", "")
    data_period = request.args.get("data_period", "")
    if not node_id or not data_period:
        return jsonify([])
    try:
        conn = db_conn()
        if not _table_exists(conn, "finance_data", "dim_organization_tree"):
            return jsonify([])
        entity_id = _resolve_entity_id(conn, node_id, tree_period)
        if not entity_id:
            return jsonify([])
        if not _table_exists(conn, "finance_data", "fact_finance_data"):
            return jsonify([])
        df = conn.execute(
            """
            SELECT
                f.raw_path AS "原始指标名称",
                COALESCE(sa.standard_path, sa.account_name) AS "标准路径",
                COALESCE(SUM(CASE WHEN f.value_column = '本月数' THEN f.value ELSE NULL END), 0.0) AS "本月数",
                COALESCE(SUM(CASE WHEN f.value_column = '上年同期' THEN f.value ELSE NULL END), 0.0) AS "上年同期",
                COALESCE(SUM(CASE WHEN f.value_column = '本年累计' THEN f.value ELSE NULL END), 0.0) AS "本年累计",
                sa.report_category AS "报表类别",
                sa.account_name AS "指标名称",
                sa.account_code AS "标准科目代码"
            FROM finance_data.fact_finance_data f
            JOIN finance_data.dim_report_category rc ON f.category_id = rc.category_id
            JOIN finance_data.dim_standard_account sa
                ON f.account_code = sa.account_code AND rc.category_name = sa.report_category
            WHERE f.entity_report_id = ? AND f.period_id = ?
            GROUP BY
                sa.account_name,
                COALESCE(sa.standard_path, sa.account_name),
                f.raw_path,
                sa.report_category,
                sa.account_code,
                sa.sort_order
            ORDER BY sa.sort_order, sa.account_code
            """,
            [entity_id, data_period],
        ).fetchdf()
        records = df.to_dict(orient="records")
        for r in records:
            std_top = r.get("指标名称", "")
            raw_path = r.get("原始指标名称", "")
            raw_top = raw_path.split(">")[0].strip() if raw_path else ""
            r["标准对比键"] = std_top
            r["原始对比键"] = raw_top

            # 用原始指标名称直接查 YAML（规范化空格）
            raw_key = re.sub(r'\s+', ' ', raw_path.strip())
            yaml_match = _yaml_lookup.get(raw_key)
            if not yaml_match:
                # 回退：用 raw_top（第一段）查
                raw_top_key = re.sub(r'\s+', ' ', raw_top.strip())
                yaml_match = _yaml_lookup.get(raw_top_key)

            if yaml_match:
                actual_code = r.get("标准科目代码", "")
                r["是否匹配"] = (yaml_match["code"] == actual_code)
            else:
                # YAML 中不存在的项目（如分析指标），直接显示匹配
                r["是否匹配"] = True
        return jsonify(records)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/time_options")
def get_time_options():
    try:
        conn = db_conn()
        options = []
        if _table_exists(conn, "finance_data", "fact_finance_data"):
            df = conn.execute(
                "SELECT DISTINCT period_id FROM finance_data.fact_finance_data ORDER BY period_id DESC"
            ).fetchdf()
            options.extend(df["period_id"].tolist())
        if _table_exists(conn, "finance_data", "fact_treasury_account_balance"):
            df = conn.execute(
                "SELECT DISTINCT period FROM finance_data.fact_treasury_account_balance ORDER BY period DESC"
            ).fetchdf()
            for p in df["period"].tolist():
                if p and p not in options:
                    options.append(p)
        return jsonify({"success": True, "options": options})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/treasury_data")
def get_treasury_data():
    node_id = request.args.get("node_id")
    tree_period = request.args.get("tree_period", "")
    data_period = request.args.get("data_period", "")
    if not node_id or not data_period:
        return jsonify([])
    try:
        conn = db_conn()
        if not _table_exists(conn, "finance_data", "dim_organization_tree"):
            return jsonify([])
        entity_id = _resolve_entity_id(conn, node_id, tree_period)
        if not entity_id:
            return jsonify([])
        if not _table_exists(conn, "finance_data", "fact_treasury_account_balance"):
            return jsonify([])
        df = conn.execute(
            """
            SELECT
                ta.account_number AS "账户编号",
                ta.account_name AS "账户名称",
                ta.opening_institution AS "开户银行",
                tat.type_label AS "账户类型",
                ta.currency AS "币种",
                fb.balance_amount AS "期末余额",
                fb.converted_amount AS "可用余额",
                fb.balance_date AS "余额日期",
                ta.is_partner_bank AS "是否合作银行",
                ta.is_overseas AS "是否境外账户",
                ta.account_nature AS "账户性质"
            FROM finance_data.fact_treasury_account_balance fb
            JOIN finance_data.dim_treasury_account ta ON fb.account_id = ta.account_id
            LEFT JOIN finance_data.dim_treasury_account_type tat ON ta.type_id = tat.type_id
            WHERE fb.entity_report_id = ? AND fb.period = ?
            ORDER BY ta.opening_institution, ta.account_number
            """,
            [entity_id, data_period],
        ).fetchdf()
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/treasury_business_types")
def get_treasury_business_types():
    return jsonify([
        {"value": "account", "label": "账户情况表"},
    ])


# --------------- 报告生成部分 ---------------

@app.route("/api/generate_report")
def generate_report():
    # TODO(work): 暂时忽略日期参数，后续恢复
    # year = request.args.get("year", type=int)
    # month = request.args.get("month", type=int)
    # day = request.args.get("day", type=int)
    # if not all([year, month, day]):
    #     return jsonify({"success": False, "error": "缺少日期参数"}), 400

    qmd_template = Path("/home/song/NutstoreFiles/5-Quartools/PrettyDoc/SiKuReport/daily_report_account-gb.qmd")
    if not qmd_template.exists():
        return jsonify({"success": False, "error": "日报模板文件不存在"}), 400

    output_dir = _proj_dir / "generated_reports"
    output_dir.mkdir(exist_ok=True)

    # TODO(work): 日期参数暂忽略，basename 仅用时间戳
    timestamp = int(time.time())
    report_basename = f"daily_report_{timestamp}"

    cmd = [
        "micromamba", "run", "-n", "quarto", "bash", "-c",
        "cd /home/song/NutstoreFiles/5-Quartools/PrettyDoc && quarto render SiKuReport/daily_report_account-gb.qmd"
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        # quarto 输出在 PrettyDoc/_output/SiKuReport/，复制到 generated_reports
        quarto_pdf = Path("/home/song/NutstoreFiles/5-Quartools/PrettyDoc/_output/SiKuReport/daily_report_account-gb.pdf")
        if not quarto_pdf.exists():
            raise FileNotFoundError("PDF 生成失败，quarto 未输出文件")
        dest_pdf = output_dir / (report_basename + ".pdf")
        shutil.copy(quarto_pdf, dest_pdf)
        # 同时复制 docx
        quarto_docx = Path("/home/song/NutstoreFiles/5-Quartools/PrettyDoc/_output/SiKuReport/daily_report_account-gb.docx")
        if quarto_docx.exists():
            shutil.copy(quarto_docx, output_dir / (report_basename + ".docx"))
        download_url = url_for("download_report", filename=dest_pdf.name)
        return jsonify({"success": True, "url": download_url})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": e.stderr}), 500


@app.route("/download_report/<filename>")
def download_report(filename):
    file_path = _proj_dir / "generated_reports" / filename
    if not file_path.exists():
        return "文件不存在", 404
    return send_file(file_path, as_attachment=True)


# --------------- 地图数据 API ---------------

@app.route("/api/units_geo")
def get_units_geo():
    """返回所有有经纬度的单位 + 财务摘要。"""
    try:
        conn = db_conn()
        if not all(
            _table_exists(conn, "finance_data", t)
            for t in ["dim_unit_report", "dim_unit_geo", "fact_finance_data"]
        ):
            return jsonify([])
        df = conn.execute("""
            WITH latest_unit AS (
                SELECT DISTINCT ON (entity_report_id) *
                FROM finance_data.dim_unit_report
                ORDER BY entity_report_id, period DESC
            )
            SELECT
                u.entity_report_id,
                u.unit_name,
                u.province,
                u.city,
                u.area,
                g.longitude,
                g.latitude,
                u.enterprise_address,
                u.sasac_area_name,
                COALESCE(SUM(CASE WHEN f.value_column = '本年累计' AND f.account_code = '01'
                             THEN f.value END), 0) AS total_assets
            FROM latest_unit u
            JOIN finance_data.dim_unit_geo g
                ON u.entity_report_id = g.entity_report_id
            LEFT JOIN finance_data.fact_finance_data f
                ON u.entity_report_id = f.entity_report_id AND f.period_id = (SELECT MAX(period_id) FROM finance_data.fact_finance_data)
            WHERE g.longitude IS NOT NULL
            GROUP BY u.entity_report_id, u.unit_name, u.province, u.city, u.area,
                     g.longitude, g.latitude, u.enterprise_address, u.sasac_area_name
        """).fetchdf()
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --------------- Vizro 仪表板 ---------------

_vizro_db = _get_db_path()
_vizro_con = duckdb.connect(_vizro_db, read_only=True)

# 图1：资产负债气泡散点 — 资产(x) vs 负债(y)，气泡=账户数
_vizro_df1 = _vizro_con.execute("""
    WITH asset_liability AS (
        SELECT
            f.entity_report_id,
            f.period_id AS 期间,
            COALESCE(ot.node_name, f.entity_report_id) AS 单位名称,
            SUM(CASE WHEN sa.account_code = '01' THEN f.value END) AS 资产总额,
            SUM(CASE WHEN sa.account_code = '02' THEN f.value END) AS 负债总额
        FROM finance_data.fact_finance_data f
        JOIN finance_data.dim_standard_account sa ON f.account_code = sa.account_code
        JOIN finance_data.dim_report_category rc ON f.category_id = rc.category_id
        LEFT JOIN finance_data.dim_organization_tree ot
            ON f.entity_report_id = ot.entity_report_id AND ot.period = f.period_id
        WHERE rc.category_name = '资产负债表'
          AND sa.account_code IN ('01', '02')
          AND f.value_column = '本年累计'
        GROUP BY f.entity_report_id, 期间, ot.node_name
        HAVING "资产总额" > 0 AND "负债总额" > 0
    ),
    account_count AS (
        SELECT entity_report_id, COUNT(DISTINCT account_id) AS 账户数
        FROM finance_data.dim_treasury_account
        WHERE account_status = '存续'
        GROUP BY entity_report_id
    )
    SELECT
        al.*,
        COALESCE(ac.账户数, 0) AS 账户数,
        al.负债总额 / NULLIF(al.资产总额, 0) AS 资产负债率
    FROM asset_liability al
    LEFT JOIN account_count ac ON al.entity_report_id = ac.entity_report_id
""").fetchdf()

# 过滤差额(1)和合并(9)单位
_exclude_ids = _vizro_con.execute("""
    SELECT DISTINCT entity_report_id FROM finance_data.dim_unit_report WHERE suffix IN ('1', '9')
""").fetchdf()
if not _exclude_ids.empty:
    _exclude_set = set(_exclude_ids.iloc[:, 0])
    _vizro_df1 = _vizro_df1[~_vizro_df1["entity_report_id"].isin(_exclude_set)]

# 只保留每个单位最新期间的数据
_vizro_df1 = _vizro_df1.sort_values("期间").groupby("entity_report_id").last().reset_index()

_vizro_df1["log10_资产总额"] = np.log10(_vizro_df1["资产总额"])
_vizro_df1["log10_负债总额"] = np.log10(_vizro_df1["负债总额"])
_vizro_df1["log10_账户数"] = np.log10(_vizro_df1["账户数"].clip(lower=1))
_vizro_df1["资产总额_万"] = _vizro_df1["资产总额"]
_vizro_df1["负债总额_万"] = _vizro_df1["负债总额"]

import plotly.graph_objects as go

@capture("graph")
def asset_liability_bubble(data_frame=_vizro_df1):
    """图A：资产负债气泡散点 — 资产(x) vs 负债(y)，气泡=账户数"""
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
    """图B：杠杆率 vs 账户规模（颜色=资产规模，正常区间 30-80%）"""
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

# 图3：中国地图 — 单位地理分布 + 资产规模
# 自动处理 geo 数据：缺失时调用 geocoder，缺表时从 Parquet 补同步
_geo_parquet = _proj_dir / "data/03_primary/dim_unit_geo.parquet"
try:
    from my_finance_etl.geocoder import run as run_geocoder
    if not _geo_parquet.exists():
        run_geocoder()

    # 同步 parquet → DuckDB（_vizro_con 是只读的，得用独立可写连接）
    _sync_conn = duckdb.connect(_vizro_db)  # 可写连接
    try:
        if not _table_exists(_sync_conn, "finance_data", "dim_unit_geo"):
            import polars as pl
            geo_df = pl.read_parquet(str(_geo_parquet))
            _sync_conn.register("_geo", geo_df.to_pandas())
            _sync_conn.execute(
                "CREATE TABLE IF NOT EXISTS finance_data.dim_unit_geo AS SELECT * FROM _geo"
            )
            print(f"[flask] Synced {geo_df.height} geo rows to DuckDB from parquet")
    finally:
        _sync_conn.close()
except Exception as e:
    print(f"[flask] Geo sync failed: {e}")

_vizro_geo_data = pl.DataFrame()
try:
    _vizro_geo_data = _vizro_con.execute("""
        WITH latest_unit AS (
            SELECT DISTINCT ON (entity_report_id) *
            FROM finance_data.dim_unit_report
            ORDER BY entity_report_id, period DESC
        )
        SELECT
            u.unit_name,
            u.province,
            u.city,
            u.enterprise_address,
            g.longitude,
            g.latitude,
            COALESCE(SUM(CASE WHEN f.value_column = '本年累计' AND f.account_code = '01'
                         THEN f.value END), 0) AS total_assets,
            COALESCE(SUM(CASE WHEN f.value_column = '本年累计' AND f.account_code = '54'
                         THEN f.value END), 0) AS total_revenue
        FROM latest_unit u
        JOIN finance_data.dim_unit_geo g
            ON u.entity_report_id = g.entity_report_id
        LEFT JOIN finance_data.fact_finance_data f
            ON u.entity_report_id = f.entity_report_id
           AND f.period_id = (SELECT MAX(period_id) FROM finance_data.fact_finance_data)
        WHERE g.longitude IS NOT NULL AND u.suffix NOT IN ('1', '9')
        GROUP BY u.entity_report_id, u.unit_name, u.province, u.city,
                 u.enterprise_address, g.longitude, g.latitude
    """).fetchdf()
except Exception:
    pass

_vizro_geo_fig = None
if _vizro_geo_data.shape[0] > 0:
    _vizro_geo_data["size_scaled"] = np.log10(_vizro_geo_data["total_assets"].clip(lower=1))
    _vizro_geo_data["hover_text"] = (
        _vizro_geo_data["unit_name"] + "<br>" +
        _vizro_geo_data["enterprise_address"].fillna("").str.strip() + "<br>" +
        "资产总额: " + _vizro_geo_data["total_assets"].apply(lambda x: f"{x:,.0f}万元")
    )

    import plotly.graph_objects as go

    _map_cfg = yaml.safe_load(open(_proj_dir / "conf/base/parameters.yml")).get("map", {})
    @capture("graph")
    def geo_map(data_frame=_vizro_geo_data):
        data_frame = data_frame.copy()
        data_frame["size_scaled"] = data_frame["total_assets"]/10000
        data_frame["hover_text"] = (
            data_frame["unit_name"] + "<br>" +
            data_frame["enterprise_address"].fillna("").str.strip() + "<br>" +
            "资产总额: " + data_frame["total_assets"].apply(lambda x: f"{x:,.0f}万元")
        )
        provider = _map_cfg.get("provider", "gaode")
        fig = create_china_map_figure(
            provider=provider,
            tile_type="vec",
            center_lon=_map_cfg.get("center_lon", 104.195),
            center_lat=_map_cfg.get("center_lat", 35.675),
            zoom=_map_cfg.get("zoom", 3),
            height=_map_cfg.get("height", 800),
            title="成员单位地理分布")
        add_scattermap(
            fig, provider,
            lat=data_frame["latitude"].to_list(),
            lon=data_frame["longitude"].to_list(),
            mode="markers",
            marker=dict(
                size=data_frame["size_scaled"].clip(lower=3),
                color=np.log10(data_frame["total_assets"].clip(lower=1)),
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(
                    title="资产总额 (人民币元)",
                    tickvals=[1,2,3,4,5,6],
                    ticktext=["10", "100", "1,000", "1万", "10万", "100万"],
                ),
                sizemin=3, sizemode="area",
                opacity=0.7, symbol="circle",
            ),
            text=data_frame["hover_text"].to_list(),
            hoverinfo="text",
        )
        fig.update_layout(
            xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
            yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        return fig

    _vizro_geo_fig = geo_map(data_frame=_vizro_geo_data)

_vizro_page_map_components = [vm.Graph(figure=_vizro_geo_fig)] if _vizro_geo_fig is not None else [vm.Card(text="地理分布 — 等待地理编码数据")]
_vizro_page_map = vm.Page(
    id="china-map",
    title="地理分布",
    components=_vizro_page_map_components,
)

_vizro_navigation = vm.Navigation(
    pages={
        "首页": ["penetration-monitor"],
        "分析": ["relationship-analysis"],
        "概览": ["overview"],
        "地图": ["china-map"],
    },
    nav_selector=vm.NavBar(),
)

_vizro_dashboard = vm.Dashboard(
    pages=[_vizro_page_monitor, _vizro_page_relationship, _vizro_page_overview, _vizro_page_map],
    navigation=_vizro_navigation,
)
_vizro = Vizro(server=app, url_base_pathname='/vizro/')
_vizro.build(_vizro_dashboard)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)

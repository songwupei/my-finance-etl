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
import pandas as pd
import vizro.plotly.express as px
from vizro import Vizro
import vizro.models as vm
from map_utils.china_map import create_china_map_figure, add_scattermap
import numpy as np
from vizro.models.types import capture
from vizro.tables import dash_ag_grid

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

def _get_email_config():
    params_path = _proj_dir / "conf/base/parameters.yml"
    if params_path.exists():
        with open(params_path) as f:
            params = yaml.safe_load(f)
        return params.get("email", {})
    return {}

_QUARTO_PDF = Path("/home/song/NutstoreFiles/5-Quartools/PrettyDoc/_output/SiKuReport/daily_report_account-gb.pdf")
_SEND_SCRIPT = Path("/home/song/NutstoreFiles/5-Quartools/app_py/sync_files/hooks/treasury_daily.sh")


def _pdf_exists():
    return _QUARTO_PDF.exists()


@app.route("/api/generate_report")
def generate_report():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    day = request.args.get("day", type=int)
    if not all([year, month, day]):
        return jsonify({"success": False, "error": "缺少日期参数 year/month/day"}), 400

    qmd_template = Path("/home/song/NutstoreFiles/5-Quartools/PrettyDoc/SiKuReport/daily_report_account-gb.qmd")
    if not qmd_template.exists():
        return jsonify({"success": False, "error": "日报模板文件不存在"}), 400

    output_dir = _proj_dir / "generated_reports"
    output_dir.mkdir(exist_ok=True)

    report_basename = f"daily_report_{year}{month:02d}{day:02d}"

    cmd = [
        "micromamba", "run", "-n", "quarto", "bash", "-c",
        f"cd /home/song/NutstoreFiles/5-Quartools/PrettyDoc && quarto render SiKuReport/daily_report_account-gb.qmd -P year:{year} -P month:{month} -P day:{day}"
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


@app.route("/api/send_report")
def send_report():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    day = request.args.get("day", type=int)
    if not all([year, month, day]):
        return jsonify({"success": False, "error": "缺少日期参数 year/month/day"}), 400

    generated = False
    # 如果 PDF 不存在，先自动生成
    if not _pdf_exists():
        qmd_template = Path("/home/song/NutstoreFiles/5-Quartools/PrettyDoc/SiKuReport/daily_report_account-gb.qmd")
        if not qmd_template.exists():
            return jsonify({"success": False, "error": "日报模板文件不存在"}), 400

        output_dir = _proj_dir / "generated_reports"
        output_dir.mkdir(exist_ok=True)
        report_basename = f"daily_report_{year}{month:02d}{day:02d}"

        cmd = [
            "micromamba", "run", "-n", "quarto", "bash", "-c",
            f"cd /home/song/NutstoreFiles/5-Quartools/PrettyDoc && quarto render SiKuReport/daily_report_account-gb.qmd -P year:{year} -P month:{month} -P day:{day}"
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            quarto_pdf = _QUARTO_PDF
            if not quarto_pdf.exists():
                raise FileNotFoundError("PDF 生成失败，quarto 未输出文件")
            dest_pdf = output_dir / (report_basename + ".pdf")
            shutil.copy(quarto_pdf, dest_pdf)
            quarto_docx = Path("/home/song/NutstoreFiles/5-Quartools/PrettyDoc/_output/SiKuReport/daily_report_account-gb.docx")
            if quarto_docx.exists():
                shutil.copy(quarto_docx, output_dir / (report_basename + ".docx"))
            generated = True
        except subprocess.CalledProcessError as e:
            return jsonify({"success": False, "error": e.stderr}), 500
        except FileNotFoundError as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # 调用 shell 脚本发送邮件
    try:
        email_cfg = _get_email_config()
        env = os.environ.copy()
        if email_cfg.get("from"):
            env["EMAIL_FROM"] = email_cfg["from"]
        if email_cfg.get("to"):
            env["EMAIL_TO"] = email_cfg["to"]
        if email_cfg.get("subject_prefix"):
            env["EMAIL_SUBJECT_PREFIX"] = email_cfg["subject_prefix"]
        result = subprocess.run(
            ["bash", str(_SEND_SCRIPT), "--send-only"],
            capture_output=True, text=True, check=True,
            env=env,
        )
        return jsonify({
            "success": True,
            "generated": generated,
            "to": email_cfg.get("to", ""),
            "message": result.stdout.strip() if result.stdout else "",
        })
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": e.stderr or "邮件发送失败"}), 500


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

_vizro_page_home = vm.Page(
    id="home",
    title="HOME",
    components=[
        vm.Card(text="""
        # 财务数据 ETL 仪表板

        欢迎使用财务数据分析平台。

        - **穿透监控**：资产负债结构气泡图、杠杆率 vs 账户规模
        - **地理分布**：成员单位全国地图分布
        - **关系分析**：关联关系分析
        - **概览**：数据概览
        """),
    ],
)

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
# 优先从 Parquet 同步 dim_unit_geo 到 DuckDB（pipeline 已写入 parquet）
_geo_parquet = _proj_dir / "data/03_primary/dim_unit_geo.parquet"
try:
    if _geo_parquet.exists():
        _sync_conn = duckdb.connect(_vizro_db)  # 可写连接
        try:
            import polars as pl
            geo_df = pl.read_parquet(str(_geo_parquet))
            if not geo_df.is_empty():
                _sync_conn.register("_geo", geo_df.to_pandas())
                _sync_conn.execute(
                    "CREATE OR REPLACE TABLE IF NOT EXISTS finance_data.dim_unit_geo AS SELECT * FROM _geo"
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

# ---------- 图3：单位地理分布 ----------
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

# v1.3: 账户地图 (带筛选) — 四维筛选 + 省份→城市级联
#
# 数据: 账户级粒度, @capture 内按网点动态聚合, Vizro Filter 自动过滤
# 筛选: 子集团 / 所属银行 / 地区 (Dropdown 多选)
# 气泡: 大小 = log10(余额)**2 * 2, 颜色 = 合计余额 (YlOrBr 浅→深)
_bank_map_account_data = pl.DataFrame()
try:
    _bank_map_account_data = _vizro_con.execute("""
        SELECT
            ta.institution_code,
            ta.sub_group_name,
            ta.account_name,
            COALESCE(NULLIF(ta.financial_institution, ''), '未知银行') AS financial_institution,
            COALESCE(NULLIF(ta.bank_city, ''), '未知城市') AS bank_city,
            fb.balance_amount,
            bb.opening_institution AS branch_name,
            bb.longitude,
            bb.latitude,
            bb.formatted_address
        FROM finance_data.fact_treasury_account_balance fb
        JOIN finance_data.dim_treasury_account ta ON fb.account_id = ta.account_id
        JOIN finance_data.dim_bank_branch bb ON ta.institution_code = bb.institution_code
        WHERE fb.period = (SELECT MAX(period) FROM finance_data.fact_treasury_account_balance)
          AND ta.account_status = '存续'
          AND fb.balance_amount > 0
          AND bb.longitude IS NOT NULL
          AND bb.financial_institution != '财务公司'
    """).fetchdf()
except Exception:
    pass

# 城市→省份映射 (覆盖34个省级行政区的188个城市)
_CITY_PROVINCE = {
    "北京市": "北京市", "上海市": "上海市", "天津市": "天津市", "重庆市": "重庆市",
    "石家庄市": "河北省", "唐山市": "河北省", "秦皇岛市": "河北省", "邯郸市": "河北省", "邢台市": "河北省", "保定市": "河北省", "张家口市": "河北省", "承德市": "河北省", "沧州市": "河北省", "廊坊市": "河北省", "衡水市": "河北省", "雄安新区": "河北省",
    "太原市": "山西省", "大同市": "山西省", "阳泉市": "山西省", "长治市": "山西省", "晋城市": "山西省", "朔州市": "山西省", "晋中市": "山西省", "运城市": "山西省", "临汾市": "山西省", "吕梁市": "山西省",
    "呼和浩特市": "内蒙古自治区", "包头市": "内蒙古自治区", "乌海市": "内蒙古自治区", "赤峰市": "内蒙古自治区", "鄂尔多斯市": "内蒙古自治区", "巴彦淖尔市": "内蒙古自治区", "阿拉善盟": "内蒙古自治区", "锡林郭勒盟": "内蒙古自治区",
    "沈阳市": "辽宁省", "大连市": "辽宁省", "鞍山市": "辽宁省", "抚顺市": "辽宁省", "锦州市": "辽宁省", "营口市": "辽宁省", "辽阳市": "辽宁省", "盘锦市": "辽宁省", "朝阳市": "辽宁省", "葫芦岛市": "辽宁省",
    "长春市": "吉林省", "吉林市": "吉林省", "通化市": "吉林省", "白城市": "吉林省",
    "哈尔滨市": "黑龙江省", "齐齐哈尔市": "黑龙江省", "鸡西市": "黑龙江省", "鹤岗市": "黑龙江省", "大庆市": "黑龙江省", "牡丹江市": "黑龙江省", "绥化市": "黑龙江省",
    "南京市": "江苏省", "无锡市": "江苏省", "徐州市": "江苏省", "苏州市": "江苏省", "南通市": "江苏省", "连云港市": "江苏省", "淮安市": "江苏省", "盐城市": "江苏省", "扬州市": "江苏省", "泰州市": "江苏省",
    "杭州市": "浙江省", "宁波市": "浙江省", "嘉兴市": "浙江省", "金华市": "浙江省", "台州市": "浙江省",
    "合肥市": "安徽省", "芜湖市": "安徽省", "蚌埠市": "安徽省", "马鞍山市": "安徽省", "安庆市": "安徽省", "滁州市": "安徽省", "六安市": "安徽省", "池州市": "安徽省", "宣城市": "安徽省", "巢湖市": "安徽省",
    "福州市": "福建省", "厦门市": "福建省", "泉州市": "福建省", "漳州市": "福建省", "宁德市": "福建省",
    "南昌市": "江西省", "九江市": "江西省", "赣州市": "江西省", "吉安市": "江西省", "宜春市": "江西省",
    "济南市": "山东省", "青岛市": "山东省", "淄博市": "山东省", "烟台市": "山东省", "潍坊市": "山东省", "泰安市": "山东省", "威海市": "山东省",
    "郑州市": "河南省", "开封市": "河南省", "洛阳市": "河南省", "平顶山市": "河南省", "新乡市": "河南省", "焦作市": "河南省", "三门峡市": "河南省", "南阳市": "河南省", "信阳市": "河南省", "驻马店市": "河南省",
    "武汉市": "湖北省", "黄石市": "湖北省", "十堰市": "湖北省", "宜昌市": "湖北省", "襄阳市": "湖北省", "襄樊市": "湖北省", "孝感市": "湖北省", "黄冈市": "湖北省", "咸宁市": "湖北省", "随州市": "湖北省", "潜江市": "湖北省",
    "长沙市": "湖南省", "湘潭市": "湖南省", "衡阳市": "湖南省", "常德市": "湖南省", "怀化市": "湖南省",
    "广州市": "广东省", "深圳市": "广东省", "珠海市": "广东省", "佛山市": "广东省", "湛江市": "广东省", "惠州市": "广东省", "东莞市": "广东省", "揭阳市": "广东省",
    "南宁市": "广西壮族自治区", "柳州市": "广西壮族自治区", "桂林市": "广西壮族自治区", "梧州市": "广西壮族自治区", "防城港市": "广西壮族自治区", "钦州市": "广西壮族自治区", "贵港市": "广西壮族自治区", "玉林市": "广西壮族自治区", "百色市": "广西壮族自治区", "贺州市": "广西壮族自治区", "河池市": "广西壮族自治区", "来宾市": "广西壮族自治区", "崇左市": "广西壮族自治区",
    "海口市": "海南省", "三亚市": "海南省",
    "成都市": "四川省", "绵阳市": "四川省", "泸州市": "四川省", "德阳市": "四川省", "内江市": "四川省", "乐山市": "四川省", "南充市": "四川省", "宜宾市": "四川省", "雅安市": "四川省", "凉山彝族自治州": "四川省", "甘孜藏族自治州": "四川省",
    "贵阳市": "贵州省", "安顺市": "贵州省", "黔南布依族苗族自治州": "贵州省",
    "昆明市": "云南省", "曲靖市": "云南省", "玉溪市": "云南省", "普洱市": "云南省", "迪庆藏族自治州": "云南省",
    "拉萨市": "西藏自治区", "林芝市": "西藏自治区", "林芝地区": "西藏自治区", "阿里地区": "西藏自治区",
    "西安市": "陕西省", "铜川市": "陕西省", "宝鸡市": "陕西省", "咸阳市": "陕西省", "渭南市": "陕西省", "延安市": "陕西省", "榆林市": "陕西省", "安康市": "陕西省", "商洛市": "陕西省",
    "兰州市": "甘肃省", "白银市": "甘肃省", "酒泉市": "甘肃省",
    "西宁市": "青海省", "海西蒙古族藏族自治州": "青海省",
    "银川市": "宁夏回族自治区", "固原市": "宁夏回族自治区",
    "乌鲁木齐市": "新疆维吾尔自治区", "克拉玛依市": "新疆维吾尔自治区", "吐鲁番地区": "新疆维吾尔自治区", "哈密地区": "新疆维吾尔自治区", "阿克苏地区": "新疆维吾尔自治区", "喀什地区": "新疆维吾尔自治区", "和田地区": "新疆维吾尔自治区", "塔城地区": "新疆维吾尔自治区", "克孜勒苏柯尔克孜自治州": "新疆维吾尔自治区", "昌吉回族自治州": "新疆维吾尔自治区", "巴音郭楞蒙古自治州": "新疆维吾尔自治区", "伊犁哈萨克自治州": "新疆维吾尔自治区",
}
if _bank_map_account_data.shape[0] > 0:
    _bank_map_account_data["province"] = _bank_map_account_data["bank_city"].map(_CITY_PROVINCE).fillna("其他")

_account_detail_df = None
if _bank_map_account_data.shape[0] > 0:
    _account_detail_df = _bank_map_account_data[[
        "sub_group_name", "account_name", "financial_institution",
        "bank_city", "province", "branch_name", "balance_amount",
    ]].sort_values("balance_amount", ascending=False)

_account_detail_column_defs = [
    {"field": "sub_group_name", "headerName": "子集团"},
    {"field": "account_name", "headerName": "账户户名"},
    {"field": "financial_institution", "headerName": "所属银行"},
    {"field": "bank_city", "headerName": "城市"},
    {"field": "province", "headerName": "省份"},
    {"field": "balance_amount", "headerName": "余额"},
    {"field": "branch_name", "headerName": "开户网点"},
]

_vizro_page_account_detail = vm.Page(
    id="account-detail",
    title="账户明细表",
    components=[
        vm.AgGrid(
            figure=dash_ag_grid(
                data_frame=_account_detail_df,
                dashGridOptions={"pagination": True, "domLayout": "autoHeight",
                                 "columnDefs": _account_detail_column_defs},
            ),
            title="账户明细表",
        ),
    ],
)

_map_cfg = yaml.safe_load(open(_proj_dir / "conf/base/parameters.yml")).get("map", {})


@capture("graph")
def bank_account_map(data_frame=None):
    if data_frame is None:
        data_frame = _bank_map_account_data
    data_frame = data_frame.copy()

    # 按网点聚合
    agg = data_frame.groupby([
        "institution_code", "branch_name", "financial_institution",
        "longitude", "latitude", "formatted_address"
    ], dropna=False).agg(
        total_balance=("balance_amount", "sum"),
        account_count=("balance_amount", "count"),
    ).reset_index()

    # 子集团余额明细 (由高到低)
    sg_agg = data_frame.groupby(["institution_code", "sub_group_name"], dropna=False).agg(
        sg_balance=("balance_amount", "sum")
    ).reset_index()
    sg_agg["sg_text"] = (
        sg_agg["sub_group_name"] + ": "
        + (sg_agg["sg_balance"] / 10000).apply(lambda x: f"{x:,.0f}万元")
    )
    # 按网点内子集团余额降序排列
    sg_order = sg_agg.sort_values(
        ["institution_code", "sg_balance"], ascending=[True, False]
    )
    sg_breakdown = sg_order.groupby("institution_code", sort=False).agg(
        subgroup_breakdown=("sg_text", lambda x: "<br>".join(x))
    ).reset_index()

    agg = agg.merge(sg_breakdown, on="institution_code", how="left")
    agg["subgroup_breakdown"] = agg["subgroup_breakdown"].fillna("")

    _max = agg["total_balance"].max() if agg.shape[0] > 0 else 1
    agg["size_scaled"] = np.log10(agg["total_balance"].clip(lower=1))**2 * 2
    agg["hover_text"] = (
        agg["branch_name"] + "<br>"
        + "所属银行: " + agg["financial_institution"] + "<br>"
        + "账户数: " + agg["account_count"].apply(lambda x: f"{x:,}个")
        + " | 合计余额: " + agg["total_balance"].apply(lambda x: f"{x/10000:,.0f}万元")
        + "<br><br><b>子集团余额明细:</b><br>" + agg["subgroup_breakdown"]
    )

    provider = _map_cfg.get("provider", "gaode")
    fig = create_china_map_figure(
        provider=provider, tile_type="vec",
        center_lon=_map_cfg.get("center_lon", 104.195),
        center_lat=_map_cfg.get("center_lat", 35.675),
        zoom=_map_cfg.get("zoom", 3),
        height=_map_cfg.get("height", 800),
        title="银行账户地理分布")

    _step = _max / 5 if _max > 0 else 1
    _ticks = [_step * i for i in range(6)]
    add_scattermap(
        fig, provider,
        lat=agg["latitude"].to_list(),
        lon=agg["longitude"].to_list(),
        mode="markers",
        marker=dict(
            size=agg["size_scaled"].clip(lower=3),
            color=agg["total_balance"],
            colorscale="Viridis",
            # colorscale="Viridis_r",
            showscale=True,
            colorbar=dict(
                title="合计余额 (万元)",
                tickvals=_ticks,
                ticktext=[f"{v/10000:,.0f}" for v in _ticks],
            ),
            sizemin=3, sizemode="area",
            opacity=0.7, symbol="circle",
        ),
        text=agg["hover_text"].to_list(),
        hoverinfo="text",
    )
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    return fig


_vizro_page_bank_map = vm.Page(
    id="bank-account-map",
    title="账户地图",
    components=[
        vm.Graph(
            id="bank-map-graph",
            figure=bank_account_map(data_frame=_bank_map_account_data),
        ),
        vm.AgGrid(
            id="clicked-branch-table",
            figure=dash_ag_grid(
                data_frame=_account_detail_df,
                dashGridOptions={"pagination": True, "domLayout": "autoHeight",
                                 "columnDefs": _account_detail_column_defs},
            ),
            title="点击气泡筛选此表",
        ),
    ],
    controls=[
        vm.Filter(column="sub_group_name",
                  selector=vm.Dropdown(id="sg-filter", title="子集团", multi=True)),
        vm.Filter(column="financial_institution",
                  selector=vm.Dropdown(id="bank-filter", title="所属银行", multi=True)),
        vm.Filter(column="province",
                  selector=vm.Dropdown(id="prov-filter", title="省份", multi=True)),
        vm.Filter(column="bank_city",
                  selector=vm.Dropdown(id="city-filter", title="城市", multi=True)),
        vm.Filter(column="branch_name",
                  selector=vm.Dropdown(id="branch-filter", title="开户网点", multi=True)),
    ],
)

# v1.3: 账户余额统计分析 — 5 页面多维度分析仪表板
# 基础查询: 账户级全维度数据, 各页面从此 DataFrame 聚合
_balance_base_data = pl.DataFrame()
try:
    _balance_base_data = _vizro_con.execute("""
        SELECT
            ta.account_id,
            ta.sub_group_name,
            COALESCE(NULLIF(ta.financial_institution, ''), '未知银行') AS financial_institution,
            COALESCE(NULLIF(ta.bank_city, ''), '未知城市') AS bank_city,
            ta.account_usage,
            ta.is_partner_bank,
            ta.is_overseas,
            fb.balance_amount
        FROM finance_data.fact_treasury_account_balance fb
        JOIN finance_data.dim_treasury_account ta ON fb.account_id = ta.account_id
        WHERE fb.period = (SELECT MAX(period) FROM finance_data.fact_treasury_account_balance)
          AND ta.account_status = '存续'
          AND fb.balance_amount > 0
    """).fetchdf()
    _balance_base_data["log10_balance"] = np.log10(_balance_base_data["balance_amount"].clip(lower=1))
except Exception:
    pass

# 预聚合: 子集团维度
_balance_by_subgroup = None
if _balance_base_data.shape[0] > 0:
    _balance_by_subgroup = _balance_base_data.groupby("sub_group_name").agg(
        total_balance=("balance_amount", "sum"),
        account_count=("account_id", "nunique"),
        avg_balance=("balance_amount", "mean"),
        median_balance=("balance_amount", "median"),
    ).reset_index().sort_values("total_balance", ascending=False)

# 预聚合: 银行维度
_balance_by_bank = None
if _balance_base_data.shape[0] > 0:
    _balance_by_bank = _balance_base_data.groupby("financial_institution").agg(
        total_balance=("balance_amount", "sum"),
        account_count=("account_id", "nunique"),
        avg_balance=("balance_amount", "mean"),
    ).reset_index().sort_values("total_balance", ascending=False)

# 预聚合: 城市维度
_balance_by_city = None
if _balance_base_data.shape[0] > 0:
    _balance_by_city = _balance_base_data.groupby("bank_city").agg(
        total_balance=("balance_amount", "sum"),
        account_count=("account_id", "nunique"),
    ).reset_index().sort_values("total_balance", ascending=False)

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

    # 余额层级分桶
    _bins = [0, 1e5, 1e6, 1e7, 1e8, float("inf")]
    _labels = ["<10万", "10万-100万", "100万-1000万", "1000万-1亿", ">1亿"]
    _balance_base_data["tier"] = pd.cut(_balance_base_data["balance_amount"], bins=_bins, labels=_labels, right=False)
    _tier_data = _balance_base_data.groupby("tier", observed=False).agg(
        total_balance=("balance_amount", "sum"),
        account_count=("account_id", "nunique"),
    ).reset_index()

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

    _top10_sg = _balance_by_subgroup.head(10)
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
    _top20_sg = _balance_by_subgroup.head(20)

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
    _bank_data = _balance_by_bank[_balance_by_bank["financial_institution"] != "财务公司"]

    @capture("graph")
    def bank_bar(data_frame=_bank_data):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=data_frame["financial_institution"], y=data_frame["total_balance"],
                             marker=dict(color="#ee6666"),
                             hovertemplate="%{x}<br>总余额: %{y:,.0f}元<extra></extra>"))
        fig.update_layout(title="银行余额排名 (剔除财务公司)", xaxis_title="银行", yaxis_title="总余额 (元)")
        fig.update_xaxes(tickangle=45)
        return fig

    @capture("graph")
    def bank_pie(data_frame=_bank_data.head(10)):
        fig = go.Figure()
        fig.add_trace(go.Pie(labels=data_frame["financial_institution"], values=data_frame["total_balance"],
                             hole=0.4, textinfo="label+percent",
                             hovertemplate="%{label}<br>总余额: %{value:,.0f}元<extra></extra>"))
        fig.update_layout(title="银行余额占比 (Top 10, 剔除财务公司)")
        return fig

    # 银行 x 账户用途交叉
    _bank_usage_data = _balance_base_data.groupby(["financial_institution", "account_usage"]).agg(
        total_balance=("balance_amount", "sum"),
    ).reset_index()
    _bank_usage_pivot = _bank_usage_data.pivot(index="financial_institution", columns="account_usage", values="total_balance").fillna(0)
    _bank_usage_pivot = _bank_usage_pivot.loc[_bank_usage_pivot.sum(axis=1).sort_values(ascending=False).index].head(10)

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
        vm.Graph(figure=bank_bar(data_frame=_bank_data)),
        vm.Graph(figure=bank_pie(data_frame=_bank_data.head(10))),
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
    _city_known = _balance_by_city[_balance_by_city["bank_city"] != "未知城市"]
    _top20_city = _city_known.head(20)
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
    # 散点: 账户数 vs 平均余额, 每个点=子集团, 颜色=余额层级
    _cross_data = _balance_by_subgroup.copy()
    _cross_data["log10_avg_balance"] = np.log10(_cross_data["avg_balance"].clip(lower=1))
    _cross_data["log10_account_count"] = np.log10(_cross_data["account_count"].clip(lower=1))
    _cross_data["size_scaled"] = np.log10(_cross_data["total_balance"].clip(lower=1)) * 4

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

    # 箱线图: 余额分布 by 银行 (Top 8)
    _top8_banks = _balance_by_bank.head(8)["financial_institution"].tolist()
    _box_data = _balance_base_data[_balance_base_data["financial_institution"].isin(_top8_banks)]

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

_vizro_navigation = vm.Navigation(
    pages={
        "首页": ["home"],
        "地理": ["china-map"],
        "监控": ["penetration-monitor", "bank-account-map"],
        "分析": ["relationship-analysis", "account-detail", "overview"],
        "账户余额统计分析": ["balance-overview", "balance-subgroup", "balance-bank", "balance-geo", "balance-cross"],
    },
    nav_selector=vm.NavBar(
        items=[
            vm.NavLink(
                icon="home",
                label="HOME",
                pages={
                    "首页": ["home"],
                    "地理": ["china-map"],
                },
            ),
            vm.NavLink(
                icon="account_balance",
                label="账户",
                pages={
                    "监控": ["penetration-monitor", "bank-account-map"],
                    "分析": ["relationship-analysis", "account-detail", "overview"],
                    "账户余额统计分析": ["balance-overview", "balance-subgroup", "balance-bank", "balance-geo", "balance-cross"],
                },
            ),
        ]
    ),
)

_vizro_dashboard = vm.Dashboard(
    pages=[_vizro_page_home, _vizro_page_monitor, _vizro_page_relationship,
           _vizro_page_account_detail,
           _vizro_page_overview, _vizro_page_map, _vizro_page_bank_map,
           _vizro_page_balance_overview, _vizro_page_balance_subgroup,
           _vizro_page_balance_bank, _vizro_page_balance_geo, _vizro_page_balance_cross],
    navigation=_vizro_navigation,
)
_vizro = Vizro(server=app, url_base_pathname='/vizro/')
_vizro.build(_vizro_dashboard)

# v1.3: 级联筛选回调 — 省份/银行/子集团驱动城市/省份/银行/子集团选项更新
# 已注释: 城市→省份回调 (城市变化不应反驱省份, 省份→城市才是自然级联方向)
# Vizro 原生不支持 Filter 下拉级联, 通过 Dash callback 动态更新 options
# 任意一个 Filter 值变化 → 其他三个下拉选项根据当前选中值重新计算, 不会循环触发
from dash import Input, Output, callback, no_update

def _get_filter_options(df, column):
    """从 DataFrame 提取下拉选项列表."""
    vals = sorted(df[column].dropna().unique().tolist())
    return [{"label": v, "value": v} for v in vals]


def _apply_all_filters(df, provinces, cities, banks, subgroups, branches=None):
    """按已选值过滤数据."""
    for col, vals in [("province", provinces), ("bank_city", cities),
                       ("financial_institution", banks), ("sub_group_name", subgroups),
                       ("branch_name", branches)]:
        if vals:
            df = df[df[col].isin(vals)]
    return df


def _bank_data():
    return _bank_map_account_data if _bank_map_account_data.shape[0] > 0 else None


# --- 更新城市选项 (依赖: 省份/银行/子集团) ---
@callback(Output("city-filter", "options"),
          Input("prov-filter", "value"), Input("bank-filter", "value"),
          Input("sg-filter", "value"))
def update_city_options(prov, bank, sg):
    df = _bank_data()
    if df is None: return no_update
    df = _apply_all_filters(df, prov, None, bank, sg)
    return _get_filter_options(df, "bank_city")


# --- 已注释: 城市变化→更新省份选项 ---
# 原因: 城市变化不应反驱省份, 省份→城市才是自然的级联方向
# @callback(Output("prov-filter", "options"),
#           Input("city-filter", "value"), Input("bank-filter", "value"),
#           Input("sg-filter", "value"))
# def update_province_options(city, bank, sg):
#     df = _bank_data()
#     if df is None: return no_update
#     df = _apply_all_filters(df, None, city, bank, sg)
#     return _get_filter_options(df, "province")


# --- 更新银行选项 (依赖: 省份/城市/子集团) ---
@callback(Output("bank-filter", "options"),
          Input("prov-filter", "value"), Input("city-filter", "value"),
          Input("sg-filter", "value"))
def update_bank_options(prov, city, sg):
    df = _bank_data()
    if df is None: return no_update
    df = _apply_all_filters(df, prov, city, None, sg)
    return _get_filter_options(df, "financial_institution")


# --- 更新子集团选项 (依赖: 省份/城市/银行) ---
@callback(Output("sg-filter", "options"),
          Input("prov-filter", "value"), Input("city-filter", "value"),
          Input("bank-filter", "value"))
def update_subgroup_options(prov, city, bank):
    df = _bank_data()
    if df is None: return no_update
    df = _apply_all_filters(df, prov, city, bank, None)
    return _get_filter_options(df, "sub_group_name")


# --- 更新开户网点选项 (依赖: 4 维筛选) ---
@callback(Output("branch-filter", "options"),
          Input("prov-filter", "value"), Input("city-filter", "value"),
          Input("bank-filter", "value"), Input("sg-filter", "value"))
def update_branch_options(prov, city, bank, sg):
    df = _bank_data()
    if df is None: return no_update
    df = _apply_all_filters(df, prov, city, bank, sg)
    return _get_filter_options(df, "branch_name")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)

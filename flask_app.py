from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file, url_for
import duckdb
import yaml
import subprocess
import shutil
import time
import re
import vizro.plotly.express as px
from vizro import Vizro
import vizro.models as vm
import numpy as np

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


def db_conn():
    return duckdb.connect(DB_PATH)


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
                sa.account_name AS "指标名称"
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
            r["是否匹配"] = re.sub(r'[（(][^）)]*[）)]', '', std_top).strip() == re.sub(r'[（(][^）)]*[）)]', '', raw_top).strip()
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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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


# --------------- Vizro 仪表板 ---------------

_vizro_db = "/home/song/NutstoreFiles/5-Quartools/app_py/skdata-etl/data/warehouse/finance_warehouse.duckdb"
_vizro_con = duckdb.connect(_vizro_db)

# 图1：资产负债表散点 — 货币资金(x) vs 资产总额(y)，颜色=log10(资产总额)
_vizro_df1 = _vizro_con.execute("""
    SELECT
        f.entity_report_id,
        f.period_id AS 期间,
        COALESCE(ot.node_name, f.entity_report_id) AS 单位名称,
        SUM(CASE WHEN sa.account_name = '资产总额' THEN f.value END) AS 资产总额,
        SUM(CASE WHEN sa.account_name = '货币资金' THEN f.value END) AS 货币资金
    FROM finance_data.fact_finance_data f
    JOIN finance_data.dim_standard_account sa ON f.account_code = sa.account_code
    JOIN finance_data.dim_report_category rc ON f.category_id = rc.category_id
    LEFT JOIN finance_data.dim_organization_tree ot
        ON f.entity_report_id = ot.entity_report_id AND ot.period = f.period_id
    WHERE rc.category_name = '资产负债表'
      AND sa.account_name IN ('资产总额', '货币资金')
      AND f.value_column = '本月数'
    GROUP BY f.entity_report_id, f.period_id, ot.node_name
    HAVING "资产总额" > 0 AND "货币资金" > 0
""").fetchdf()

_vizro_df1["log10_资产总额"] = np.log10(_vizro_df1["资产总额"])

# 图2：账户折算金额分布，按金融机构着色
_vizro_df2 = _vizro_con.execute("""
    SELECT
        fb.converted_amount AS 折算金额,
        fb.period AS 期间,
        COALESCE(ot.node_name, fb.entity_report_id) AS 单位名称,
        COALESCE(NULLIF(ta.financial_institution, ''), ta.opening_institution) AS 金融机构
    FROM finance_data.fact_treasury_account_balance fb
    JOIN finance_data.dim_treasury_account ta ON fb.account_id = ta.account_id
    LEFT JOIN finance_data.dim_organization_tree ot
        ON fb.entity_report_id = ot.entity_report_id AND ot.period = fb.period
    WHERE fb.converted_amount IS NOT NULL AND fb.converted_amount > 0
      AND ta.financial_institution IS NOT NULL AND ta.financial_institution != ''
""").fetchdf()

_vizro_con.close()

_vizro_page = vm.Page(
    title="穿透监控大屏",
    components=[
        vm.Graph(figure=px.scatter(_vizro_df1, x="货币资金", y="资产总额", color="log10_资产总额")),
        vm.Graph(figure=px.histogram(_vizro_df2, x="折算金额", color="金融机构")),
    ],
    controls=[
        vm.Filter(column="期间"),
        vm.Filter(column="单位名称"),
    ],
)

_vizro_dashboard = vm.Dashboard(pages=[_vizro_page])
_vizro = Vizro(server=app, url_base_pathname='/vizro/')
_vizro.build(_vizro_dashboard)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)

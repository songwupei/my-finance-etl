import re

from flask import Blueprint, jsonify, render_template, request

from ..config import _yaml_lookup
from ..database import _resolve_entity_id, _table_exists, db_conn

tree_bp = Blueprint("tree", __name__)


@tree_bp.route("/")
def index():
    return render_template("index.html")


@tree_bp.route("/api/periods")
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


@tree_bp.route("/api/tree_periods")
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


@tree_bp.route("/api/report_categories")
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


@tree_bp.route("/api/tree")
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


@tree_bp.route("/api/node_data")
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

            raw_key = re.sub(r'\s+', ' ', raw_path.strip())
            yaml_match = _yaml_lookup.get(raw_key)
            if not yaml_match:
                raw_top_key = re.sub(r'\s+', ' ', raw_top.strip())
                yaml_match = _yaml_lookup.get(raw_top_key)

            if yaml_match:
                actual_code = r.get("标准科目代码", "")
                r["是否匹配"] = (yaml_match["code"] == actual_code)
            else:
                r["是否匹配"] = True
        return jsonify(records)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

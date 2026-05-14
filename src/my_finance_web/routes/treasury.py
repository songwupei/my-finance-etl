from flask import Blueprint, jsonify, request

from ..database import _resolve_entity_id, _table_exists, db_conn

treasury_bp = Blueprint("treasury", __name__)


@treasury_bp.route("/api/time_options")
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


@treasury_bp.route("/api/treasury_data")
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


@treasury_bp.route("/api/treasury_business_types")
def get_treasury_business_types():
    return jsonify([
        {"value": "account", "label": "账户情况表"},
    ])

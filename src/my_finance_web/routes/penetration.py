"""穿透监管规则手册 — 中台只读 API 与查询页（v1）。"""

from flask import Blueprint, jsonify, render_template, request

from ..database import PENETRATION_DB, penetration_conn

penetration_bp = Blueprint("penetration", __name__)


import math


def _sanitize(value):
    """清洗 pandas/DuckDB 值：NaN/Inf → None，保证输出严格 JSON。"""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def _rows(conn, sql, params=None):
    df = conn.execute(sql, params or []).fetchdf()
    return [_sanitize(d) for d in df.to_dict("records")]


@penetration_bp.route("/penetration")
def index():
    return render_template("penetration.html")


@penetration_bp.route("/api/penetration/meta")
def meta():
    try:
        conn = penetration_conn()
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 503
    try:
        log = _rows(
            conn,
            "SELECT run_id, data_md5, tables_count, rows_total, created_at "
            "FROM penetration_data._ingest_log ORDER BY created_at DESC LIMIT 1",
        )
        return jsonify({"success": True, "db_path": str(PENETRATION_DB),
                        "last_ingest": log[0] if log else None})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@penetration_bp.route("/api/penetration/models")
def models():
    try:
        conn = penetration_conn()
        rows = _rows(
            conn,
            "SELECT DISTINCT model_type, model_name FROM penetration_data.ml_risk_config "
            "WHERE model_name IS NOT NULL AND model_name <> '' "
            "ORDER BY model_type, model_name",
        )
        return jsonify({"success": True, "items": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@penetration_bp.route("/api/penetration/departments")
def departments():
    try:
        conn = penetration_conn()
        rows = _rows(
            conn,
            "SELECT DISTINCT lead_dept FROM penetration_data.ml_risk_config "
            "WHERE lead_dept IS NOT NULL AND lead_dept <> '' ORDER BY lead_dept",
        )
        return jsonify({"success": True, "items": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@penetration_bp.route("/api/penetration/rules")
def rules():
    q = (request.args.get("q") or "").strip()
    model = (request.args.get("model") or "").strip()
    dept = (request.args.get("dept") or "").strip()
    limit = min(int(request.args.get("limit", 100)), 500)
    conds, params = ['rn = 1'], []
    if model:
        conds.append('model_name = ?')
        params.append(model)
    if dept:
        conds.append('lead_dept = ?')
        params.append(dept)
    if q:
        conds.append(
            '(risk_rule_desc ILIKE ? OR rule_parse ILIKE ? OR rule_desc ILIKE ? '
            'OR risk_item ILIKE ? OR gzwgkyq ILIKE ?)'
        )
        like = f"%{q}%"
        params += [like, like, like, like, like]
    where = f"WHERE {' AND '.join(conds)}"
    sql = (
        "SELECT * EXCLUDE (rn) FROM ("
        "  SELECT *, ROW_NUMBER() OVER (PARTITION BY risk_config_id "
        "    ORDER BY rule_order NULLS LAST) AS rn"
        "  FROM penetration_data.v_risk_rule"
        f") {where} ORDER BY risk_config_id LIMIT ?"
    )
    params.append(limit)
    try:
        conn = penetration_conn()
        rows = _rows(conn, sql, params)
        return jsonify({"success": True, "items": rows, "count": len(rows)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@penetration_bp.route("/api/penetration/rules/<int:config_id>")
def rule_detail(config_id):
    try:
        conn = penetration_conn()
        config = _rows(
            conn,
            "SELECT * FROM penetration_data.ml_risk_config WHERE id = ?",
            [config_id],
        )
        if not config:
            return jsonify({"success": False, "error": "规则配置不存在"}), 404
        rules = _rows(
            conn,
            "SELECT rule_order, rule_desc, rule_parse FROM penetration_data.ml_risk_rule "
            "WHERE risk_config_id = ? ORDER BY rule_order",
            [config_id],
        )
        thresholds = _rows(
            conn,
            "SELECT threshold_key, threshold_name, judge_logic, threshold_value "
            "FROM penetration_data.ml_risk_threshold WHERE risk_config_id = ?",
            [config_id],
        )
        points = _rows(
            conn,
            "SELECT point_name, condition_logic, sort_order, remark "
            "FROM penetration_data.ml_risk_rule_point WHERE risk_config_id = ? "
            "ORDER BY sort_order",
            [config_id],
        )
        outputs = _rows(
            conn,
            "SELECT data_name, data_mark FROM penetration_data.ml_risk_output "
            "WHERE risk_config_id = ?",
            [config_id],
        )
        return jsonify({
            "success": True,
            "config": config[0],
            "rules": rules,
            "thresholds": thresholds,
            "points": points,
            "outputs": outputs,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@penetration_bp.route("/api/penetration/ingest_log")
def ingest_log():
    try:
        conn = penetration_conn()
        rows = _rows(
            conn,
            "SELECT run_id, data_md5, tables_count, rows_total, created_at "
            "FROM penetration_data._ingest_log ORDER BY created_at DESC LIMIT 10",
        )
        return jsonify({"success": True, "items": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

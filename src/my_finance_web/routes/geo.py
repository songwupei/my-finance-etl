from flask import Blueprint, jsonify

from ..database import _table_exists, db_conn

geo_bp = Blueprint("geo", __name__)


@geo_bp.route("/api/units_geo")
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

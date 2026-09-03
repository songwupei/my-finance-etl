import duckdb
from pathlib import Path

from .config import DB_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PENETRATION_DB = PROJECT_ROOT / "data/warehouse/penetration.duckdb"


def db_conn():
    return duckdb.connect(DB_PATH, read_only=True)


def penetration_conn():
    """穿透监管中台库（modelmanual 物化产物，只读复用）。"""
    if not PENETRATION_DB.exists():
        raise FileNotFoundError(
            f"穿透监管中台库不存在: {PENETRATION_DB}\n"
            "请先运行 modelmanual: kedro run --tags penetration"
        )
    return duckdb.connect(str(PENETRATION_DB), read_only=True)



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

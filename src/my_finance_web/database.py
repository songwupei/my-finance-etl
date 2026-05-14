import duckdb

from .config import DB_PATH


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

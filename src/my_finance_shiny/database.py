import duckdb

from .config import DB_PATH


def db_conn():
    return duckdb.connect(DB_PATH, read_only=True)

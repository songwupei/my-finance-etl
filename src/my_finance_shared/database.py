"""Shared DuckDB connection with retry logic."""

import time

import duckdb
import polars as pl

from .config import DB_PATH, _proj_dir


def connect_with_retry(read_only=True, retries=3, delay=2):
    """Connect to DuckDB with retry on lock conflicts (e.g. Nutstore sync)."""
    for i in range(retries):
        try:
            return duckdb.connect(DB_PATH, read_only=read_only)
        except duckdb.IOException:
            if i < retries - 1:
                print(f"[shared] DB locked, retrying ({i+1}/{retries})...")
                time.sleep(delay)
            else:
                raise


def sync_geo_to_duckdb(conn):
    """Sync dim_unit_geo parquet into DuckDB."""
    geo_parquet = _proj_dir / "data/03_primary/dim_unit_geo.parquet"
    if not geo_parquet.exists():
        return
    try:
        geo_df = pl.read_parquet(str(geo_parquet))
        if geo_df.is_empty():
            return
        conn.register("_geo", geo_df.to_pandas())
        conn.execute(
            "CREATE OR REPLACE TABLE finance_data.dim_unit_geo AS SELECT * FROM _geo"
        )
        print(f"[shared] Synced {geo_df.height} geo rows to DuckDB from parquet")
    except Exception as e:
        print(f"[shared] Geo sync failed: {e}")

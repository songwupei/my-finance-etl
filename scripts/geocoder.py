"""企业地理编码模块 — 批量地理编码，读取 dim_unit_report，写入 dim_unit_geo + geo_enterprise 缓存。

由 hooks.yml 中的 after_nodes 触发执行。
优先从 geo_enterprise.parquet 缓存读取（code+suffix 为 key），不足的再查高德 API。
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import duckdb
import polars as pl

from geocode_amap.client import AMapClient

_GEO_ENTERPRISE_CACHE = Path(os.path.expanduser(
    "~/NutstoreFiles/8-MyData/GeoData/geo_enterprise.parquet"
))


def run(project_dir: str = None):
    """批量地理编码入口 — 增量模式，优先从缓存加载（code+suffix 为 key）。"""
    t0 = time.time()
    proj = Path(project_dir or os.getcwd())
    geo_parquet = proj / "data/03_primary/dim_unit_geo.parquet"
    unit_parquet = proj / "data/03_primary/dim_unit_report.parquet"
    duckdb_path = proj / "data/warehouse/finance_warehouse.duckdb"

    if not unit_parquet.exists():
        print("[geocoder] dim_unit_report.parquet not found, skipping")
        return

    dim_unit = pl.read_parquet(str(unit_parquet))
    total = len(dim_unit)
    print(f"[geocoder] dim_unit_report: {total} rows")

    # Collect already-geocoded (code, suffix) pairs from geo_enterprise cache
    existing_pairs = set()
    if _GEO_ENTERPRISE_CACHE.exists():
        geo_cache = pl.read_parquet(str(_GEO_ENTERPRISE_CACHE))
        for row in geo_cache.filter(
            pl.col("longitude").is_not_null()
        ).select(["code", "suffix"]).iter_rows(named=True):
            existing_pairs.add((row["code"], row["suffix"]))
        geocoded = geo_cache.filter(pl.col("longitude").is_not_null()).height
        print(f"[geocoder] geo_enterprise cache: {geocoded} with coordinates, "
              f"{geo_cache.height} total")

    # Also check dim_unit_geo (backward compat: entity_report_id keyed)
    if geo_parquet.exists():
        existing_geo = pl.read_parquet(str(geo_parquet))
        # merge dim_unit to get (code,suffix) for existing entity_report_ids
        if "code" not in existing_geo.columns:
            existing_geo = existing_geo.join(
                dim_unit.select(["entity_report_id", "code", "suffix"]).unique(
                    subset=["entity_report_id"]
                ),
                on="entity_report_id", how="left"
            )
        for row in existing_geo.filter(
            pl.col("longitude").is_not_null()
        ).select(["code", "suffix"]).iter_rows(named=True):
            existing_pairs.add((row["code"], row["suffix"]))
        print(f"[geocoder] dim_unit_geo: {existing_geo.height} rows")

    # Find pending: (code,suffix) not in existing_pairs
    dim_unit_dedup = dim_unit.unique(subset=["code", "suffix"], keep="first")
    pending_rows = []
    for row in dim_unit_dedup.iter_rows(named=True):
        key = (row["code"], row["suffix"])
        if key not in existing_pairs:
            pending_rows.append(row)

    if not pending_rows:
        print(f"[geocoder] All {len(dim_unit_dedup)} unique units already geocoded")
        _sync_duckdb_to_geo_enterprise(duckdb_path)
        return

    print(f"[geocoder] Pending: {len(pending_rows)} units "
          f"(QPS=3, ETA ~{len(pending_rows)//3//60} min)")

    records = []
    for row in pending_rows:
        addr = (row.get("enterprise_address") or "").strip()
        parts = [row.get("province") or "", row.get("city") or "", row.get("area") or ""]
        fallback = "".join(parts).strip()
        records.append({
            "code": row["code"],
            "suffix": row["suffix"],
            "entity_report_id": row.get("entity_report_id", ""),
            "enterprise_address": addr,
            "fallback_address": fallback,
        })

    api_key = os.environ.get("AMAP_API_KEY_S", "")
    if not api_key:
        print("[geocoder] AMAP_API_KEY_S not set, using cached data only")
        _sync_duckdb_to_geo_enterprise(duckdb_path)
        return

    results = asyncio.run(_geocode_batch(api_key, records))

    geo_records = []
    for r, geo in zip(records, results):
        geo_records.append({
            "code": r["code"],
            "suffix": r["suffix"],
            "entity_report_id": r["entity_report_id"],
            "longitude": geo.get("lon") if geo else None,
            "latitude": geo.get("lat") if geo else None,
            "geocode_level": geo.get("level") if geo else None,
            "formatted_address": geo.get("formatted_address") if geo else None,
        })

    new_df = pl.DataFrame(geo_records)

    # Update geo_enterprise cache (code+suffix keyed)
    _upsert_geo_enterprise(new_df)

    # Update dim_unit_geo (backward compat, entity_report_id keyed)
    _upsert_dim_unit_geo(geo_parquet, new_df)

    _sync_duckdb_to_geo_enterprise(duckdb_path)
    geocoded = sum(1 for g in geo_records if g["longitude"] is not None)
    elapsed = time.time() - t0
    print(f"[geocoder] Done: {geocoded}/{len(geo_records)} new geocoded in {elapsed:.1f}s")


def _upsert_geo_enterprise(new_df: pl.DataFrame):
    """Merge new geocode results into geo_enterprise.parquet by (code,suffix)."""
    geo_cols = ["code", "suffix", "longitude", "latitude", "geocode_level", "formatted_address"]
    new = new_df.select(geo_cols)

    if _GEO_ENTERPRISE_CACHE.exists():
        old = pl.read_parquet(str(_GEO_ENTERPRISE_CACHE))
        # Remove existing rows with same keys, then concat
        new_keys = set(zip(new["code"].to_list(), new["suffix"].to_list()))
        old = old.filter(
            ~pl.struct(["code", "suffix"]).is_in(
                [{"code": c, "suffix": s} for c, s in new_keys]
            )
        )
        combined = pl.concat([old, new], how="vertical")
    else:
        combined = new

    combined.write_parquet(str(_GEO_ENTERPRISE_CACHE))
    print(f"[geocoder] geo_enterprise cache: {combined.height} rows")


def _upsert_dim_unit_geo(geo_parquet: Path, new_df: pl.DataFrame):
    """Merge new geocode results into dim_unit_geo.parquet (entity_report_id keyed)."""
    cols = ["entity_report_id", "code", "suffix", "longitude", "latitude",
            "geocode_level", "formatted_address"]
    new = new_df.select(cols)

    if geo_parquet.exists():
        old = pl.read_parquet(str(geo_parquet))
        # Ensure code/suffix columns exist in old (backward compat)
        for c in ["code", "suffix"]:
            if c not in old.columns:
                old = old.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
        new_ids = set(new["entity_report_id"].to_list())
        old = old.filter(~pl.col("entity_report_id").is_in(new_ids))
        combined = pl.concat([old, new], how="vertical")
    else:
        combined = new

    combined.write_parquet(str(geo_parquet))
    print(f"[geocoder] dim_unit_geo: {combined.height} rows")


def _sync_duckdb_to_geo_enterprise(duckdb_path: Path):
    """Sync geo_enterprise cache + dim_unit_report to DuckDB dim_unit_geo table."""
    if not _GEO_ENTERPRISE_CACHE.exists():
        return
    try:
        geo = pl.read_parquet(str(_GEO_ENTERPRISE_CACHE))
        if geo.is_empty():
            return
        conn = duckdb.connect(str(duckdb_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS finance_data")
        conn.register("_geo_df", geo.to_pandas())
        conn.execute(
            "CREATE OR REPLACE TABLE finance_data.dim_unit_geo AS SELECT * FROM _geo_df"
        )
        conn.close()
        print(f"[geocoder] Synced {geo.height} rows to DuckDB: {duckdb_path}")
    except Exception as e:
        print(f"[geocoder] DuckDB sync skipped (will retry on Flask restart): {e}")


async def _geocode_batch(api_key: str, records: list[dict]) -> list:
    """单实例串行 geocode，先全文地址 → 失败回退省+市+县。"""
    results = [None] * len(records)
    async with AMapClient(api_key, qps=3) as client:
        for i, r in enumerate(records):
            addr = r["enterprise_address"]
            if addr:
                result = await client.geocode(addr)
                if result:
                    results[i] = result
                    continue
            fallback = r["fallback_address"]
            if fallback:
                result = await client.geocode(fallback)
                if result:
                    results[i] = result
    return results

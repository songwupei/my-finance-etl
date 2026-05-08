"""企业地理编码模块 — 独立的批量地理编码，读取 dim_unit_report，写入 dim_unit_geo。

由 hooks.yml 中的 after_nodes 触发执行。
优先从 BQ_geo.parquet 缓存读取，不足的再查高德 API。
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import duckdb
import polars as pl

_MAP_UTILS = os.path.expanduser("~/NutstoreFiles/2-Code/1-MyPython/0-MyPyPkg/map_utils")
if _MAP_UTILS not in sys.path:
    sys.path.insert(0, _MAP_UTILS)
from amap_client import AMapClient

_BQ_CACHE = Path(os.path.expanduser("~/NutstoreFiles/8-MyData/GeoData/BQ_geo.parquet"))


def run(project_dir: str = None):
    """批量地理编码入口 — 增量模式，优先从缓存加载。"""
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

    # 从缓存和已有数据收集已 geocoded 的 ID
    existing_ids = set()
    for cache_path in (geo_parquet, _BQ_CACHE):
        if cache_path.exists():
            existing_ids.update(pl.read_parquet(str(cache_path))["entity_report_id"].to_list())

    # 如果本地还没有但缓存有，直接复制
    if _BQ_CACHE.exists() and not geo_parquet.exists():
        pl.read_parquet(str(_BQ_CACHE)).write_parquet(str(geo_parquet))
        print(f"[geocoder] Copied {len(existing_ids)} rows from {_BQ_CACHE}")

    # 统计
    if geo_parquet.exists():
        geo_df = pl.read_parquet(str(geo_parquet))
        geocoded = geo_df.filter(pl.col("longitude").is_not_null()).height
        print(f"[geocoder] Stats: {geocoded}/{total} units geocoded ({100*geocoded/total:.1f}%)")

    pending = dim_unit.filter(~pl.col("entity_report_id").is_in(existing_ids))
    if pending.is_empty():
        print(f"[geocoder] All {len(dim_unit)} units already geocoded (cached), done")
        # 确保 DuckDB 也有数据
        _sync_duckdb(duckdb_path, pl.read_parquet(str(geo_parquet)))
        return

    print(f"[geocoder] Pending: {len(pending)} units (QPS=3, ETA ~{len(pending)//3//60} min)")

    records = []
    for row in pending.iter_rows(named=True):
        addr = (row.get("enterprise_address") or "").strip()
        parts = [row.get("province") or "", row.get("city") or "", row.get("area") or ""]
        fallback = "".join(parts).strip()
        records.append({
            "entity_report_id": row["entity_report_id"],
            "enterprise_address": addr,
            "fallback_address": fallback,
        })

    api_key = os.environ.get("AMAP_API_KEY_S", "")
    if not api_key:
        print("[geocoder] AMAP_API_KEY_S not set, using cached data only")
        _sync_duckdb(duckdb_path, pl.read_parquet(str(geo_parquet)) if geo_parquet.exists() else pl.DataFrame())
        return

    results = asyncio.run(_geocode_batch(api_key, records))

    geo_records = []
    for r, geo in zip(records, results):
        geo_records.append({
            "entity_report_id": r["entity_report_id"],
            "longitude": geo.get("lon") if geo else None,
            "latitude": geo.get("lat") if geo else None,
            "geocode_level": geo.get("level") if geo else None,
            "formatted_address": geo.get("formatted_address") if geo else None,
        })

    new_df = pl.DataFrame(geo_records)
    if geo_parquet.exists():
        old_df = pl.read_parquet(str(geo_parquet))
        combined = pl.concat([old_df, new_df], how="vertical")
    else:
        combined = new_df
    combined.write_parquet(str(geo_parquet))
    print(f"[geocoder] Written {len(combined)} rows to {geo_parquet}")

    _sync_duckdb(duckdb_path, combined)
    geocoded = sum(1 for g in geo_records if g["longitude"] is not None)
    print(f"[geocoder] Done: {geocoded}/{len(geo_records)} new geocoded")


def _sync_duckdb(duckdb_path: Path, df: pl.DataFrame):
    """同步数据到 DuckDB（锁冲突时跳过，下次 Flask 启动自动补）。"""
    if df.is_empty():
        return
    try:
        conn = duckdb.connect(str(duckdb_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS finance_data")
        conn.register("_geo_df", df.to_pandas())
        conn.execute("CREATE OR REPLACE TABLE finance_data.dim_unit_geo AS SELECT * FROM _geo_df")
        conn.close()
        print(f"[geocoder] Synced {df.height} rows to DuckDB: {duckdb_path}")
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

"""Pipeline node: enrich geo coordinates via 高德 API + write-back to shared caches.

Two-layer cache:
  geo_enterprise / geo_bank   — entity → current address + coords (PK: entity key)
  geo_address                 — address → coords + query_time (PK: address string)

Lookup order: entity cache → address cache (TTL check) → 高德 API
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import polars as pl
from kedro.pipeline import Pipeline, node

_MAP_UTILS = os.path.expanduser("~/NutstoreFiles/2-Code/1-MyPython/0-MyPyPkg/map_utils")
if _MAP_UTILS not in sys.path:
    sys.path.insert(0, _MAP_UTILS)
from amap_client import AMapClient

logger = logging.getLogger(__name__)

GEO_BANK_PATH = Path(os.path.expanduser(
    "~/NutstoreFiles/8-MyData/GeoData/geo_bank.parquet"
))
GEO_ENTERPRISE_PATH = Path(os.path.expanduser(
    "~/NutstoreFiles/8-MyData/GeoData/geo_enterprise.parquet"
))
GEO_ADDRESS_PATH = Path(os.path.expanduser(
    "~/NutstoreFiles/8-MyData/GeoData/geo_address.parquet"
))


# ==================== main entry ====================

def enrich_geo_coordinates(
    dim_bank_branch: pl.DataFrame,
    dim_unit_report: pl.DataFrame,
    parameters: dict = None,
) -> tuple:
    """Geocode bank branches + enterprises, address-first lookup with TTL.

    Returns:
        (dim_bank_branch, dim_unit_geo) — with fresh coordinates filled in.
    """
    t0 = time.time()
    params = parameters or {}
    bank_cfg = params.get("bank_branch", {})
    geo_bank_path = Path(bank_cfg.get("geo_cache_path", str(GEO_BANK_PATH)))
    geo_cfg = params.get("geo", {})
    geo_ent_path = Path(geo_cfg.get("enterprise_cache_path", str(GEO_ENTERPRISE_PATH)))
    geo_addr_path = Path(geo_cfg.get("address_cache_path", str(GEO_ADDRESS_PATH)))
    geo_failed_path = Path(geo_cfg.get("failed_cache_path",
        str(GEO_ADDRESS_PATH.parent / "geo_address_failed.parquet")))
    ttl_months = int(geo_cfg.get("address_ttl_months", 12))
    failed_retry_months = int(geo_cfg.get("failed_retry_months", 3))

    api_key = os.environ.get("AMAP_API_KEY_S", "")
    if not api_key:
        logger.info("AMAP_API_KEY_S not set — skipping API geocoding")
        return dim_bank_branch, pl.DataFrame()

    # Load caches
    addr_cache = _load_address_cache(geo_addr_path)
    failed_cache = _load_failed_addresses(geo_failed_path)

    # ---- 1. Bank branches ----
    bank_updated, addr_cache, failed_cache = _geocode_bank_branches(
        dim_bank_branch, api_key, geo_bank_path, addr_cache, failed_cache,
        ttl_months, failed_retry_months,
    )

    # ---- 2. Enterprises ----
    addr_cache, failed_cache = _geocode_enterprises(
        dim_unit_report, api_key, geo_ent_path, addr_cache, failed_cache,
        ttl_months, failed_retry_months,
    )

    # Save caches
    _save_address_cache(geo_addr_path, addr_cache)
    _save_failed_addresses(geo_failed_path, failed_cache)

    # Build full dim_unit_geo from geo_enterprise + dim_unit_report
    ent_geo = _build_full_dim_unit_geo(geo_ent_path, dim_unit_report)

    elapsed = time.time() - t0
    logger.info("Geo enrich done in %.1fs", elapsed)
    return bank_updated, ent_geo


# ==================== address cache ====================

def _load_address_cache(cache_path: Path) -> dict:
    """Return {address: {lon, lat, level, formatted_address, query_time}}."""
    cache = {}
    if cache_path.exists():
        df = pl.read_parquet(str(cache_path))
        for row in df.iter_rows(named=True):
            addr = row["address"]
            cache[addr] = {
                "longitude": row["longitude"],
                "latitude": row["latitude"],
                "geocode_level": row["geocode_level"],
                "formatted_address": row["formatted_address"],
                "query_time": row["query_time"],
            }
    return cache


def _save_address_cache(cache_path: Path, cache: dict):
    """Write address cache dict back to parquet."""
    if not cache:
        return
    rows = []
    for addr, geo in cache.items():
        rows.append({
            "address": addr,
            "address_type": geo.get("address_type", ""),
            "longitude": geo["longitude"],
            "latitude": geo["latitude"],
            "geocode_level": geo.get("geocode_level", ""),
            "formatted_address": geo.get("formatted_address", ""),
            "query_time": geo.get("query_time", ""),
        })
    df = pl.DataFrame(rows)
    # Dedup by address, keep latest query_time
    df = df.sort("query_time", descending=True).unique(
        subset=["address"], keep="first"
    )
    df.write_parquet(str(cache_path))
    logger.info("Geo address cache saved: %d entries", df.height)


# ==================== failed address cache ====================

def _load_failed_addresses(cache_path: Path) -> dict:
    """Return {address: {fail_count, last_retry}}."""
    cache = {}
    if cache_path.exists():
        df = pl.read_parquet(str(cache_path))
        for row in df.iter_rows(named=True):
            cache[row["address"]] = {
                "fail_count": row["fail_count"],
                "last_retry": row["last_retry"],
            }
    return cache


def _save_failed_addresses(cache_path: Path, cache: dict):
    """Write failed address cache to parquet."""
    if not cache:
        return
    rows = []
    for addr, info in cache.items():
        rows.append({
            "address": addr,
            "address_type": info.get("address_type", ""),
            "fail_count": info.get("fail_count", 0),
            "last_retry": info.get("last_retry", ""),
        })
    df = pl.DataFrame(rows)
    df = df.sort("last_retry", descending=True).unique(
        subset=["address"], keep="first"
    )
    df.write_parquet(str(cache_path))
    logger.info("Failed address cache saved: %d entries", df.height)


def _is_in_cooldown(addr: str, failed_cache: dict, retry_months: int) -> bool:
    """True if address failed recently and should NOT be retried yet."""
    if not addr:
        return False
    failed = failed_cache.get(addr)
    if failed is None:
        return False
    try:
        last_retry = datetime.fromisoformat(str(failed["last_retry"]))
        cutoff = datetime.now(timezone.utc) - timedelta(days=retry_months * 30)
        return last_retry >= cutoff
    except (ValueError, TypeError):
        return False


def _record_failed(addr: str, addr_type: str, failed_cache: dict) -> dict:
    """Record a failed geocode attempt. Returns updated cache."""
    now_ts = datetime.now(timezone.utc).isoformat()
    existing = failed_cache.get(addr, {})
    failed_cache[addr] = {
        "address_type": addr_type,
        "fail_count": existing.get("fail_count", 0) + 1,
        "last_retry": now_ts,
    }
    return failed_cache


def _remove_failed(addr: str, failed_cache: dict) -> dict:
    """Remove address from failed cache (on successful geocode)."""
    failed_cache.pop(addr, None)
    return failed_cache


def _check_address_cache(addr: str, addr_cache: dict, ttl_months: int) -> dict | None:
    """Return cached geo if address exists and is within TTL, else None."""
    if not addr:
        return None
    cached = addr_cache.get(addr)
    if cached is None:
        return None
    qt = cached.get("query_time")
    if qt is None:
        return None
    try:
        query_time = datetime.fromisoformat(str(qt))
        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_months * 30)
        if query_time < cutoff:
            return None  # expired
    except (ValueError, TypeError):
        return None
    return cached


# ==================== bank branches ====================

def _geocode_bank_branches(
    dim: pl.DataFrame, api_key: str, cache_path: Path,
    addr_cache: dict, failed_cache: dict,
    ttl_months: int, failed_retry_months: int,
) -> tuple[pl.DataFrame, dict, dict]:
    """POI-search bank branches, address-cache-first with TTL + failed cooldown."""
    # Build entity cache: institution_code → (name, city)
    ent_cache = {}
    if cache_path.exists():
        cache = pl.read_parquet(str(cache_path))
        for row in cache.select(
            ["institution_code", "opening_institution", "bank_city"]
        ).iter_rows(named=True):
            ent_cache[row["institution_code"]] = (
                (row.get("opening_institution") or "").strip(),
                (row.get("bank_city") or "").strip(),
            )

    pending_rows = []
    for row in dim.filter(
        pl.col("institution_code").is_not_null()
    ).iter_rows(named=True):
        code = row["institution_code"]
        cur_name = (row.get("opening_institution") or "").strip()
        cur_city = (row.get("bank_city") or "").strip()
        cur_lon = row.get("longitude")

        cached = ent_cache.get(code)
        if cached is None:
            pending_rows.append(row)
        elif cur_lon is None:
            pending_rows.append(row)
        elif cached != (cur_name, cur_city):
            pending_rows.append(row)
        # else: up to date → skip

    if not pending_rows:
        logger.info("Bank branches: all up to date, skip")
        return dim, addr_cache, failed_cache

    logger.info("Bank branches pending: %d", len(pending_rows))

    # Split: address cache hits vs API needed (with failed cooldown)
    now_ts = datetime.now(timezone.utc).isoformat()
    geo_updates = {}  # institution_code → geo dict
    api_records = []

    for row in pending_rows:
        code = row["institution_code"]
        name = (row.get("opening_institution") or "").strip()
        city = (row.get("bank_city") or "").strip()
        addr_key = f"{name} | {city}" if name else ""

        # Check failed cooldown first
        if _is_in_cooldown(addr_key, failed_cache, failed_retry_months):
            continue

        # Check address cache
        cached_geo = _check_address_cache(addr_key, addr_cache, ttl_months)
        if cached_geo:
            geo_updates[code] = {
                "institution_code": code,
                "opening_institution": name,
                "bank_city": city,
                "longitude": cached_geo["longitude"],
                "latitude": cached_geo["latitude"],
                "geocode_level": cached_geo["geocode_level"],
                "formatted_address": cached_geo["formatted_address"],
            }
            # Remove from failed cache if previously failed
            _remove_failed(addr_key, failed_cache)
            continue

        api_records.append({"institution_code": code, "name": name, "city": city})

    addr_hits = len(geo_updates)
    logger.info("Bank: %d from address cache, %d need API", addr_hits, len(api_records))

    # API calls for remaining
    if api_records:
        api_results = asyncio.run(_geocode_banks(api_key, api_records))
        for r, geo in zip(api_records, api_results):
            name = r["name"]
            city = r["city"]
            addr_key = f"{name} | {city}"
            if geo:
                geo_updates[r["institution_code"]] = {
                    "institution_code": r["institution_code"],
                    "opening_institution": name,
                    "bank_city": city,
                    "longitude": geo["lon"],
                    "latitude": geo["lat"],
                    "geocode_level": geo.get("typecode") or geo.get("level", ""),
                    "formatted_address": geo.get("address") or geo.get("formatted_address", ""),
                }
                # Save to address cache
                addr_cache[addr_key] = {
                    "address_type": "bank",
                    "longitude": geo["lon"],
                    "latitude": geo["lat"],
                    "geocode_level": geo.get("typecode") or geo.get("level", ""),
                    "formatted_address": geo.get("address") or geo.get("formatted_address", ""),
                    "query_time": now_ts,
                }
                _remove_failed(addr_key, failed_cache)
            else:
                _record_failed(addr_key, "bank", failed_cache)
        logger.info("Bank API: %d/%d matched", sum(1 for g in api_results if g), len(api_records))

    # Update dim_bank_branch
    if geo_updates:
        geo_df = pl.DataFrame(list(geo_updates.values()))
        dim = dim.join(
            geo_df.select([
                "institution_code",
                pl.col("longitude").alias("longitude_new"),
                pl.col("latitude").alias("latitude_new"),
                pl.col("geocode_level").alias("geocode_level_new"),
                pl.col("formatted_address").alias("formatted_address_new"),
            ]),
            on="institution_code", how="left",
        )
        for col in ["longitude", "latitude", "geocode_level", "formatted_address"]:
            dim = dim.with_columns(
                pl.col(f"{col}_new").fill_null(pl.col(col)).alias(col)
            ).drop(f"{col}_new")

        _upsert_geo_cache(cache_path, geo_df.select([
            "institution_code", "opening_institution", "bank_city",
            "longitude", "latitude", "geocode_level", "formatted_address",
        ]), key="institution_code")

    return dim, addr_cache, failed_cache


async def _geocode_banks(api_key: str, records: list[dict]) -> list:
    """POI search bank branches via 高德 place/text API."""
    results = [None] * len(records)
    async with AMapClient(api_key, qps=3) as client:
        for i, rec in enumerate(records):
            if rec["city"]:
                result = await client.search_poi(
                    keywords=rec["name"], city=rec["city"],
                    city_limit=True, page_size=1, verbose=False,
                )
                if result and result.get("pois"):
                    results[i] = result["pois"][0]
                    continue
            result = await client.search_poi(
                keywords=rec["name"], city_limit=False,
                page_size=1, verbose=False,
            )
            if result and result.get("pois"):
                results[i] = result["pois"][0]
    return results


# ==================== enterprises ====================

def _geocode_enterprises(
    dim_unit: pl.DataFrame, api_key: str, cache_path: Path,
    addr_cache: dict, failed_cache: dict,
    ttl_months: int, failed_retry_months: int,
) -> tuple[dict, dict]:
    """Geocode enterprises, address-cache-first with TTL + failed cooldown.
    Returns (addr_cache, failed_cache)."""
    # Sort by period DESC so unique keeps the latest month's address
    dim_unit_sorted = dim_unit.sort("period", descending=True)
    dim_dedup = dim_unit_sorted.unique(subset=["code", "suffix"], keep="first")

    # Build entity cache: (code, suffix) → (address, has_coords)
    ent_cache = {}
    if cache_path.exists():
        geo_cache = pl.read_parquet(str(cache_path))
        for row in geo_cache.select(
            ["code", "suffix", "enterprise_address", "longitude"]
        ).iter_rows(named=True):
            ent_cache[(row["code"], row["suffix"])] = (
                (row.get("enterprise_address") or "").strip(),
                row.get("longitude") is not None,
            )

    pending_rows = []
    for row in dim_dedup.iter_rows(named=True):
        key = (row["code"], row["suffix"])
        cur_addr = (row.get("enterprise_address") or "").strip()
        cached = ent_cache.get(key)
        if cached is None:
            pending_rows.append(row)
        elif not cached[1]:
            pending_rows.append(row)
        elif cached[0] != cur_addr:
            pending_rows.append(row)

    if not pending_rows:
        logger.info("Enterprises: all up to date, skip")
        return addr_cache, failed_cache

    logger.info("Enterprises pending: %d", len(pending_rows))

    now_ts = datetime.now(timezone.utc).isoformat()
    geo_rows = []        # final output rows
    api_records = []     # records needing API call

    for row in pending_rows:
        addr = (row.get("enterprise_address") or "").strip()
        code = row["code"]
        suffix = row["suffix"]
        entity_id = row.get("entity_report_id", "")

        base = {
            "code": code, "suffix": suffix,
            "enterprise_address": addr,
            "entity_report_id": entity_id,
        }

        # Check failed cooldown first
        if _is_in_cooldown(addr, failed_cache, failed_retry_months):
            continue

        cached_geo = _check_address_cache(addr, addr_cache, ttl_months)
        if cached_geo:
            geo_rows.append({**base,
                "longitude": cached_geo["longitude"],
                "latitude": cached_geo["latitude"],
                "geocode_level": cached_geo["geocode_level"],
                "formatted_address": cached_geo["formatted_address"],
            })
            _remove_failed(addr, failed_cache)
            continue

        # Need API — build geocode record with fallback
        parts = [
            row.get("province") or "",
            row.get("city") or "",
            row.get("area") or "",
        ]
        fb = "".join(parts).strip()
        api_records.append({**base, "address": addr, "fallback": fb})

    addr_hits = len(geo_rows)
    logger.info("Enterprise: %d from address cache, %d need API",
                addr_hits, len(api_records))

    if api_records:
        api_results = asyncio.run(_geocode_enterprises_async(api_key, api_records))
        for r, geo in zip(api_records, api_results):
            row = {
                "code": r["code"], "suffix": r["suffix"],
                "enterprise_address": r.get("enterprise_address", r["address"]),
                "entity_report_id": r["entity_report_id"],
                "longitude": geo.get("lon") if geo else None,
                "latitude": geo.get("lat") if geo else None,
                "geocode_level": geo.get("level") if geo else None,
                "formatted_address": geo.get("formatted_address") if geo else None,
            }
            geo_rows.append(row)
            if geo and r.get("address"):
                addr_cache[r["address"]] = {
                    "address_type": "enterprise",
                    "longitude": geo["lon"],
                    "latitude": geo["lat"],
                    "geocode_level": geo.get("level", ""),
                    "formatted_address": geo.get("formatted_address", ""),
                    "query_time": now_ts,
                }
                _remove_failed(r["address"], failed_cache)
            else:
                if r.get("address"):
                    _record_failed(r["address"], "enterprise", failed_cache)
        logger.info("Enterprise API: %d/%d matched",
                    sum(1 for g in api_results if g), len(api_records))

    if not geo_rows:
        logger.info("Enterprise: all skipped (cooldown), no new geocodes")
        return addr_cache, failed_cache

    geo_df = pl.DataFrame(geo_rows)
    hit = geo_df.filter(pl.col("longitude").is_not_null()).height
    logger.info("Enterprise total geocoded: %d/%d", hit, len(geo_rows))

    # Upsert entity cache
    _upsert_geo_cache(cache_path, geo_df.select([
        "code", "suffix", "enterprise_address",
        "longitude", "latitude", "geocode_level", "formatted_address",
    ]), key=["code", "suffix"])

    return addr_cache, failed_cache


def _build_full_dim_unit_geo(cache_path: Path, dim_unit: pl.DataFrame) -> pl.DataFrame:
    """Build complete dim_unit_geo from geo_enterprise cache + dim_unit_report.

    Joins geo_enterprise (code+suffix → coords) with dim_unit_report to get
    entity_report_id.  Returns all entities that have coordinates.
    """
    if not cache_path.exists():
        logger.warning("geo_enterprise not found, returning empty dim_unit_geo")
        return pl.DataFrame()

    geo = pl.read_parquet(str(cache_path))
    geo = geo.filter(pl.col("longitude").is_not_null())

    # Get latest entity_report_id for each (code, suffix)
    unit_dedup = (
        dim_unit.sort("period", descending=True)
        .unique(subset=["code", "suffix"], keep="first")
        .select(["entity_report_id", "code", "suffix"])
    )

    result = unit_dedup.join(geo, on=["code", "suffix"], how="inner").select([
        "entity_report_id", "code", "suffix",
        "longitude", "latitude", "geocode_level", "formatted_address",
    ])
    logger.info("Built dim_unit_geo: %d rows with coordinates", result.height)
    return result


async def _geocode_enterprises_async(api_key: str, records: list[dict]) -> list:
    """Geocode enterprise addresses via 高德 geocode API."""
    results = [None] * len(records)
    async with AMapClient(api_key, qps=3) as client:
        for i, r in enumerate(records):
            if r.get("address"):
                result = await client.geocode(r["address"])
                if result:
                    results[i] = result
                    continue
            if r.get("fallback"):
                result = await client.geocode(r["fallback"])
                if result:
                    results[i] = result
    return results


# ==================== shared ====================

def _upsert_geo_cache(cache_path: Path, new: pl.DataFrame, key):
    """Upsert new geo rows into cache parquet by key column(s)."""
    keys = [key] if isinstance(key, str) else key
    if cache_path.exists():
        old = pl.read_parquet(str(cache_path))
        new_keys = set()
        for row in new.select(keys).iter_rows(named=True):
            new_keys.add(tuple(row[k] for k in keys))
        if len(keys) == 1:
            k = keys[0]
            old = old.filter(~pl.col(k).is_in([nk[0] for nk in new_keys]))
        else:
            old = old.filter(
                ~pl.struct(keys).is_in(
                    [dict(zip(keys, nk)) for nk in new_keys]
                )
            )
        combined = pl.concat([old, new], how="vertical")
    else:
        combined = new
    combined.write_parquet(str(cache_path))
    logger.info("Geo cache updated: %s (%d rows)", cache_path.name, combined.height)


# ==================== pipeline ====================

def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline([
        node(
            func=enrich_geo_coordinates,
            inputs=["dim_bank_branch", "dim_unit_report", "parameters"],
            outputs=["dim_bank_branch_enriched", "dim_unit_geo"],
            name="enrich_geo_coordinates",
        ),
    ])

#!/usr/bin/env python3
"""Export enterprise geo data from my-finance-etl DuckDB to SionTiles POI GeoJSON.

Reads dim_unit_geo (Gaode GCJ-02 coordinates), converts to WGS-84,
and writes a GeoJSON FeatureCollection to the SionTiles POI directory.

Usage:
    python scripts/export_enterprise_poi.py                    # default paths
    python scripts/export_enterprise_poi.py --output /tmp/test.geojson  # dry-run
"""

import json
import math
import os
import sys
from pathlib import Path

# ── GCJ-02 → WGS-84 conversion (same as SionTiles convert_poi.py) ──


def gcj02_to_wgs84(lon: float, lat: float) -> tuple[float, float]:
    a, ee = 6378245.0, 0.00669342162296594323

    def tlat(x, y):
        r = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        r += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
        r += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
        return r

    def tlon(x, y):
        r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
        r += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
        r += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
        return r

    dlat = tlat(lon - 105.0, lat - 35.0)
    dlon = tlon(lon - 105.0, lat - 35.0)
    rlat = lat / 180.0 * math.pi
    magic = 1 - ee * math.sin(rlat) * math.sin(rlat)
    sm = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sm) * math.pi)
    dlon = (dlon * 180.0) / (a / sm * math.cos(rlat) * math.pi)
    return round(lon - dlon, 6), round(lat - dlat, 6)


# ── Default paths ──

_PROJ_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _PROJ_DIR / "data" / "warehouse" / "finance_warehouse.duckdb"
_DEFAULT_OUT = Path(
    os.environ.get(
        "SIONTILES_POI_DIR",
        os.path.expanduser("~/NutstoreFiles/8-MyData/GeoData/poi"),
    )
) / "my_finance_enterprise_wgs84.geojson"


def export_enterprise_geojson(db_path: str = None, output_path: str = None) -> str:
    """Export dim_unit_geo to GeoJSON, returns output path."""
    import duckdb

    db_path = db_path or str(_DEFAULT_DB)
    output_path = output_path or str(_DEFAULT_OUT)

    con = duckdb.connect(db_path, read_only=True)

    # Join geo data with org tree for enterprise names
    df = con.execute("""
        SELECT
            g.code,
            g.longitude,
            g.latitude,
            g.geocode_level,
            g.formatted_address,
            t.node_name,
            t.suffix
        FROM finance_data.dim_unit_geo g
        LEFT JOIN finance_data.dim_organization_tree t
            ON g.code = t.unit_code AND g.suffix = t.suffix
        WHERE g.longitude IS NOT NULL
          AND g.latitude IS NOT NULL
    """).fetchdf()

    con.close()

    # Filter: prefer suffix=0 (本部口径), deduplicate by code
    df = df.sort_values("suffix").groupby("code", as_index=False).first()

    features = []
    for _, row in df.iterrows():
        wgs_lon, wgs_lat = gcj02_to_wgs84(row["longitude"], row["latitude"])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [wgs_lon, wgs_lat]},
            "properties": {
                "code": row["code"],
                "name": row["node_name"] or row["code"],
                "address": row["formatted_address"] or "",
                "geocode_level": row["geocode_level"] or "",
                "source": "my-finance-etl",
            },
        })

    result = {
        "type": "FeatureCollection",
        "coord_type": "wgs84",
        "source": "my-finance-etl dim_unit_geo",
        "features": features,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✓ Exported {len(features)} enterprises → {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export enterprise geo data to SionTiles POI GeoJSON")
    parser.add_argument("--db", help="DuckDB path", default=str(_DEFAULT_DB))
    parser.add_argument("--output", help="Output GeoJSON path", default=str(_DEFAULT_OUT))
    args = parser.parse_args()

    export_enterprise_geojson(args.db, args.output)

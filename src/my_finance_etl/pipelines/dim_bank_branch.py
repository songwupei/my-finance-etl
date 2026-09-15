"""Build dim_bank_branch from parsed treasury account info + CNAPS XML enrichment."""
import logging

import pandas as pd
import polars as pl
from kedro.pipeline import Pipeline, node
from pathlib import Path

from my_finance_shared import NUTSTORE_ROOT

logger = logging.getLogger(__name__)


def build_dim_bank_branch(parsed_treasury_account_info: pl.DataFrame,
                          parameters: dict = None) -> pl.DataFrame:
    """Extract unique bank branches, enrich from CNAPS XML.

    Args:
        parsed_treasury_account_info: from treasury_ingestion output
        parameters: Kedro parameters dict

    Returns:
        dim_bank_branch DataFrame (written to parquet by Kedro catalog)
    """
    params = parameters or {}
    bank_cfg = params.get("bank_branch", {})
    cnaps_xml = Path(bank_cfg.get(
        "cnaps_xml_path",
        "data/01_raw/CNAPS/CCMSZDT0401.xml",
    ))

    # 1. Extract bank branch columns, clean, deduplicate
    col_map = {
        "financial_institution": "financial_institution",
        "opening_institution": "opening_institution",
        "institution_code": "institution_code",
        "bank_city": "bank_city",
    }
    keep = [c for c in col_map if c in parsed_treasury_account_info.columns]
    if "institution_code" not in keep:
        logger.warning("institution_code missing from account info, returning empty")
        return pl.DataFrame()

    branches = parsed_treasury_account_info.select(keep)
    branches = branches.with_columns(pl.all().cast(pl.Utf8).str.strip_chars())
    branches = branches.with_columns(
        pl.col("institution_code").str.strip_chars().str.zfill(12)
    )
    branches = branches.unique(subset=["institution_code"], keep="first")
    logger.info("Unique bank branches from account info: %d", len(branches))

    # 2. Enrich from CNAPS XML
    out = branches
    if cnaps_xml.exists():
        xml_pd = pd.read_xml(str(cnaps_xml), xpath=".//ROW", dtype=str)
        xml = pl.from_pandas(xml_pd)
        xml = xml.with_columns(pl.all().cast(pl.Utf8).str.strip_chars())
        xml = xml.with_columns(
            pl.col("BANKCODE").str.strip_chars().str.zfill(12)
        )
        xml = xml.rename({
            "BANKCODE": "institution_code",
            "BANKNAME": "cnaps_bank_name",
            "BANKCATALOG": "bank_catalog",
            "BANKTYPE": "bank_type_code",
            "PBCCODE": "pbc_code",
            "CCPC": "ccpc",
            "DRECCODE": "drec_code",
            "AGENTSETTBANK": "agent_sett_bank",
            "SUPRLIST": "supr_list",
            "SBSTITNBK": "sbst_itn_bk",
            "DEBTORCITY": "cnaps_city_code",
            "SYSCODE": "sys_code",
            "TEL": "tel",
            "EFFECTDATE": "effect_date",
            "EXPDATE": "exp_date",
            "ACCBKCDINF": "acc_bk_cd_inf",
        })
        xml_cols = [c for c in [
            "institution_code", "cnaps_bank_name", "bank_catalog",
            "bank_type_code", "pbc_code", "ccpc", "drec_code",
            "agent_sett_bank", "supr_list", "sbst_itn_bk",
            "cnaps_city_code", "sys_code", "tel", "effect_date",
            "exp_date", "acc_bk_cd_inf",
        ] if c in xml.columns]
        xml = xml.select(xml_cols).unique(subset=["institution_code"], keep="first")

        out = branches.join(xml, on="institution_code", how="left", coalesce=True)
        matched = out.filter(pl.col("cnaps_bank_name").is_not_null()).height
        logger.info("CNAPS enriched: %d/%d matched", matched, len(branches))
    else:
        logger.info("CNAPS XML not found: %s, skipping enrichment", cnaps_xml)
        out = branches.with_columns([
            pl.lit(None, dtype=pl.Utf8).alias(c) for c in [
                "cnaps_bank_name", "bank_catalog", "bank_type_code",
                "pbc_code", "ccpc", "drec_code", "agent_sett_bank",
                "supr_list", "sbst_itn_bk", "cnaps_city_code",
                "sys_code", "tel", "effect_date", "exp_date", "acc_bk_cd_inf",
            ]
        ])

    # 3. Geocode from cache (BQBankBranch_geo.parquet), fallback to NULL placeholders
    geo_path = Path(bank_cfg.get(
        "geo_cache_path",
        str(NUTSTORE_ROOT / "8-MyData/GeoData/geo_bank.parquet"),
    ))
    if geo_path.exists():
        geo = pl.read_parquet(str(geo_path))
        # only take geo columns + join key from cache
        geo_cols = ["institution_code", "longitude", "latitude", "geocode_level", "formatted_address"]
        geo = geo.select([c for c in geo_cols if c in geo.columns])
        # drop existing placeholder geo cols before join
        out = out.drop([c for c in ["longitude", "latitude", "geocode_level", "formatted_address"]
                        if c in out.columns])
        out = out.join(geo, on="institution_code", how="left")
        cached_geo = out.filter(pl.col("longitude").is_not_null()).height
        logger.info("Geo cache loaded: %d/%d have coordinates", cached_geo, len(out))
    else:
        out = out.with_columns([
            pl.lit(None, dtype=pl.Float64).alias("longitude"),
            pl.lit(None, dtype=pl.Float64).alias("latitude"),
            pl.lit(None, dtype=pl.Utf8).alias("geocode_level"),
            pl.lit(None, dtype=pl.Utf8).alias("formatted_address"),
        ])
        logger.info("Geo cache not found: %s, using NULL placeholders", geo_path)

    logger.info("dim_bank_branch: %d rows", len(out))
    return out


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline([
        node(
            func=build_dim_bank_branch,
            inputs=["parsed_treasury_account_info", "parameters"],
            outputs="dim_bank_branch",
            name="build_dim_bank_branch",
        ),
    ])

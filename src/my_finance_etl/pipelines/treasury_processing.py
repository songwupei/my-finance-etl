"""司库数据处理 Pipeline — 构建维度表和事实表（含 entity_report_id 匹配）。"""
import hashlib
import logging
import polars as pl
from pathlib import Path
from kedro.pipeline import Pipeline, node
from kedro.config import OmegaConfigLoader
from kedro.framework.project import settings


def _build_entity_lookup(dim_org_tree: pl.DataFrame, manual_map: dict) -> dict:
    """预建 org_code → entity_report_id 查找表（避免逐行 filter）。"""
    lookup = dict(manual_map)
    for row in dim_org_tree.iter_rows(named=True):
        code = row.get("unit_code")
        if not code or code in lookup:
            continue
        suffix = row.get("suffix", "")
        # 优先 suffix=0 > 其他(排除1,9) > 9
        if suffix not in ("1", "9"):
            if suffix == "0" or code not in lookup:
                lookup[code] = row["entity_report_id"]
        elif suffix == "9" and code not in lookup:
            lookup[code] = row["entity_report_id"]
    return lookup


def build_account_dimensions_and_fact(
    parsed_treasury_account_info: pl.DataFrame,
    parsed_treasury_account_balance: pl.DataFrame,
    dim_organization_tree: pl.DataFrame,
    parameters: dict,
):
    """构建账户维度表和余额事实表 — 向量化版本，无逐行 filter。"""
    logger = logging.getLogger(__name__)

    if parsed_treasury_account_info.is_empty():
        logger.warning("No treasury account info data")
        return pl.DataFrame(), pl.DataFrame(), pl.DataFrame()

    # 手工映射表
    config_loader = OmegaConfigLoader(conf_source=settings.CONF_SOURCE)
    try:
        treasury_config = config_loader["treasury_loader"]
    except Exception:
        treasury_config = {}
    manual_map = treasury_config.get("unit_code_mapping", {})

    # --- entity_report_id: 预建 lookup → replace 批量匹配 ---
    logger.info("Resolving entity_report_id for treasury accounts...")
    lookup = _build_entity_lookup(dim_organization_tree, manual_map)
    account_info = parsed_treasury_account_info.with_columns(
        pl.col("org_code").replace(lookup, default=None).alias("entity_report_id")
    )
    matched_count = account_info["entity_report_id"].is_not_null().sum()
    logger.info(f"Entity ID matched: {matched_count}/{len(account_info)}")

    # --- dim_treasury_account_type: MD5 via map_elements (34 rows, trivial) ---
    account_types = account_info.select(["account_nature", "account_type"]).unique()
    account_types = account_types.drop_nulls(subset=["account_nature"])
    account_types = account_types.with_columns(
        pl.struct(["account_nature", "account_type"]).map_elements(
            lambda s: hashlib.md5(
                f"{s['account_nature']}|{s.get('account_type','')}".encode()
            ).hexdigest()[:8],
            return_dtype=pl.String,
        ).alias("type_id")
    )
    dim_account_type = account_types.rename({
        "account_nature": "type_label",
        "account_type": "category_label",
    }).select(["type_id", "type_label", "category_label"])
    dim_account_type = dim_account_type.unique(subset=["type_label"])

    # --- dim_treasury_account ---
    dim_account_cols = [
        "account_number", "account_name", "financial_institution",
        "opening_institution", "institution_code", "account_status",
        "country_region", "account_nature", "is_overseas", "bank_city",
        "open_date", "close_date", "is_partner_bank", "auth_channel",
        "auth_date", "is_auth_collection", "is_auth_payment",
        "currency", "account_usage", "is_visible", "is_system_settlement",
        "management_limit_wan", "is_limited", "approval_doc_no",
        "entity_report_id", "org_code", "unit_name", "unit_id",
        "sub_group_name", "source_file", "period",
    ]
    available_cols = [c for c in dim_account_cols if c in account_info.columns]
    dim_account = account_info.select(available_cols)
    dim_account = dim_account.unique(subset=["account_number", "org_code"])
    dim_account = dim_account.with_columns(
        pl.struct(["account_number", "org_code"]).map_elements(
            lambda s: hashlib.md5(
                f"{s['account_number']}|{s.get('org_code','')}".encode()
            ).hexdigest()[:12],
            return_dtype=pl.String,
        ).alias("account_id")
    )
    dim_account = dim_account.join(
        dim_account_type.select(["type_label", "type_id"]),
        left_on="account_nature", right_on="type_label", how="left",
    )

    # --- fact_treasury_account_balance ---
    if parsed_treasury_account_balance.is_empty():
        logger.warning("No treasury account balance data")
        return dim_account, dim_account_type, pl.DataFrame()

    account_lookup = account_info.select(
        ["account_number", "org_code", "entity_report_id"]
    ).unique(subset="account_number")
    acc_id_lookup = dim_account.select(["account_number", "account_id"]).unique(subset="account_number")

    fact_cols_balance = ["account_number", "balance", "converted_amount",
                         "currency", "balance_date", "is_partner_bank",
                         "is_overseas", "period"]
    fact_cols = [c for c in fact_cols_balance if c in parsed_treasury_account_balance.columns]
    fact_df = parsed_treasury_account_balance.select(fact_cols).join(
        account_lookup, on="account_number", how="left",
    ).join(
        acc_id_lookup, on="account_number", how="left",
    )
    # Ensure required columns exist
    for col, dtype in [("entity_report_id", pl.String), ("account_id", pl.String)]:
        if col not in fact_df.columns:
            fact_df = fact_df.with_columns(pl.lit(None).cast(dtype).alias(col))
    if "balance" in fact_df.columns:
        fact_df = fact_df.with_columns(pl.col("balance").cast(pl.Float64, strict=False).alias("balance_amount"))
    else:
        fact_df = fact_df.with_columns(pl.lit(None).cast(pl.Float64).alias("balance_amount"))
    if "converted_amount" not in fact_df.columns:
        fact_df = fact_df.with_columns(pl.lit(None).cast(pl.Float64).alias("converted_amount"))

    fact_df = fact_df.select([
        "account_id", "entity_report_id", "period",
        "balance_amount", "converted_amount", "currency",
        "balance_date", "is_partner_bank", "is_overseas",
    ]).unique()

    logger.info(f"Built dim_treasury_account: {len(dim_account)} rows, "
                f"dim_account_type: {len(dim_account_type)} rows, "
                f"fact_balance: {len(fact_df)} rows")
    return dim_account, dim_account_type, fact_df


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline([
        node(
            func=build_account_dimensions_and_fact,
            inputs=[
                "parsed_treasury_account_info",
                "parsed_treasury_account_balance",
                "dim_organization_tree",
                "parameters",
            ],
            outputs=[
                "dim_treasury_account",
                "dim_treasury_account_type",
                "fact_treasury_account_balance",
            ],
            name="build_treasury_dimensions_and_fact",
        ),
    ])

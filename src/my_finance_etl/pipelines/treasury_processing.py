"""司库数据处理 Pipeline — 构建维度表和事实表（含 entity_report_id 匹配）。"""
import hashlib
import logging
import pandas as pd
from pathlib import Path
from kedro.pipeline import Pipeline, node
from kedro.config import OmegaConfigLoader
from kedro.framework.project import settings


def resolve_entity_id(org_code: str, dim_org_tree: pd.DataFrame, unit_code_mapping: dict) -> str:
    """根据统一社会信用代码匹配 entity_report_id。

    规则：
    1. 在 dim_organization_tree 中查找 unit_code == org_code
    2. 排除 suffix 1（差额表）和 9（合并表）
    3. 优先取 suffix=0，否则取第一个剩余 suffix
    4. 未匹配则查手工映射表
    """
    if not org_code or pd.isna(org_code):
        return None

    matched = dim_org_tree[dim_org_tree["unit_code"] == str(org_code).strip()]
    if matched.empty:
        return unit_code_mapping.get(str(org_code).strip())

    suffixes = matched["suffix"].unique().tolist()
    valid = [s for s in suffixes if s not in ("1", "9")]

    if not valid:
        # 只有 1 和 9，取 suffix 9（合并口径）
        target = "9" if "9" in suffixes else suffixes[0]
    elif len(valid) == 1:
        target = valid[0]
    elif "0" in valid:
        target = "0"
    else:
        target = valid[0]

    row = matched[matched["suffix"] == target].iloc[0]
    return row["entity_report_id"]


def build_account_dimensions_and_fact(
    parsed_treasury_account_info: pd.DataFrame,
    parsed_treasury_account_balance: pd.DataFrame,
    dim_organization_tree: pd.DataFrame,
    parameters: dict,
):
    """构建账户维度表和余额事实表。

    Returns:
        dim_treasury_account, dim_treasury_account_type, fact_treasury_account_balance
    """
    logger = logging.getLogger(__name__)

    if parsed_treasury_account_info.empty:
        logger.warning("No treasury account info data, returning empty DataFrames")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # 加载手工映射表
    config_loader = OmegaConfigLoader(conf_source=settings.CONF_SOURCE)
    try:
        treasury_config = config_loader["treasury_loader"]
    except Exception:
        treasury_config = {}
    unit_code_mapping = treasury_config.get("unit_code_mapping", {})

    # --- entity_report_id 匹配 ---
    logger.info("Resolving entity_report_id for treasury accounts...")
    account_info = parsed_treasury_account_info.copy()
    account_info["entity_report_id"] = account_info["org_code"].apply(
        lambda code: resolve_entity_id(code, dim_organization_tree, unit_code_mapping)
    )
    matched_count = account_info["entity_report_id"].notna().sum()
    logger.info(f"Entity ID matched: {matched_count}/{len(account_info)}")

    # --- dim_treasury_account_type ---
    account_types = account_info[["account_nature", "account_type"]].drop_duplicates()
    account_types = account_types.dropna(subset=["account_nature"]).copy()
    account_types["type_id"] = account_types.apply(
        lambda r: hashlib.md5(
            f"{r['account_nature']}|{r.get('account_type','')}".encode()
        ).hexdigest()[:8],
        axis=1,
    )
    dim_account_type = account_types.rename(columns={
        "account_nature": "type_label",
        "account_type": "category_label",
    })[["type_id", "type_label", "category_label"]]
    dim_account_type = dim_account_type.drop_duplicates(subset=["type_label"])

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
    dim_account = account_info[available_cols].copy()
    dim_account = dim_account.drop_duplicates(subset=["account_number", "org_code"])
    dim_account["account_id"] = dim_account.apply(
        lambda r: hashlib.md5(
            f"{r['account_number']}|{r.get('org_code','')}".encode()
        ).hexdigest()[:12],
        axis=1,
    )
    dim_account = dim_account.merge(
        dim_account_type[["type_label", "type_id"]],
        left_on="account_nature", right_on="type_label", how="left",
    )

    # --- fact_treasury_account_balance ---
    if parsed_treasury_account_balance.empty:
        logger.warning("No treasury account balance data")
        return dim_account, dim_account_type, pd.DataFrame()

    # join 余额表 with account info (通过 银行账号) 获取 org_code 和 entity_report_id
    balance = parsed_treasury_account_balance.copy()
    account_lookup = account_info[["account_number", "org_code", "unit_name",
                                   "entity_report_id"]].drop_duplicates(subset="account_number")
    fact = balance.merge(account_lookup, on="account_number", how="left", suffixes=("_bal", "_info"))

    if "entity_report_id" not in fact.columns:
        fact["entity_report_id"] = None

    # add account_id from dim_account
    acc_id_lookup = dim_account[["account_number", "account_id"]].drop_duplicates(subset="account_number")
    fact = fact.merge(acc_id_lookup, on="account_number", how="left")

    fact_df = pd.DataFrame({
        "account_id": fact.get("account_id"),
        "entity_report_id": fact.get("entity_report_id"),
        "period": fact.get("period", account_info.get("period").iloc[0] if len(account_info) > 0 else ""),
        "balance_amount": pd.to_numeric(fact.get("balance"), errors="coerce"),
        "converted_amount": pd.to_numeric(fact.get("converted_amount"), errors="coerce"),
        "currency": fact.get("currency"),
        "balance_date": fact.get("balance_date"),
        "is_partner_bank": fact.get("is_partner_bank"),
        "is_overseas": fact.get("is_overseas"),
    })

    fact_df = fact_df.drop_duplicates()

    logger.info(f"Built dim_treasury_account: {len(dim_account)} rows")
    logger.info(f"Built dim_treasury_account_type: {len(dim_account_type)} rows")
    logger.info(f"Built fact_treasury_account_balance: {len(fact_df)} rows")

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

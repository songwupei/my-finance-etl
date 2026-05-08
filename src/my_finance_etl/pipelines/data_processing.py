"""Data processing pipeline for standardization and matching."""
import os
import sys
import polars as pl
import yaml
from kedro.pipeline import Pipeline, node

from ..matcher import StandardAccountMatcher

_AREACODE_PATH = os.path.expanduser(
    "~/NutstoreFiles/2-Code/1-MyPython/0-MyPyPkg/map_utils"
)
if _AREACODE_PATH not in sys.path:
    sys.path.insert(0, _AREACODE_PATH)


def standardize_report_data(
    parsed_report_data: pl.DataFrame,
    parameters: dict,
) -> pl.DataFrame:
    """Standardize report data using standard account matcher."""
    if parsed_report_data.is_empty():
        return pl.DataFrame()

    # Load configuration
    indicator_mapping_path = parameters.get("indicator_mapping_path", "conf/base/indicator_mapping.yml")

    # Load context rules, report type mapping, and standard accounts path from indicator_mapping.yml
    import yaml
    import os
    with open(indicator_mapping_path, "r", encoding="utf-8") as f:
        indicator_mapping = yaml.safe_load(f)
    context_rules = indicator_mapping.get("context_rules", [])
    report_type_names = indicator_mapping.get("report_type_names", {})

    # Get standard accounts path from indicator mapping
    standard_accounts_source = indicator_mapping.get("standard_accounts_source", {})
    standard_accounts_path = standard_accounts_source.get("path", "conf/base/standard_accounts.json")

    # Initialize matcher
    matcher = StandardAccountMatcher(standard_accounts_path, context_rules, report_type_names)

    # Process each row
    records = []
    for row in parsed_report_data.iter_rows(named=True):
        row_dict = row  # row is already a dict with named=True
        matched_account = matcher.match(row_dict)

        record = {
            "indicator_raw": row.get("indicator_raw"),
            "indicator_clean": row.get("indicator_clean"),
            "indicator_number": row.get("indicator_number"),
            "indicator_level": row.get("indicator_level"),
            "full_path": row.get("full_path"),
            "value_column": row.get("value_column"),
            "value": row.get("value"),
            "sheet_name": row.get("sheet_name"),
            "unit": row.get("unit"),
            "code": row.get("code"),
            "suffix": row.get("suffix"),
            "period": row.get("period"),
            "entity_report_id": row.get("entity_report_id"),
            "is_standardized": False,
            "standard_account_code": None,
            "standard_account_name": None,
            "report_category": row.get("report_category"),
            "top_level_account_name": row.get("top_level_account_name"),
        }

        if matched_account:
            # Get report_type from matched account, map to Chinese category name
            report_type = matched_account.get("report_type", "unknown")
            category = report_type_names.get(report_type, report_type)
            # 交叉验证：匹配结果的报表类别必须与 parser 章节检测一致
            parser_category = row.get("report_category")
            if parser_category and category != parser_category:
                matched_account = None  # 跨类别污染，丢弃此匹配
            else:
                record.update({
                    "is_standardized": True,
                    "standard_account_code": matched_account.get("account_code"),
                    "standard_account_name": matched_account.get("account_name"),
                    "report_category": category,
                })

        records.append(record)

    return pl.DataFrame(records)


def build_dimension_tables(
    parsed_base_info: pl.DataFrame,
    processed_report_data: pl.DataFrame,
    parameters: dict,
) -> dict:
    """Build dimension tables from parsed and processed data."""
    from china_areacode import ChinaDivision

    # 初始化地区展开
    china_div = ChinaDivision(standard_code_length=6)

    # 安全获取列值的辅助函数
    def _get(row, key, default=None):
        if key in parsed_base_info.columns:
            val = row.get(key)
            return val if val is not None else default
        return default

    dim_unit_report_records = []
    for row in parsed_base_info.iter_rows(named=True):
        unit_name = _get(row, "unit_name")
        if not unit_name:
            continue

        # 地区代码展开
        sasac_code = _get(row, "sasac_area_raw_code", "")
        sasac_name_raw = _get(row, "sasac_area_raw_name", "")
        area_info = china_div.get_areaname(sasac_code) if sasac_code else None

        province = (area_info or {}).get("province") or ""
        city = (area_info or {}).get("city") or ""
        area = (area_info or {}).get("area") or ""

        # sasac_area_name: 用展开的全称，覆盖原始简称
        sasac_area_name = f"{province}{city}{area}" if province else sasac_name_raw

        record = {
            "entity_report_id": _get(row, "entity_report_id"),
            "unit_name": unit_name,
            "code": _get(row, "code"),
            "suffix": _get(row, "suffix"),
            "unit": _get(row, "unit"),
            "period": _get(row, "period"),
            # 新增字段
            "country_region_code": _get(row, "country_region_raw_code", ""),
            "country_region_name": _get(row, "country_region_raw_name", ""),
            "sasac_area_code": sasac_code or "",
            "sasac_area_name": sasac_area_name or "",
            "province": province,
            "city": city,
            "area": area,
            "enterprise_address": _get(row, "enterprise_address", ""),
        }
        dim_unit_report_records.append(record)

    dim_unit_report = pl.DataFrame(dim_unit_report_records)

    # dim_caliber ... (rest unchanged)
    dim_caliber = pl.DataFrame([{
        "caliber_id": "1",
        "caliber_name": "合并口径",
        "description": "包含所有子公司的合并数据",
    }])

    # dim_report_category
    # Defensive check: ensure report_category column exists
    if "report_category" not in processed_report_data.columns:
        # Create column with default value "unknown"
        processed_report_data = processed_report_data.with_columns(pl.lit("unknown").alias("report_category"))

    unique_categories = processed_report_data["report_category"].unique().to_list()
    category_records = [
        {
            "category_id": str(i + 1),
            "category_name": cat,
        }
        for i, cat in enumerate(unique_categories) if cat is not None
    ]

    # Ensure at least one record to avoid empty DataFrame
    if not category_records:
        category_records = [{
            "category_id": "1",
            "category_name": "unknown",
        }]

    dim_report_category = pl.DataFrame(category_records)

    # dim_period
    # Defensive check: ensure period column exists
    if "period" not in processed_report_data.columns:
        # Create empty period column if missing
        processed_report_data = processed_report_data.with_columns(pl.lit(None).alias("period"))

    unique_periods = processed_report_data["period"].unique().to_list()
    dim_period_records = []
    for period in unique_periods:
        if period is not None and period:
            try:
                year, month, _ = period.split("-")
                period_name = f"{year}年{int(month):02d}月"
                dim_period_records.append({
                    "period_id": period,
                    "period_name": period_name,
                    "year": int(year),
                    "month": int(month),
                })
            except (ValueError, AttributeError):
                continue

    # Ensure at least one record to avoid empty DataFrame
    if not dim_period_records:
        dim_period_records = [{
            "period_id": "1900-01-01",
            "period_name": "1900年01月",
            "year": 1900,
            "month": 1,
        }]

    dim_period = pl.DataFrame(dim_period_records)

    # dim_standard_account (from standard accounts JSON)
    import json

    # Load configuration from indicator_mapping.yml
    indicator_mapping_path = parameters.get("indicator_mapping_path", "conf/base/indicator_mapping.yml")
    with open(indicator_mapping_path, "r", encoding="utf-8") as f:
        indicator_mapping = yaml.safe_load(f)

    # Get standard accounts path from indicator mapping
    standard_accounts_source = indicator_mapping.get("standard_accounts_source", {})
    standard_accounts_path = standard_accounts_source.get("path", "conf/base/standard_accounts.json")

    # Load standard accounts
    with open(standard_accounts_path, "r", encoding="utf-8") as f:
        standard_accounts = json.load(f)

    # Load report type mapping
    report_type_names = indicator_mapping.get("report_type_names", {})

    dim_standard_account_records = []
    for sort_idx, report in enumerate(standard_accounts["reports"]):
        for acc in report["accounts"]:
            # Map report_type to Chinese category name
            category = report_type_names.get(report["report_type"], report["report_type"])
            record = {
                "account_code": acc["account_code"],
                "account_name": acc["account_name"],
                "report_category": category,
                "account_code_dash": acc.get("account_code_dash", acc["account_code"].replace(".", "-")),
                "standard_path": acc.get("standard_path"),
                "match_priority": acc.get("match_rules", {}).get("match_priority", 0),
                "sort_order": sort_idx,
            }
            dim_standard_account_records.append(record)

    dim_standard_account = pl.DataFrame(dim_standard_account_records)

    return (
        dim_unit_report,
        dim_caliber,
        dim_report_category,
        dim_period,
        dim_standard_account,
    )


def create_pipeline(**kwargs) -> Pipeline:
    """Create the data processing pipeline."""
    return Pipeline(
        [
            node(
                func=standardize_report_data,
                inputs=["parsed_report_data", "parameters"],
                outputs="processed_report_data",
                name="standardize_report_data",
            ),
            node(
                func=build_dimension_tables,
                inputs=["parsed_base_info", "processed_report_data", "parameters"],
                outputs=[
                    "dim_unit_report",
                    "dim_caliber",
                    "dim_report_category",
                    "dim_period",
                    "dim_standard_account",
                ],
                name="build_dimension_tables",
            ),
        ]
    )

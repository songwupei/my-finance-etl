"""Data warehouse pipeline for loading data into DuckDB."""
import pandas as pd
import uuid
from datetime import datetime
from pathlib import Path
from kedro.pipeline import Pipeline, node

from ..tree_builder import build_organization_tree


def build_fact_table(
    processed_report_data: pd.DataFrame,
    dim_unit_report: pd.DataFrame,
    dim_caliber: pd.DataFrame,
    dim_report_category: pd.DataFrame,
    dim_period: pd.DataFrame,
    dim_standard_account: pd.DataFrame,
) -> pd.DataFrame:
    """Build fact_finance_data table by joining with dimension tables."""
    if processed_report_data.empty:
        return pd.DataFrame()

    # Prepare fact data
    fact_records = []
    for _, row in processed_report_data.iterrows():
        # Find dimension IDs
        entity_report_id = row.get("entity_report_id")
        period_id = row.get("period")
        account_code = row.get("standard_account_code")
        value_column = row.get("value_column")

        # Default values if dimension IDs not found
        caliber_id = "1"  # default caliber
        category_id = None

        # Find category_id from report_category
        report_category = row.get("report_category")
        if pd.notna(report_category):
            category_match = dim_report_category[dim_report_category["category_name"] == report_category]
            if not category_match.empty:
                category_id = category_match.iloc[0]["category_id"]

        fact_records.append({
            "id": str(uuid.uuid4()),
            "entity_report_id": entity_report_id,
            "period_id": period_id,
            "account_code": account_code,
            "caliber_id": caliber_id,
            "category_id": category_id,
            "value": row.get("value"),
            "value_column": value_column,
            "is_standardized": row.get("is_standardized", False),
            "source_file": row.get("sheet_name", ""),
            "raw_path": row.get("full_path", ""),
            "top_level_account_name": row.get("top_level_account_name", ""),
            "etl_created_at": datetime.now().isoformat(),
        })

    fact_df = pd.DataFrame(fact_records)

    # Filter out records with missing essential dimension IDs
    fact_df = fact_df[
        fact_df["entity_report_id"].notna() &
        fact_df["period_id"].notna() &
        fact_df["account_code"].notna()
    ]

    return fact_df


def load_to_data_warehouse(
    dim_unit_report: pd.DataFrame,
    dim_caliber: pd.DataFrame,
    dim_report_category: pd.DataFrame,
    dim_period: pd.DataFrame,
    dim_standard_account: pd.DataFrame,
    dim_organization_tree: pd.DataFrame,
    fact_finance_data: pd.DataFrame,
    parameters: dict = None,
) -> tuple:
    """加载所有维度表和事实表到数据仓库，并同步到DuckDB。"""
    import logging
    logger = logging.getLogger(__name__)

    # 先确保Parquet文件存在
    try:
        for df_name in ["dim_unit_report", "dim_caliber", "dim_report_category",
                        "dim_period", "dim_standard_account",
                        "dim_organization_tree", "fact_finance_data"]:
            parquet_path = f"data/03_primary/{df_name}.parquet"
            if not Path(parquet_path).exists():
                logger.warning(f"Parquet文件不存在: {parquet_path}")
    except Exception as e:
        logger.error(f"检查Parquet文件失败: {e}")

    # 尝试加载DuckDB数据仓库
    duckdb_success = False
    try:
        from ..duckdb_data_warehouse import DuckDBDataWarehouse

        warehouse = DuckDBDataWarehouse(parameters=parameters)
        warehouse.create_schema()
        warehouse.load_all_tables()
        warehouse.optimize_for_analytical_queries()

        stats = warehouse.get_database_stats()
        logger.info(f"DuckDB数据仓库加载成功: {len(stats['tables'])}个表")
        duckdb_success = True

        warehouse.close()

    except Exception as e:
        logger.warning(f"DuckDB加载失败，使用Parquet中间存储: {e}")
        # 记录错误但不中断流程

    # 返回数据框供后续使用
    return (
        dim_unit_report,
        dim_caliber,
        dim_report_category,
        dim_period,
        dim_standard_account,
        dim_organization_tree,
        fact_finance_data,
    )


def create_pipeline(**kwargs) -> Pipeline:
    """Create the data warehouse pipeline."""
    return Pipeline(
        [
            node(
                func=build_fact_table,
                inputs=[
                    "processed_report_data",
                    "dim_unit_report",
                    "dim_caliber",
                    "dim_report_category",
                    "dim_period",
                    "dim_standard_account",
                ],
                outputs="fact_finance_data",
                name="build_fact_table",
            ),
            node(
                func=build_organization_tree,
                inputs=["parsed_base_info", "dim_unit_report", "parameters"],
                outputs="dim_organization_tree",
                name="build_organization_tree",
            ),
            node(
                func=load_to_data_warehouse,
                inputs=[
                    "dim_unit_report",
                    "dim_caliber",
                    "dim_report_category",
                    "dim_period",
                    "dim_standard_account",
                    "dim_organization_tree",
                    "fact_finance_data",
                    "parameters",
                ],
                outputs=[
                    "loaded_dim_unit_report",
                    "loaded_dim_caliber",
                    "loaded_dim_report_category",
                    "loaded_dim_period",
                    "loaded_dim_standard_account",
                    "loaded_dim_organization_tree",
                    "loaded_fact_finance_data",
                ],
                name="load_to_data_warehouse",
            ),
        ]
    )
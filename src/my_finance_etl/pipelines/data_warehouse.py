"""Data warehouse pipeline for loading data into DuckDB."""
import polars as pl
import uuid
from datetime import datetime
from pathlib import Path
from kedro.pipeline import Pipeline, node

from ..tree_builder import build_organization_tree


def build_fact_table(
    processed_report_data: pl.DataFrame,
    dim_unit_report: pl.DataFrame,
    dim_caliber: pl.DataFrame,
    dim_report_category: pl.DataFrame,
    dim_period: pl.DataFrame,
    dim_standard_account: pl.DataFrame,
) -> pl.DataFrame:
    """Build fact_finance_data — vectorized with polars expressions, no row loop."""
    if processed_report_data.is_empty():
        return pl.DataFrame()

    # Resolve category_id via left join (tiny dim, fast)
    # Cast both sides to Utf8 to avoid null vs str type mismatch
    fact_df = processed_report_data.with_columns(
        pl.col("report_category").cast(pl.Utf8)
    ).join(
        dim_report_category.select(
            pl.col("category_name").cast(pl.Utf8).alias("report_category"),
            pl.col("category_id"),
        ),
        on="report_category",
        how="left",
    )

    n = fact_df.height
    etl_ts = datetime.now().isoformat()

    fact_df = fact_df.select(
        pl.Series("id", [str(uuid.uuid4()) for _ in range(n)]),
        pl.col("entity_report_id"),
        pl.col("period").alias("period_id"),
        pl.col("standard_account_code").alias("account_code"),
        pl.lit("1").alias("caliber_id"),
        pl.col("category_id"),
        pl.col("value"),
        pl.col("value_column"),
        pl.col("is_standardized").fill_null(False),
        pl.col("sheet_name").fill_null("").alias("source_file"),
        pl.col("full_path").fill_null("").str.replace_all(r'\s+', ' ').str.strip_chars().alias("raw_path"),
        pl.col("top_level_account_name").fill_null(""),
        pl.lit(etl_ts).alias("etl_created_at"),
    ).filter(
        pl.col("entity_report_id").is_not_null() &
        pl.col("period_id").is_not_null() &
        pl.col("account_code").is_not_null()
    )

    return fact_df


def load_to_data_warehouse(
    dim_unit_report: pl.DataFrame,
    dim_caliber: pl.DataFrame,
    dim_report_category: pl.DataFrame,
    dim_period: pl.DataFrame,
    dim_standard_account: pl.DataFrame,
    dim_organization_tree: pl.DataFrame,
    fact_finance_data: pl.DataFrame,
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
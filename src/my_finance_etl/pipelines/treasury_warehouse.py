"""司库数据入库 Pipeline — 加载司库维度表和事实表到 DuckDB。"""
import logging
import polars as pl
from kedro.pipeline import Pipeline, node


def load_treasury_to_warehouse(
    dim_treasury_account: pl.DataFrame,
    dim_treasury_account_type: pl.DataFrame,
    fact_treasury_account_balance: pl.DataFrame,
    dim_bank_branch: pl.DataFrame,
    dim_unit_geo: pl.DataFrame,
    parameters: dict = None,
) -> tuple:
    """将司库表加载到 DuckDB 数据仓库。"""
    logger = logging.getLogger(__name__)

    try:
        from ..duckdb_data_warehouse import DuckDBDataWarehouse

        warehouse = DuckDBDataWarehouse(parameters=parameters)
        warehouse.load_treasury_tables(
            dim_treasury_account,
            dim_treasury_account_type,
            fact_treasury_account_balance,
            dim_bank_branch,
        )
        if not dim_unit_geo.is_empty():
            warehouse.conn.register("_dim_ug", dim_unit_geo)
            warehouse.conn.execute(
                "CREATE OR REPLACE TABLE finance_data.dim_unit_geo AS SELECT * FROM _dim_ug"
            )
            warehouse.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ug_entity ON finance_data.dim_unit_geo(entity_report_id)"
            )
            logger.info("dim_unit_geo synced to DuckDB: %d rows", dim_unit_geo.height)
        warehouse.close()
        logger.info("Treasury tables loaded to DuckDB")

    except Exception as e:
        logger.warning(f"DuckDB treasury load failed: {e}")

    return (
        dim_treasury_account,
        dim_treasury_account_type,
        fact_treasury_account_balance,
        dim_bank_branch,
        dim_unit_geo,
    )


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline([
        node(
            func=load_treasury_to_warehouse,
            inputs=[
                "dim_treasury_account",
                "dim_treasury_account_type",
                "fact_treasury_account_balance",
                "dim_bank_branch_enriched",
                "dim_unit_geo",
                "parameters",
            ],
            outputs=[
                "loaded_treasury_dim_account",
                "loaded_treasury_dim_account_type",
                "loaded_treasury_fact_balance",
                "loaded_dim_bank_branch_enriched",
                "loaded_dim_unit_geo",
            ],
            name="load_treasury_to_warehouse",
        ),
    ])

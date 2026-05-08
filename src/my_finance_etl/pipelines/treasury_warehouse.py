"""司库数据入库 Pipeline — 加载司库维度表和事实表到 DuckDB。"""
import logging
import polars as pl
from kedro.pipeline import Pipeline, node


def load_treasury_to_warehouse(
    dim_treasury_account: pl.DataFrame,
    dim_treasury_account_type: pl.DataFrame,
    fact_treasury_account_balance: pl.DataFrame,
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
        )
        warehouse.close()
        logger.info("Treasury tables loaded to DuckDB")

    except Exception as e:
        logger.warning(f"DuckDB treasury load failed: {e}")

    return (
        dim_treasury_account,
        dim_treasury_account_type,
        fact_treasury_account_balance,
    )


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline([
        node(
            func=load_treasury_to_warehouse,
            inputs=[
                "dim_treasury_account",
                "dim_treasury_account_type",
                "fact_treasury_account_balance",
                "parameters",
            ],
            outputs=[
                "loaded_treasury_dim_account",
                "loaded_treasury_dim_account_type",
                "loaded_treasury_fact_balance",
            ],
            name="load_treasury_to_warehouse",
        ),
    ])

from kedro.pipeline import Pipeline

from .pipelines.data_ingestion import create_pipeline as ingest_pipeline
from .pipelines.data_ingestion_polars import create_pipeline as ingest_polars_pipeline
from .pipelines.data_processing import create_pipeline as process_pipeline
from .pipelines.data_warehouse import create_pipeline as warehouse_pipeline
from .pipelines.treasury_ingestion import create_pipeline as treasury_ingest_pipeline
from .pipelines.treasury_processing import create_pipeline as treasury_process_pipeline
from .pipelines.treasury_warehouse import create_pipeline as treasury_warehouse_pipeline


def register_pipelines():
    """Register the project's pipelines."""
    treasury_full = treasury_ingest_pipeline() + treasury_process_pipeline() + treasury_warehouse_pipeline()
    return {
        "__default__": ingest_pipeline() + process_pipeline() + warehouse_pipeline() + treasury_full,
        "ingest": ingest_pipeline(),
        "ingest_polars": ingest_polars_pipeline(),
        "process": process_pipeline(),
        "warehouse": warehouse_pipeline(),
        "finance_report": ingest_polars_pipeline() + process_pipeline() + warehouse_pipeline(),
        "treasury_data": treasury_full,
    }

"""Pipelines package for My Finance ETL."""

# Export create_pipeline functions for easier import
from .data_ingestion_polars import create_pipeline as create_ingestion_pipeline
from .data_processing import create_pipeline as create_processing_pipeline
from .data_warehouse import create_pipeline as create_warehouse_pipeline

__all__ = [
    "create_ingestion_pipeline",
    "create_processing_pipeline",
    "create_warehouse_pipeline",
]
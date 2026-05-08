"""Polars优化的数据摄入pipeline，针对1500+个Excel文件提供并行处理。"""
import polars as pl
from kedro.pipeline import Pipeline, node
import logging

logger = logging.getLogger(__name__)


def batch_parse_excel_files_polars(catalog) -> tuple:
    """使用Polars批量解析Excel文件。"""
    from ..polars_optimizer import create_polars_pipeline_node
    return create_polars_pipeline_node(catalog)


def create_pipeline(**kwargs) -> Pipeline:
    """创建Polars优化的数据摄入pipeline。"""
    return Pipeline(
        [
            node(
                func=batch_parse_excel_files_polars,
                inputs=["catalog"],
                outputs=["parsed_base_info", "parsed_report_data"],
                name="parse_excel_files_polars",
            ),
        ]
    )

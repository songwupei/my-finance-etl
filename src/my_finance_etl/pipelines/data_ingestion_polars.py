"""
Polars优化的数据摄入pipeline，针对1500+个Excel文件提供并行处理。
"""
import pandas as pd
from kedro.pipeline import Pipeline, node
import logging

logger = logging.getLogger(__name__)


def batch_parse_excel_files_polars(catalog) -> tuple:
    """
    使用Polars批量解析Excel文件（优化的版本）。

    与原有版本保持相同的接口，内部使用Polars并行处理。
    """
    try:
        # 尝试使用Polars优化版本
        from ..polars_optimizer import create_polars_pipeline_node
        return create_polars_pipeline_node(catalog)
    except ImportError as e:
        logger.warning(f"Polars优化不可用，回退到原有Pandas实现: {e}")
        # 回退到原有实现
        from .data_ingestion import batch_parse_excel_files
        return batch_parse_excel_files(catalog)
    except Exception as e:
        logger.error(f"Polars处理失败，回退到原有实现: {e}")
        from .data_ingestion import batch_parse_excel_files
        return batch_parse_excel_files(catalog)


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
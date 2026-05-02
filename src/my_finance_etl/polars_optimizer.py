"""
Polars优化处理器，用于加速Excel文件处理。
针对1500+个Excel文件提供并行处理和内存优化。
"""
import polars as pl
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 导入项目自制的PolarsExcelDataset（符合用户要求）
from .io.polars_excel_dataset import PolarsExcelDataset

logger = logging.getLogger(__name__)


class PolarsExcelProcessor:
    """使用Polars优化Excel文件处理的处理器。"""

    def __init__(self, max_workers: int = 4, chunk_size: int = 100):
        """
        初始化Polars处理器。

        Args:
            max_workers: 并行处理的最大线程数
            chunk_size: 批量处理的文件大小
        """
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self._lock = threading.Lock()

    def process_excel_batch_polars(
        self,
        files: List[Dict[str, Any]],
        config: Dict[str, Any]
    ) -> Tuple[pl.DataFrame, pl.DataFrame]:
        """
        使用Polars并行处理Excel文件批次。

        Args:
            files: 文件信息列表，每个元素包含path、code、suffix、month_folder等
            config: 解析配置（从finance_loader.yml加载）

        Returns:
            (base_info_df, report_data_df): Polars DataFrame元组
        """
        logger.info(f"开始并行处理 {len(files)} 个Excel文件，使用 {self.max_workers} 个线程")

        all_base_info = []
        all_report_data = []

        # 分批次处理以避免内存溢出
        for batch_start in range(0, len(files), self.chunk_size):
            batch_end = min(batch_start + self.chunk_size, len(files))
            batch_files = files[batch_start:batch_end]

            logger.info(f"处理批次 {batch_start//self.chunk_size + 1}: {batch_start}-{batch_end-1}")

            # 并行处理当前批次
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_file = {
                    executor.submit(self._process_single_file_polars, file_info, config): file_info
                    for file_info in batch_files
                }

                for future in as_completed(future_to_file):
                    file_info = future_to_file[future]
                    try:
                        base_info_df, report_df = future.result()
                        if base_info_df is not None and not base_info_df.is_empty():
                            all_base_info.append(base_info_df)
                        if report_df is not None and not report_df.is_empty():
                            all_report_data.append(report_df)
                    except Exception as e:
                        logger.warning(f"处理文件失败 {file_info.get('path', 'unknown')}: {e}")

        # 合并结果
        if all_base_info:
            base_info_combined = pl.concat(all_base_info, how="vertical")
            logger.info(f"基础信息合并完成: {base_info_combined.height} 行")
        else:
            base_info_combined = pl.DataFrame()
            logger.warning("没有找到基础信息数据")

        if all_report_data:
            report_data_combined = pl.concat(all_report_data, how="vertical")
            logger.info(f"报表数据合并完成: {report_data_combined.height} 行")
        else:
            report_data_combined = pl.DataFrame()
            logger.warning("没有找到报表数据")

        return base_info_combined, report_data_combined

    def _process_single_file_polars(
        self,
        file_info: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Tuple[Optional[pl.DataFrame], Optional[pl.DataFrame]]:
        """
        处理单个Excel文件，使用Polars优化。

        Args:
            file_info: 文件信息字典
            config: 解析配置

        Returns:
            (base_info_df, report_df): 单个文件的Polars DataFrame
        """
        filepath = file_info.get("path")
        if not filepath or not Path(filepath).exists():
            logger.warning(f"文件不存在: {filepath}")
            return None, None

        try:
            # 使用项目自制的PolarsExcelDataset读取Excel（符合用户要求）
            dataset = PolarsExcelDataset(
                filepath=str(filepath),
                load_args={
                    "sheet_name": None,  # 读取所有工作表（参数名修正为单数）
                    "engine": "calamine",  # 高性能Excel引擎
                    "infer_schema_length": 1000
                }
            )

            # 加载数据 - 返回Dict[str, pl.DataFrame]或单个pl.DataFrame
            excel_data = dataset.load()

            # 提取元数据
            metadata = {
                "unit": file_info.get("unit"),
                "code": file_info.get("code"),
                "suffix": file_info.get("suffix"),
                "month_folder": file_info.get("month_folder"),
                "period": file_info.get("period"),
                "entity_report_id": file_info.get("entity_report_id"),
                "file_path": str(filepath)
            }

            # 解析工作表 - 处理PolarsExcelDataset的返回值
            base_info_records = []
            report_data_records = []

            # excel_data可能是Dict[str, pl.DataFrame]或单个pl.DataFrame
            sheets_dict = {}
            if isinstance(excel_data, dict):
                sheets_dict = excel_data
            elif isinstance(excel_data, pl.DataFrame):
                # 单个工作表，使用默认名称
                sheets_dict = {"Sheet1": excel_data}
            else:
                logger.warning(f"不支持的数据类型: {type(excel_data)}")
                return None, None

            for sheet_name, df in sheets_dict.items():
                sheet_type, override = self._identify_sheet_type(sheet_name, config)

                if sheet_type == "base_info":
                    base_info = self._parse_base_info_sheet_polars(df, override)
                    if base_info:
                        base_info.update(metadata)
                        base_info_records.append(base_info)
                elif sheet_type == "report_data":
                    report_df = self._parse_report_sheet_polars(df, sheet_name, override, metadata)
                    if report_df is not None and not report_df.is_empty():
                        report_data_records.append(report_df)

            # 转换为DataFrame
            if base_info_records:
                base_info_df = pl.DataFrame(base_info_records)
            else:
                base_info_df = pl.DataFrame()

            if report_data_records:
                report_df = pl.concat(report_data_records, how="vertical")
            else:
                report_df = pl.DataFrame()

            logger.debug(f"文件处理成功: {filepath}, 基础信息: {len(base_info_records)}条, 报表数据: {report_df.height if report_df is not None else 0}行")

            return base_info_df, report_df

        except Exception as e:
            logger.error(f"处理文件失败 {filepath}: {e}")
            return None, None

    def _identify_sheet_type(
        self,
        sheet_name: str,
        config: Dict[str, Any]
    ) -> Tuple[str, Optional[Dict]]:
        """识别工作表类型（与FinanceExcelParser兼容）"""
        patterns = config.get("sheet_identification", {})
        overrides = config.get("sheet_overrides", {})

        # 检查基础信息模式
        base_info_patterns = patterns.get("base_info_pattern", [])
        for pattern in base_info_patterns:
            if pattern in sheet_name:
                override = self._get_sheet_override(sheet_name, overrides)
                return "base_info", override

        # 检查报表数据模式
        report_patterns = patterns.get("report_data_pattern", [])
        for pattern in report_patterns:
            if pattern in sheet_name:
                override = self._get_sheet_override(sheet_name, overrides)
                return "report_data", override

        return "other", None

    def _get_sheet_override(
        self,
        sheet_name: str,
        overrides: Dict[str, Dict]
    ) -> Optional[Dict]:
        """获取工作表覆盖配置"""
        for pattern, cfg in overrides.items():
            if pattern in sheet_name:
                return cfg
        return None

    def _parse_base_info_sheet_polars(
        self,
        df: pl.DataFrame,
        override: Optional[Dict] = None
    ) -> Optional[Dict]:
        """解析基础信息工作表，返回字段字典"""
        result = {}
        field_mapping = (override or {}).get("field_mapping", {})

        try:
            if field_mapping and df.shape[1] >= 2:
                # 使用field_mapping逻辑
                for row in df.iter_rows(named=True):
                    field_cell = row.get(df.columns[0])
                    if field_cell is None:
                        continue

                    field_str = str(field_cell).strip()
                    if not field_str:
                        continue

                    # 检查是否匹配field_mapping中的任何模式
                    for pattern, field_name in field_mapping.items():
                        if pattern in field_str:
                            # 取同一行的第二列作为值
                            value_cell = row.get(df.columns[1]) if len(df.columns) > 1 else None
                            if value_cell is not None:
                                result[field_name] = str(value_cell).strip()
                            break
            else:
                # 默认：A列是字段名，B列是值
                for row in df.iter_rows(named=True):
                    if len(df.columns) >= 2:
                        key = row.get(df.columns[0])
                        val = row.get(df.columns[1])
                        if key is not None and val is not None:
                            result[str(key).strip()] = str(val).strip()

            return result if result else None

        except Exception as e:
            logger.warning(f"解析基础信息工作表失败: {e}")
            return None

    def _parse_report_sheet_polars(
        self,
        df: pl.DataFrame,
        sheet_name: str,
        override: Optional[Dict],
        file_meta: Dict[str, Any]
    ) -> Optional[pl.DataFrame]:
        """解析报表数据工作表，返回Polars DataFrame"""
        try:
            rules = override or {}
            default_rules = {
                "skip_rows": 0,
                "header_row": 0,
                "indicator_column": 0,
                "value_columns_pattern": [r"\d{4}-\d{2}"]
            }

            # 合并规则
            skip_rows = rules.get("skip_rows", default_rules["skip_rows"])
            header_row = rules.get("header_row", default_rules["header_row"])
            indicator_col = rules.get("indicator_column", default_rules["indicator_column"])

            # 跳过指定行数
            if skip_rows > 0:
                df = df.slice(skip_rows)

            # 设置表头
            if header_row is not None and header_row >= 0 and header_row < df.height:
                # 获取表头行
                header_values = df.row(header_row)
                # 设置列名
                df = df.slice(header_row + 1)
                df.columns = [str(val) if val is not None else f"col_{i}" for i, val in enumerate(header_values)]

            # 识别指标列
            indicator_col_idx = None
            if isinstance(indicator_col, int) and indicator_col < len(df.columns):
                indicator_col_idx = indicator_col
            elif isinstance(indicator_col, str):
                for i, col in enumerate(df.columns):
                    if col == indicator_col:
                        indicator_col_idx = i
                        break

            # 识别数值列
            value_cols = []
            patterns = rules.get("value_columns_pattern", default_rules["value_columns_pattern"])
            for i, col in enumerate(df.columns):
                col_str = str(col)
                for pattern in patterns:
                    import re
                    if re.search(pattern, col_str):
                        value_cols.append(i)
                        break

            if not value_cols:
                # 默认：选择数值类型的列
                for i, col in enumerate(df.columns):
                    try:
                        # 尝试转换第一行的值为数值
                        first_val = df[0, i]
                        if first_val is not None:
                            float(str(first_val))
                            value_cols.append(i)
                    except:
                        pass

            if not value_cols:
                logger.warning(f"工作表 {sheet_name} 中未找到数值列")
                return pl.DataFrame()

            # 构建记录
            records = []
            for row_idx in range(df.height):
                indicator_raw = ""
                if indicator_col_idx is not None:
                    indicator_val = df[row_idx, indicator_col_idx]
                    indicator_raw = str(indicator_val) if indicator_val is not None else ""

                if not indicator_raw or indicator_raw == "nan":
                    continue

                # 简化处理：直接使用原始文本
                clean_name = indicator_raw.strip()
                level = 1

                # 处理每个数值列
                for val_col_idx in value_cols:
                    val_col_name = str(df.columns[val_col_idx])
                    val = df[row_idx, val_col_idx]

                    try:
                        if val is not None:
                            val_float = float(str(val))
                        else:
                            val_float = 0.0
                    except (ValueError, TypeError):
                        val_float = 0.0

                    record = {
                        "indicator_raw": indicator_raw,
                        "indicator_clean": clean_name,
                        "indicator_number": None,
                        "indicator_level": level,
                        "full_path": clean_name,
                        "value_column": val_col_name,
                        "value": val_float,
                        "sheet_name": sheet_name,
                        **file_meta
                    }
                    records.append(record)

            if records:
                return pl.DataFrame(records)
            else:
                return pl.DataFrame()

        except Exception as e:
            logger.error(f"解析报表工作表 {sheet_name} 失败: {e}")
            return pl.DataFrame()

    def convert_to_pandas_if_needed(self, df: pl.DataFrame) -> pd.DataFrame:
        """将Polars DataFrame转换为Pandas DataFrame（如果需要）"""
        if isinstance(df, pl.DataFrame):
            return df.to_pandas()
        elif isinstance(df, pd.DataFrame):
            return df
        else:
            raise TypeError(f"不支持的类型: {type(df)}")


def create_polars_pipeline_node(
    catalog: Dict[str, Any],
    config_path: str = "conf/base/finance_loader.yml"
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    创建Polars优化的pipeline节点函数。

    Args:
        catalog: Kedro目录
        config_path: 配置文件路径

    Returns:
        (parsed_base_info, parsed_report_data): Pandas DataFrame元组
    """
    import yaml
    from pathlib import Path
    import logging

    logger = logging.getLogger(__name__)

    # 修复1：正确导入settings模块
    from kedro.framework.project import settings

    # 加载配置
    config_file = Path(settings.CONF_SOURCE) / config_path if not Path(config_path).is_absolute() else Path(config_path)
    if not config_file.exists():
        logger.error(f"配置文件不存在: {config_file}")
        return pd.DataFrame(), pd.DataFrame()

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 修复2：简化文件获取逻辑，不依赖hooks
    files = []
    try:
        # 尝试从catalog获取文件列表
        if "excel_files" in catalog:
            files = catalog["excel_files"]
        else:
            # 备选方案：从配置中获取基础路径
            base_path = Path(config.get("data_source", {}).get("base_path", "data/01_raw"))
            month_pattern = config.get("data_source", {}).get("month_folder_pattern", r"\d{4}年\d{1,2}月")

            # 简单文件扫描
            import re
            if base_path.exists():
                month_folders = [d for d in base_path.iterdir() if d.is_dir() and re.search(month_pattern, d.name)]
                for month_folder in month_folders:
                    excel_files = list(month_folder.glob("*.xlsx")) + list(month_folder.glob("*.xls"))
                    for file_path in excel_files:
                        # 解析文件名获取元数据
                        match = re.search(r"(\d{18}[A-Za-z])-(\d)", file_path.stem)
                        if match:
                            code = match.group(1)
                            suffix = match.group(2)
                            files.append({
                                "path": str(file_path),
                                "code": code,
                                "suffix": suffix,
                                "month_folder": month_folder.name,
                                "unit": file_path.stem.split("（")[0] if "（" in file_path.stem else file_path.stem
                            })
    except Exception as e:
        logger.warning(f"获取文件列表失败: {e}")
        return pd.DataFrame(), pd.DataFrame()

    if not files:
        logger.warning("没有找到Excel文件")
        return pd.DataFrame(), pd.DataFrame()

    # 使用Polars处理器
    processor = PolarsExcelProcessor(max_workers=4, chunk_size=50)
    base_info_polars, report_data_polars = processor.process_excel_batch_polars(files, config)

    # 转换为Pandas以保持兼容性
    base_info_pandas = processor.convert_to_pandas_if_needed(base_info_polars)
    report_data_pandas = processor.convert_to_pandas_if_needed(report_data_polars)

    logger.info(f"Polars处理完成: {len(base_info_pandas)} 条基础信息, {len(report_data_pandas)} 条报表数据")

    return base_info_pandas, report_data_pandas
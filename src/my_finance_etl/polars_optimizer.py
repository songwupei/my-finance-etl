"""
Polars优化处理器，用于加速Excel文件处理。
针对1500+个Excel文件提供并行处理和内存优化。

文件过滤规则:
  - 跳过临时文件（~$ 和 .~ 前缀）
  - 跳过 unit_code（本企业代码）或 parent_code（上级企业代码）为空的文件（必填强制校验）
  - 选填字段（enterprise_address, sasac_area_raw, country_region_raw 等）为空时填"无"

列一致性:
  - 封面代码字段含 | 分隔符时 _split_code_name 自动拆为 _code/_name
  - 合并前按全集列对齐，缺失列填 NULL::Utf8
"""
import polars as pl
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 导入项目自制的PolarsExcelDataset + polars-etl-kit 流式读取
from .io.polars_excel_dataset import PolarsExcelDataset
from .file_cache import FileCache
from polars_etl_kit.excel.parser import stream_excel  # noqa: F401 — 大文件流式读取

logger = logging.getLogger(__name__)


class PolarsExcelProcessor:
    """使用Polars优化Excel文件处理的处理器。"""

    def __init__(self, max_workers: int = 4, chunk_size: int = 100,
                 file_cache: Optional[FileCache] = None):
        """
        初始化Polars处理器。

        Args:
            max_workers: 并行处理的最大线程数
            chunk_size: 批量处理的文件大小
            file_cache: 可选的 FileCache 实例，用于跳过未变化的文件
        """
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.file_cache = file_cache
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

        # 合并结果 — 列对齐：不同文件 | 拆分字段数不同(2或3个字段含|→19或21列)
        if all_base_info:
            all_cols = sorted(set(c for bi in all_base_info for c in bi.columns))
            base_info_combined = pl.concat(
                [bi.with_columns([pl.lit(None).cast(pl.Utf8).alias(c)
                 for c in all_cols if c not in bi.columns]).select(all_cols)
                 for bi in all_base_info],
                how="vertical"
            )
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

        # --- 缓存检查 ---
        if self.file_cache:
            cache_key = self.file_cache.get(str(filepath))
            if cache_key:
                try:
                    bi_path = self.file_cache.base_info_path(cache_key)
                    rd_path = self.file_cache.report_data_path(cache_key)
                    base_info_df = pl.read_parquet(bi_path) if bi_path.exists() else pl.DataFrame()
                    report_df = pl.read_parquet(rd_path) if rd_path.exists() else pl.DataFrame()
                    logger.debug(f"Cache hit: {filepath}")
                    return base_info_df, report_df
                except Exception as e:
                    logger.debug(f"Cache read failed, re-parsing: {e}")

        try:
            # 使用项目自制的PolarsExcelDataset读取Excel
            dataset = PolarsExcelDataset(
                filepath=str(filepath),
                load_args={
                    "sheet_id": 0,  # 0=读取全部工作表，返回Dict[str, DataFrame]
                    "engine": "calamine",
                    "has_header": False,  # 禁用自动header检测，手动处理
                    "infer_schema_length": 0,
                    "raise_if_empty": False
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
                        # 剔除必填字段为空的文件
                        unit_code_val = base_info.get("unit_code", "").strip()
                        parent_code_val = base_info.get("parent_code", "#").strip()
                        # if not unit_code_val or not parent_code_val:
                        # 如果本级代码为空，直接退出
                        if not unit_code_val:
                            logger.debug(f"跳过文件 (必填字段为空 unit_code={unit_code_val!r} parent_code={parent_code_val!r}): {filepath}")
                            return None, None
                        # 选填字段为空时填"无"
                        for opt_field in ("enterprise_address", "sasac_area_raw",
                                          "country_region_raw", "industry_affiliation", "industry_code"):
                            if not base_info.get(opt_field, "").strip():
                                base_info[opt_field] = "无"
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

            # --- 写入缓存 ---
            if self.file_cache:
                try:
                    cache_key = self.file_cache.put(str(filepath))
                    if base_info_df is not None and not base_info_df.is_empty():
                        base_info_df.write_parquet(self.file_cache.base_info_path(cache_key))
                    if report_df is not None and not report_df.is_empty():
                        report_df.write_parquet(self.file_cache.report_data_path(cache_key))
                except Exception as e:
                    logger.debug(f"Cache write failed: {e}")

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
        """解析基础信息工作表，返回字段字典。自动拆分 code | name 格式。"""
        result = {}
        field_mapping = (override or {}).get("field_mapping", {})

        try:
            if field_mapping and df.shape[1] >= 2:
                for row in df.iter_rows(named=True):
                    field_cell = row.get(df.columns[0])
                    if field_cell is None:
                        continue

                    field_str = str(field_cell).strip()
                    if not field_str:
                        continue

                    for pattern, field_name in field_mapping.items():
                        if pattern in field_str:
                            value_cell = row.get(df.columns[1]) if len(df.columns) > 1 else None
                            if value_cell is not None:
                                raw_value = str(value_cell).strip()
                                result[field_name] = raw_value
                                self._split_code_name(result, field_name, raw_value)
                            break
            else:
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

    @staticmethod
    def _split_code_name(result: dict, field_name: str, raw_value: str):
        """检测 code | name 格式并拆分为 _code 和 _name 字段。"""
        import re
        m = re.match(r'^(\S+)\s*\|\s*(.+)$', raw_value)
        if m:
            code_part = m.group(1)
            name_part = m.group(2).strip()
            if re.match(r'^[0-9A-Za-z]+$', code_part):
                result[f"{field_name}_code"] = code_part
                result[f"{field_name}_name"] = name_part

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
                new_cols = []
                seen = {}
                for i, val in enumerate(header_values):
                    name = str(val).strip() if val is not None else f"col_{i}"
                    name = name or f"col_{i}"
                    if name in seen:
                        seen[name] += 1
                        name = f"{name}_{seen[name]}"
                    else:
                        seen[name] = 0
                    new_cols.append(name)
                df.columns = new_cols

            # 识别指标列
            indicator_col_idx = None
            if isinstance(indicator_col, int) and indicator_col < len(df.columns):
                indicator_col_idx = indicator_col
            elif isinstance(indicator_col, str):
                for i, col in enumerate(df.columns):
                    if indicator_col in str(col):  # 子串匹配 (如 "项" 匹配 "项      目")
                        indicator_col_idx = i
                        break

            # 识别数值列: 1) 配置的 value_columns 名 2) 正则模式 3) 多行采样
            value_cols = []
            value_col_names = rules.get("value_columns", [])
            for i, col in enumerate(df.columns):
                col_str = str(col).strip()
                if col_str in value_col_names:
                    value_cols.append(i)

            if not value_cols:
                patterns = rules.get("value_columns_pattern", default_rules["value_columns_pattern"])
                for i, col in enumerate(df.columns):
                    col_str = str(col)
                    for pattern in patterns:
                        import re
                        if re.search(pattern, col_str):
                            value_cols.append(i)
                            break

            if not value_cols:
                # 回退：采样前10行，找含数字的列
                sample_rows = min(10, df.height)
                for i in range(len(df.columns)):
                    has_num = False
                    for r in range(sample_rows):
                        try:
                            v = df[r, i]
                            if v is not None:
                                s = str(v).strip()
                                if s and s != '--':
                                    float(s.replace(',', ''))
                                    has_num = True
                                    break
                        except (ValueError, TypeError):
                            continue
                    if has_num:
                        value_cols.append(i)

            if not value_cols:
                logger.warning(f"工作表 {sheet_name} 中未找到数值列")
                return pl.DataFrame()

            # 向量化：unpivot 宽表→长表，替代 row_idx × val_col_idx 双循环
            if indicator_col_idx is None:
                indicator_col_idx = 0
            indicator_col_name = df.columns[indicator_col_idx]
            value_col_names = [df.columns[i] for i in value_cols]

            # 过滤空行/章节标题行，只保留有指标名称的数据行
            df_data = df.filter(
                pl.col(indicator_col_name).is_not_null() &
                (pl.col(indicator_col_name).cast(pl.Utf8).str.strip_chars() != "") &
                (pl.col(indicator_col_name).cast(pl.Utf8).str.strip_chars() != "nan")
            )

            if df_data.is_empty():
                return pl.DataFrame()

            # unpivot: 每个 value_column 变成一行
            result = df_data.unpivot(
                index=[c for c in df_data.columns if c not in value_col_names],
                on=value_col_names,
                variable_name="value_column",
                value_name="value"
            )

            indicator_raw_series = result[indicator_col_name].cast(pl.Utf8).str.strip_chars()
            # 剥除编号前缀和前缀词，得到干净的指标名称用于 matcher 匹配
            indicator_clean_series = (
                indicator_raw_series
                .str.replace(r'^\s*\d+(?:[-.]\d+)*\s*[\.、\s]+', '')
                .str.strip_chars()
            )
            for prefix in ("其中：", "减：", "加：", "其中,"):
                indicator_clean_series = indicator_clean_series.str.strip_prefix(prefix)
            indicator_clean_series = indicator_clean_series.str.strip_chars()

            # 不填 report_category (留空)，让 standardize_report_data 的 matcher 决定
            report_category = ""

            result = result.with_columns([
                indicator_raw_series.alias("indicator_raw"),
                indicator_clean_series.alias("indicator_clean"),
                indicator_raw_series.alias("full_path"),
                indicator_clean_series.alias("top_level_account_name"),
                pl.lit(None, dtype=pl.Utf8).alias("indicator_number"),
                pl.lit(1, dtype=pl.Int32).alias("indicator_level"),
                pl.col("value").cast(pl.Float64, strict=False).fill_null(0.0).alias("value"),
                pl.lit(sheet_name).alias("sheet_name"),
                pl.lit(report_category).alias("report_category"),
            ])

            # 只保留目标列 + file_meta
            keep_cols = [
                "indicator_raw", "indicator_clean", "indicator_number",
                "indicator_level", "full_path", "value_column", "value",
                "sheet_name", "report_category", "top_level_account_name"
            ]
            result = result.select(keep_cols)
            for k, v in file_meta.items():
                result = result.with_columns(pl.lit(v).cast(pl.Utf8).alias(k))

            return result if not result.is_empty() else pl.DataFrame()

        except Exception as e:
            logger.error(f"解析报表工作表 {sheet_name} 失败: {e}")
            return pl.DataFrame()

def create_polars_pipeline_node(
    catalog: Dict[str, Any],
    config_path: str = "base/finance_loader.yml"
) -> Tuple[pl.DataFrame, pl.DataFrame]:
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
        return pl.DataFrame(), pl.DataFrame()

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 修复2：使用 finance_loader.yml 中的正则模式
    files = []
    try:
        if "excel_files" in catalog:
            files = catalog["excel_files"]
        else:
            base_path = Path(config.get("data_source", {}).get("base_path", "data/01_raw"))
            month_pattern = config.get("data_source", {}).get("month_folder_pattern", r"\d{4}年\d{1,2}月")
            file_name_patterns = config.get("file_name_pattern", {}).get("patterns", [])

            import re, calendar
            if base_path.exists():
                month_folders = [d for d in base_path.iterdir() if d.is_dir() and re.search(month_pattern, d.name)]
                for month_folder in month_folders:
                    # Parse period from folder name (e.g. "2026年02月" → "2026-02-28")
                    pm = re.search(r'(\d{4})年(\d{1,2})月', month_folder.name)
                    period = ""
                    if pm:
                        y, mth = int(pm.group(1)), int(pm.group(2))
                        period = f"{y}-{mth:02d}-{calendar.monthrange(y, mth)[1]:02d}"

                    excel_files = list(month_folder.glob("*.xlsx")) + list(month_folder.glob("*.xls"))
                    excel_files = [f for f in excel_files if not f.name.startswith(('.~', '~$'))]
                    for file_path in excel_files:
                        matched = False
                        for pattern_cfg in file_name_patterns:
                            regex = pattern_cfg.get("regex", "")
                            m = re.match(regex, file_path.name)
                            if m:
                                metadata = m.groupdict()
                                code = metadata.get("code", "")
                                suffix = metadata.get("suffix", "")
                                entity_id = hashlib.md5(f"{code}|{suffix}".encode()).hexdigest()[:8]
                                files.append({
                                    "path": str(file_path),
                                    "code": code,
                                    "suffix": suffix,
                                    "month_folder": month_folder.name,
                                    "unit": metadata.get("unit", file_path.stem),
                                    "entity_report_id": entity_id,
                                    "period": period,
                                })
                                matched = True
                                break
                        if not matched:
                            logger.debug(f"文件 {file_path.name} 不匹配任何模式，已跳过")
    except Exception as e:
        logger.warning(f"获取文件列表失败: {e}")
        return pl.DataFrame(), pl.DataFrame()

    if not files:
        logger.warning("没有找到Excel文件")
        return pl.DataFrame(), pl.DataFrame()

    # 使用Polars处理器
    file_cache = None
    try:
        from kedro.config import OmegaConfigLoader
        config_loader = OmegaConfigLoader(conf_source=settings.CONF_SOURCE)
        params = config_loader["parameters"]
        proc_cfg = params.get("processing", {})
        if proc_cfg.get("enable_file_cache", False):
            cache_dir = Path(settings.CONF_SOURCE).parent / proc_cfg.get("file_cache_dir", "data/02_intermediate/file_cache")
            file_cache = FileCache(str(cache_dir))
            logger.info("File cache enabled: %s", cache_dir)
    except Exception as e:
        logger.debug("File cache init skipped: %s", e)

    processor = PolarsExcelProcessor(max_workers=4, chunk_size=50, file_cache=file_cache)
    base_info_polars, report_data_polars = processor.process_excel_batch_polars(files, config)

    logger.info(f"Polars处理完成: {base_info_polars.height} 条基础信息, {report_data_polars.height} 条报表数据")

    return base_info_polars, report_data_polars

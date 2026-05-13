"""司库数据摄入 Pipeline — 批量解析司库 Excel 文件。"""
import logging
import polars as pl
from pathlib import Path
from kedro.pipeline import Pipeline, node
from kedro.framework.project import settings
from kedro.config import OmegaConfigLoader

from ..treasury_parser import transform_treasury_data
from ..file_cache import FileCache


def _init_file_cache() -> FileCache | None:
    try:
        config_loader = OmegaConfigLoader(conf_source=settings.CONF_SOURCE)
        params = config_loader["parameters"]
        proc_cfg = params.get("processing", {})
        if proc_cfg.get("enable_file_cache", False):
            cache_dir = Path(settings.CONF_SOURCE).parent / proc_cfg.get("file_cache_dir", "data/02_intermediate/file_cache")
            return FileCache(str(cache_dir))
    except Exception:
        pass
    return None


def batch_parse_treasury_files(catalog, parameters: dict = None):
    """遍历 catalog 中所有 treasury_* 数据集，按 file_type 路由解析。

    Returns:
        parsed_treasury_account_info, parsed_treasury_account_balance
    """
    logger = logging.getLogger(__name__)
    file_cache = _init_file_cache()
    if file_cache:
        logger.info("File cache enabled: %s", file_cache.stats()["cache_dir"])

    account_info_frames = []
    account_balance_frames = []
    cache_hits = 0
    cache_misses = 0

    for name, ds in catalog._datasets.items():
        if not name.startswith("treasury_"):
            continue

        metadata = getattr(ds, "metadata", {}) or {}
        file_type = metadata.get("file_type", "")
        period = metadata.get("period", "")

        if file_type not in ("account_info", "account_balance"):
            logger.debug(f"Skipping unknown treasury file_type: {name} -> {file_type}")
            continue

        # resolve source file path from dataset config
        source_path = None
        try:
            source_path = ds._describe().get("filepath")
        except Exception:
            pass

        try:
            # --- 缓存检查 ---
            if file_cache and source_path:
                cache_key = file_cache.get(str(source_path))
                if cache_key:
                    cache_path = file_cache.treasury_path(cache_key)
                    if cache_path.exists():
                        df = pl.read_parquet(cache_path)
                        df = df.with_columns([
                            pl.lit(name).alias("source_file"),
                            pl.lit(period).alias("period"),
                        ])
                        if file_type == "account_info":
                            account_info_frames.append(df)
                        else:
                            account_balance_frames.append(df)
                        cache_hits += 1
                        logger.debug(f"Cache hit: {source_path}")
                        continue

            # 正常加载
            excel_data = ds.load()
            cache_misses += 1
            logger.info(f"Parsing {name} (file_type={file_type})")

            frames_for_file = []
            for sheet_name, df in excel_data.items():
                if not isinstance(df, pl.DataFrame):
                    df = pl.from_pandas(df)
                df = transform_treasury_data(df, file_type)
                df = df.with_columns([
                    pl.lit(name).alias("source_file"),
                    pl.lit(period).alias("period"),
                ])

                if file_type == "account_info":
                    account_info_frames.append(df)
                else:
                    account_balance_frames.append(df)
                frames_for_file.append(df)

            # --- 写入缓存 ---
            if file_cache and source_path and frames_for_file:
                try:
                    cache_key = file_cache.put(str(source_path))
                    combined = pl.concat(frames_for_file, how="vertical")
                    combined.write_parquet(file_cache.treasury_path(cache_key))
                except Exception as e:
                    logger.debug(f"Cache write failed for {source_path}: {e}")

        except Exception as e:
            logger.error(f"Failed to parse {name}: {e}")

    if file_cache:
        logger.info("Treasury cache: %d hits, %d misses", cache_hits, cache_misses)

    parsed_info = pl.concat(account_info_frames, how="vertical") if account_info_frames else pl.DataFrame()
    parsed_balance = pl.concat(account_balance_frames, how="vertical") if account_balance_frames else pl.DataFrame()

    logger.info(f"Parsed {len(parsed_info)} account_info rows, {len(parsed_balance)} account_balance rows")
    return parsed_info, parsed_balance


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline([
        node(
            func=batch_parse_treasury_files,
            inputs=["catalog", "parameters"],
            outputs=["parsed_treasury_account_info", "parsed_treasury_account_balance"],
            name="batch_parse_treasury_files",
        ),
    ])

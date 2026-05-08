"""司库数据摄入 Pipeline — 批量解析司库 Excel 文件。"""
import logging
import polars as pl
from kedro.pipeline import Pipeline, node

from ..treasury_parser import transform_treasury_data


def batch_parse_treasury_files(catalog, parameters: dict = None):
    """遍历 catalog 中所有 treasury_* 数据集，按 file_type 路由解析。

    Returns:
        parsed_treasury_account_info, parsed_treasury_account_balance
    """
    logger = logging.getLogger(__name__)
    account_info_frames = []
    account_balance_frames = []

    for name, ds in catalog._datasets.items():
        if not name.startswith("treasury_"):
            continue

        metadata = getattr(ds, "metadata", {}) or {}
        file_type = metadata.get("file_type", "")
        period = metadata.get("period", "")

        if file_type not in ("account_info", "account_balance"):
            logger.debug(f"Skipping unknown treasury file_type: {name} -> {file_type}")
            continue

        try:
            excel_data = ds.load()
            logger.info(f"Parsing {name} (file_type={file_type})")

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

        except Exception as e:
            logger.error(f"Failed to parse {name}: {e}")

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

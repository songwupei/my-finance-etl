"""Polars Parquet Kedro Dataset."""

from pathlib import Path
from typing import Any

import polars as pl
from kedro.io import AbstractDataset


class PolarsParquetDataset(AbstractDataset):
    """Kedro dataset for reading/writing Polars DataFrames as Parquet."""

    def __init__(self, filepath: str):
        self._filepath = Path(filepath)

    def _load(self) -> pl.DataFrame:
        return pl.read_parquet(str(self._filepath))

    def _save(self, data) -> None:
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, pl.DataFrame):
            data.write_parquet(str(self._filepath))
        else:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                data.to_parquet(str(self._filepath))
            else:
                raise TypeError(f"Expected pl.DataFrame or pd.DataFrame, got {type(data)}")

    def _describe(self) -> dict[str, Any]:
        return {"filepath": str(self._filepath), "exists": self._filepath.exists()}

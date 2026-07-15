"""
自定义Polars Excel数据集，支持使用polars读取Excel文件。
支持读取单个工作表或多个工作表。
"""

import polars as pl
from pathlib import Path
from typing import Any, Dict, Optional, Union
from kedro.io import AbstractDataset
from kedro.io.core import DatasetError


class PolarsExcelDataset(AbstractDataset[Union[pl.DataFrame, Dict[str, pl.DataFrame]], Union[pl.DataFrame, Dict[str, pl.DataFrame]]]):
    """``PolarsExcelDataset`` 使用polars库加载和保存Excel文件。

    根据`sheet_name`参数，可以返回单个DataFrame或工作表名称到DataFrame的字典。

    示例:
    ::

        >>> # 读取单个工作表
        >>> dataset = PolarsExcelDataset(
        >>>     filepath="/path/to/file.xlsx",
        >>>     load_args={"has_header": True, "sheet_name": "Sheet1"}
        >>> )
        >>> dataframe = dataset.load()  # 返回单个DataFrame
        >>>
        >>> # 读取所有工作表
        >>> dataset = PolarsExcelDataset(
        >>>     filepath="/path/to/file.xlsx",
        >>>     load_args={"has_header": True, "sheet_name": None}
        >>> )
        >>> sheets_dict = dataset.load()  # 返回Dict[str, DataFrame]

    """

    def __init__(
        self,
        filepath: str,
        load_args: Optional[Dict[str, Any]] = None,
        save_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """创建PolarsExcelDataset的新实例。

        Args:
            filepath: Excel文件的路径。
            load_args: 传递给polars.read_excel()的选项。
                支持的参数包括：sheet_id, sheet_name, engine, has_header,
                xlsx2csv_options, read_options, raise_if_empty,
                infer_schema_length, schema_overrides等。
                参见 https://pola-rs.github.io/polars/py-polars/html/reference/io.html
            save_args: 传递给polars.DataFrame.write_excel()的选项。
                参见 https://pola-rs.github.io/polars/py-polars/html/reference/dataframe/io.html

        Raises:
            DatasetError: 当提供无效参数时。
        """
        self._filepath = Path(filepath)
        self._load_args = load_args if load_args is not None else {}
        self._save_args = save_args if save_args is not None else {}

        # 设置默认引擎为calamine（fastexcel），如果未指定
        if "engine" not in self._load_args:
            self._load_args["engine"] = "calamine"

    def _describe(self) -> Dict[str, Any]:
        return {
            "filepath": str(self._filepath),
            "load_args": self._load_args,
            "save_args": self._save_args,
        }

    def _load(self) -> Union[pl.DataFrame, Dict[str, pl.DataFrame]]:
        """从Excel文件加载数据。

        Returns:
            如果sheet_id=0或sheet_name是列表/None，返回工作表名称到DataFrame的字典；
            否则返回单个DataFrame。

        Raises:
            DatasetError: 当加载失败时。
        """
        # 引擎降级列表：优先calamine(fastexcel)，降级到openpyxl
        engines_to_try = []
        specified_engine = self._load_args.get("engine")
        if specified_engine:
            engines_to_try.append(specified_engine)
            # 如果指定了calamine，添加openpyxl作为降级
            if specified_engine == "calamine":
                engines_to_try.append("openpyxl")
        else:
            engines_to_try = ["calamine", "openpyxl"]

        # 合并报错信息
        last_exception = None
        tried_engines = []

        for engine in engines_to_try:
            try:
                load_args = {**self._load_args, "engine": engine}
                # openpyxl 引擎需要 raise_if_empty=False 来处理空工作表
                if engine == "openpyxl" and "raise_if_empty" not in load_args:
                    load_args["raise_if_empty"] = False
                result = pl.read_excel(self._filepath, **load_args)
                return result
            except Exception as exc:
                engine_name = engine
                last_exception = exc
                tried_engines.append(engine_name)
                continue

        # 所有引擎都失败，构造详细错误信息
        error_detail = (
            f"从 {self._filepath} 加载Excel文件失败。"
            f" 尝试的引擎: {tried_engines}"
        )
        if last_exception:
            error_detail += f" 最后错误: [{type(last_exception).__name__}] {last_exception}"
        raise DatasetError(error_detail) from last_exception

    def _save(self, data: Union[pl.DataFrame, Dict[str, pl.DataFrame]]) -> None:
        """将数据保存到Excel文件。

        Args:
            data: 要保存的Polars DataFrame或工作表名称到DataFrame的字典。

        Raises:
            DatasetError: 当保存失败时，或当数据格式不支持时。
        """
        try:
            # 确保目录存在
            self._filepath.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(data, pl.DataFrame):
                # 单个DataFrame
                data.write_excel(self._filepath, **self._save_args)
            elif isinstance(data, dict):
                # 多个工作表
                # 注意：polars的write_excel可以通过worksheet_name参数支持多个工作表
                # 但需要检查是否所有值都是DataFrame
                for sheet_name, df in data.items():
                    if not isinstance(df, pl.DataFrame):
                        raise DatasetError(
                            f"字典值必须是DataFrame，但 '{sheet_name}' 的类型是 {type(df)}"
                        )
                # 目前polars的write_excel不支持直接写入多个工作表到单个文件
                # 我们可以使用第一个DataFrame写入，然后添加其他工作表
                # 这是一个简化实现：只保存第一个工作表
                # 更完整的实现需要使用其他库如openpyxl或xlsxwriter
                first_sheet_name = next(iter(data))
                first_df = data[first_sheet_name]
                first_df.write_excel(self._filepath, **self._save_args)
                # 记录警告或抛出不支持的错误
                if len(data) > 1:
                    raise DatasetError(
                        "当前版本不支持保存多个工作表。请提供一个DataFrame。"
                    )
            else:
                raise DatasetError(
                    f"不支持的数据类型：{type(data)}。必须是DataFrame或Dict[str, DataFrame]。"
                )
        except Exception as exc:
            raise DatasetError(
                f"保存到 {self._filepath} 失败。"
            ) from exc

    def _exists(self) -> bool:
        return self._filepath.exists()
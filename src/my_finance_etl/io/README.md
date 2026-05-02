# 自定义Polars Excel数据集

这个目录包含一个自定义Kedro数据集，用于使用Polars库读取和写入Excel文件。

## PolarsExcelDataset

`PolarsExcelDataset` 是一个Kedro数据集实现，封装了polars的`read_excel`和`write_excel`功能。

### 特性

- 支持使用fastexcel (calamine) 引擎快速读取Excel文件
- 支持读取单个或多个工作表
- 灵活的加载参数配置
- 类型安全：根据参数返回`DataFrame`或`Dict[str, DataFrame]`

### 安装依赖

确保以下依赖已安装：

```bash
pip install polars fastexcel
```

项目已通过`requirements.txt`包含这些依赖。

### 使用方法

#### 1. 在catalog.yml中配置

```yaml
# 读取所有工作表（返回字典）
my_excel_dataset:
  type: modelmanual_pl.io.PolarsExcelDataset
  filepath: data/01_raw/my_file.xlsx
  load_args:
    engine: calamine
    has_header: true
    sheet_id: 0  # 或使用 sheet_name: null

# 读取单个工作表（返回DataFrame）
single_sheet_dataset:
  type: modelmanual_pl.io.PolarsExcelDataset
  filepath: data/01_raw/my_file.xlsx
  load_args:
    engine: calamine
    has_header: true
    sheet_name: "Sheet1"  # 或使用 sheet_id: 1
```

#### 2. 在节点函数中使用

```python
import polars as pl
from typing import Dict

def process_excel_data(sheets_dict: Dict[str, pl.DataFrame]) -> pl.DataFrame:
    """处理从PolarsExcelDataset加载的Excel数据"""
    # 排除封面工作表
    sheets_to_process = {
        name: df for name, df in sheets_dict.items()
        if "封面" not in name and "封皮" not in name
    }

    # 处理逻辑...
    # 返回合并的DataFrame
    return combined_df
```

#### 3. 在管道中连接

在`pipeline.py`中：

```python
from .nodes import process_excel_data

Node(
    func=process_excel_data,
    inputs="my_excel_dataset",  # catalog中的数据集名称
    outputs="processed_data",
    name="process_excel_node"
)
```

### 参数说明

#### 加载参数 (`load_args`)

| 参数 | 类型 | 说明 |
|------|------|------|
| `sheet_id` | int | 读取所有工作表时使用0，读取特定工作表时使用索引（1-based） |
| `sheet_name` | str/int/list/None | 工作表名称、索引、列表或None（读取所有） |
| `has_header` | bool | 是否将第一行作为标题（默认：true） |
| `engine` | str | Excel引擎（默认："calamine"） |
| `xlsx2csv_options` | dict | 传递给xlsx2csv的选项 |
| `read_options` | dict | 传递给CSV读取器的选项 |
| `raise_if_empty` | bool | 空文件时是否引发异常 |
| `infer_schema_length` | int | 推断模式的行数 |
| `schema_overrides` | dict | 列模式覆盖 |

#### 保存参数 (`save_args`)

| 参数 | 类型 | 说明 |
|------|------|------|
| `worksheet_name` | str | 工作表名称（默认："Sheet1"） |
| `position` | str | 单元格位置（默认："A1"） |
| `table_style` | str | 表格样式 |
| `table_name` | str | 表格名称 |
| `column_widths` | dict | 列宽度 |
| `row_heights` | dict | 行高度 |
| `...` | | 其他polars write_excel参数 |

### 示例：处理项目中的Excel文件

项目已经包含两个示例数据集配置：

```yaml
# conf/base/catalog.yml
attachment1_excel:
  type: modelmanual_pl.io.PolarsExcelDataset
  filepath: data/01_raw/附件1：穿透式监管模型系统数据需求表.xlsx
  load_args:
    engine: calamine
    has_header: false
    sheet_id: 0

attachment2_excel:
  type: modelmanual_pl.io.PolarsExcelDataset
  filepath: data/01_raw/附件2：规则明细表.xlsx
  load_args:
    engine: calamine
    has_header: true
    sheet_id: 0
```

对应的节点函数已在`nodes.py`中实现：

- `process_attachment1_excel()` - 处理附件1数据
- `process_attachment2_excel()` - 处理附件2数据

### 注意事项

1. **多工作表保存**：当前版本不支持保存多个工作表到单个Excel文件。保存字典数据时只保存第一个工作表。

2. **性能**：使用`engine="calamine"`（fastexcel）可以获得最佳性能，特别是对于大型Excel文件。

3. **数据类型推断**：Excel数据类型可能不如Parquet或CSV精确，建议在节点函数中进行适当的数据清洗和类型转换。

### 故障排除

1. **导入错误**：确保`src`目录在Python路径中，或正确安装项目包。

2. **文件未找到**：检查`filepath`是否为相对于项目根目录的正确路径。

3. **工作表读取问题**：尝试使用`sheet_id=0`而不是`sheet_name=None`来读取所有工作表。

4. **内存问题**：对于非常大的Excel文件，考虑使用`pl.scan_excel()`进行惰性读取（需要自定义实现）。

### 扩展建议

如需更高级的功能，可以考虑：

1. **分块读取**：实现分块读取大型Excel文件
2. **数据类型自动检测**：增强Excel到Polars数据类型的映射
3. **多工作表保存**：实现完整的多个工作表保存支持
4. **Excel模板支持**：支持基于模板的Excel写入
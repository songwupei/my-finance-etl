# 数据标准驱动升级 + Polars 全量迁移 — 实施计划

## Context

将 skdata-etl 项目升级为数据标准驱动架构，同时完成 pandas → polars 全量迁移。`standards/` 目录下已有司库数据标准规范 2.0（YAML + DDL + xlsx），覆盖 19 个业务模块，范围远超当前项目，作为外部参考标准。本次需新建 `finance_treasury_standard.yaml`，作为本 ETL 数据中台的完整 schema 定义。

## 一、现状分析

### 1.1 数据标准现状

| 文件 | 覆盖范围 | 与项目关系 |
|------|---------|-----------|
| `standards/treasury_data.yaml` | 19 个业务模块（银行账户、资金结算、贷款...） | 外部参考标准（集团司库报送规范），仅 bank_account 模块与项目相关 |
| `standards/treasury_ddl.sql` | 从 YAML 自动生成的 DuckDB DDL | 同上 |
| `standards/数据报送标准规范2.0.xlsx` | 原始规范文档 | 业务参考 |
| `conf/base/standard_accounts.json` | 124 个财务科目（4 类报表） | 项目核心知识库，格式为非标 JSON |
| ❌ **待建** | `standards/finance_treasury_standard.yaml` | **本项目 ETL 数据中台的完整 schema 定义** |

### 1.2 Pandas 使用全景

所有 pipeline 节点当前都使用 pandas：

| 文件 | pandas 调用数 | 关键模式 | 迁移难度 |
|------|-------------|---------|---------|
| `data_processing.py` | 16 | `iterrows` x2, `.unique`, `pd.notna` | **中** |
| `data_warehouse.py` | 10 | `iterrows`, `df[filter]`, `.iloc` | 低 |
| `treasury_processing.py` | 21 | `.apply()` x3, `.merge()` x2 | **高** |
| `tree_builder.py` | 9 | `iterrows` x2, `.iloc` | 低 |
| `parser.py` | 14 | `iterrows` x2, `iloc` | 中（已有 polars 版） |
| `treasury_parser.py` | 4 | `.rename`, `.dropna` | 低 |
| `treasury_ingestion.py` | 3 | `pd.concat`, `pd.DataFrame` | 低 |
| `duckdb_data_warehouse.py` | 6 | `.empty`, `.fetch_df()` | 低 |
| `matcher.py` | 0 | 纯 Python dict | **无需迁移** |
| `geocoder.py` | 0 | 已是 polars | **已完成** |
| `polars_optimizer.py` | 1 (bridge) | 已是 polars，仅 `to_pandas()` 桥接 | **已完成** |
| `catalog.yml` | 14 entries | 全部 `pandas.ParquetDataset` | 低 |

### 1.3 关键 API 映射速查

| Pandas | Polars |
|---|---|
| `df.empty` | `df.is_empty()` |
| `df.iterrows()` | `df.iter_rows(named=True)` |
| `df[df["col"]==v]` | `df.filter(pl.col("col")==v)` |
| `df["col"].unique()` | `df["col"].unique().to_list()` |
| `df["new"] = val` | `df = df.with_columns(pl.lit(val).alias("new"))` |
| `df.merge(...)` | `df.join(...)` |
| `df.copy()` | `df.clone()` |
| `df.dropna(...)` | `df.drop_nulls(...)` |
| `pd.notna(x)` | `x is not None` |
| `df.to_parquet(p)` | `df.write_parquet(p)` |
| `pd.read_parquet(p)` | `pl.read_parquet(p)` |

## 二、实施阶段

### 阶段 1: 新建集团财务数据标准 `standards/finance_treasury_standard.yaml`

**目标**：定义本 ETL 数据中台的完整 schema，覆盖财务快报 + 司库账户全部维度表和事实表。

**文件**：`standards/finance_treasury_standard.yaml`

**结构设计**（参考 treasury_data.yaml 格式）：

```yaml
meta:
  standard_name: 司库数据标准
  version: "1.0"
  rendered_date: "2026-05-08"
  description: 集团标准财务科目知识库，涵盖资产负债表/利润表/现金流量表/所有者权益变动表
  source: conf/base/standard_accounts.json

dimensions:
  - table_name: dim_standard_account
    table_cn: 标准科目
    description: 集团统一财务科目树，4类报表共124个科目
    fields:
      - name: account_code
        cn_name: 科目编码
        dtype: VARCHAR
        length: 20
        nullable: false
      - name: account_name
        cn_name: 科目名称
        dtype: VARCHAR
        length: 100
        nullable: false
      - name: account_code_dash
        cn_name: 科目编码(横杠)
        dtype: VARCHAR
        length: 20
      - name: parent_code
        cn_name: 父级编码
        dtype: VARCHAR
        length: 20
      - name: level
        cn_name: 层级
        dtype: INTEGER
      - name: is_summary
        cn_name: 是否汇总科目
        dtype: BOOLEAN
      - name: is_leaf_for_fact
        cn_name: 是否事实表叶子节点
        dtype: BOOLEAN
      - name: standard_path
        cn_name: 标准路径
        dtype: VARCHAR
        length: 500
      - name: report_category
        cn_name: 报表类别
        dtype: VARCHAR
        length: 50
      - name: match_priority
        cn_name: 匹配优先级
        dtype: INTEGER
      - name: sort_order
        cn_name: 排序序号
        dtype: INTEGER

  - table_name: dim_report_category
    table_cn: 报表类别
    fields:
      - name: category_id
        cn_name: 类别ID
        dtype: VARCHAR
        length: 10
      - name: category_name
        cn_name: 类别名称
        dtype: VARCHAR
        length: 50

  - table_name: dim_period
    table_cn: 会计期间
    fields:
      - name: period_id
        cn_name: 期间ID
        dtype: VARCHAR
        length: 10
      - name: period_name
        cn_name: 期间名称
        dtype: VARCHAR
        length: 20
      - name: year
        cn_name: 年份
        dtype: INTEGER
      - name: month
        cn_name: 月份
        dtype: INTEGER

  - table_name: dim_unit_report
    table_cn: 报表单位
    fields:
      - name: entity_report_id
        cn_name: 单位上报ID
        dtype: VARCHAR
        length: 50
      - name: unit_name
        cn_name: 单位名称
        dtype: VARCHAR
        length: 200
      - name: code
        cn_name: 统一社会信用代码
        dtype: VARCHAR
        length: 18
      - name: suffix
        cn_name: 后缀
        dtype: VARCHAR
        length: 10
      - name: province
        cn_name: 省份
        dtype: VARCHAR
        length: 50
      - name: city
        cn_name: 城市
        dtype: VARCHAR
        length: 50
      - name: enterprise_address
        cn_name: 企业地址
        dtype: VARCHAR
        length: 500

  - table_name: dim_organization_tree
    table_cn: 组织架构树
    fields:
      - name: node_id
        cn_name: 节点ID
        dtype: VARCHAR
        length: 100
      - name: parent_id
        cn_name: 父节点ID
        dtype: VARCHAR
        length: 100
      - name: node_name
        cn_name: 节点名称
        dtype: VARCHAR
        length: 200
      - name: entity_report_id
        cn_name: 单位上报ID
        dtype: VARCHAR
        length: 50

facts:
  - table_name: fact_finance_data
    table_cn: 财务事实数据
    fields:
      - name: id
        cn_name: 唯一ID
        dtype: VARCHAR
        length: 36
      - name: entity_report_id
        cn_name: 单位上报ID
        dtype: VARCHAR
        length: 50
      - name: period_id
        cn_name: 期间ID
        dtype: VARCHAR
        length: 10
      - name: account_code
        cn_name: 科目编码
        dtype: VARCHAR
        length: 20
      - name: category_id
        cn_name: 报表类别ID
        dtype: VARCHAR
        length: 10
      - name: value
        cn_name: 金额
        dtype: DECIMAL
        precision: 18
        scale: 2
      - name: value_column
        cn_name: 数值列类型
        dtype: VARCHAR
        length: 20
      - name: is_standardized
        cn_name: 是否已标准化
        dtype: BOOLEAN
      - name: source_file
        cn_name: 来源文件
        dtype: VARCHAR
        length: 200
      - name: raw_path
        cn_name: 原始路径
        dtype: VARCHAR
        length: 500
      - name: top_level_account_name
        cn_name: 顶层科目名称
        dtype: VARCHAR
        length: 100
      - name: etl_created_at
        cn_name: ETL创建时间
        dtype: TIMESTAMP
```

**同时创建** `standards/finance_ddl.sql` 从 YAML 自动生成。

### 阶段 2: Schema Registry 模块

**新建** `src/my_finance_etl/schema_registry.py`：

```python
# 核心功能
class SchemaRegistry:
    def __init__(self, yaml_path: str): ...
    def get_table_schema(self, table_name: str) -> TableSchema: ...
    def get_field_map(self, table_name: str) -> dict[str, FieldDef]: ...
    def generate_duckdb_ddl(self, table_name: str) -> str: ...
    def cn_to_en(self, table_name: str, cn_name: str) -> str: ...
    def en_to_cn(self, table_name: str, en_name: str) -> str: ...
```

**字段定义数据类**：
```python
@dataclass
class FieldDef:
    name: str           # 英文名
    cn_name: str        # 中文名
    dtype: str          # VARCHAR / DECIMAL / INTEGER / DATE / TIMESTAMP / BOOLEAN
    length: int | None
    precision: int | None
    scale: int | None
    nullable: bool
    checks: list[dict]
```

### 阶段 3: Polars 全量迁移

按数据流从上游到下游逐文件迁移：

| 顺序 | 文件 | 关键改动 | 风险 |
|------|------|---------|------|
| 1 | `catalog.yml` | 14 个 `pandas.ParquetDataset` → `PolarsParquetDataset`（需新建） | 低 |
| 2 | `polars_optimizer.py` | 去掉末尾 `to_pandas()` 桥接 | 低 |
| 3 | `data_processing.py` | `iterrows()` → `iter_rows(named=True)`，`df["col"]=` → `with_columns` | 中 |
| 4 | `matcher.py` | 无需改动（纯 Python dict 接口不变） | 无 |
| 5 | `tree_builder.py` | `iterrows()` → `iter_rows(named=True)` | 低 |
| 6 | `data_warehouse.py` | `iterrows()` → `iter_rows(named=True)`，lookup dict 预计算 | 低 |
| 7 | `duckdb_data_warehouse.py` | `fetch_df()` → `.pl()`，polars DF 需 `conn.register()` | 中 |
| 8 | `treasury_parser.py` | `.rename()` → `.select(pl.col().alias())` | 低 |
| 9 | `treasury_ingestion.py` | `pd.concat` → `pl.concat` | 低 |
| 10 | `treasury_processing.py` | `.apply()` → 向量化 + `map_elements()` | **高** |
| 11 | `treasury_warehouse.py` | 类型标注改为 `pl.DataFrame` | 低 |
| 12 | `geocoder.py` | 去掉 `.to_pandas()` 桥接（如果存在） | 低 |

**DuckDB 集成关键改动**（`duckdb_data_warehouse.py`）：

```python
# 旧：pandas DataFrame 自动被 DuckDB 识别
conn.execute("CREATE TABLE ... AS SELECT * FROM df_pandas")

# 新：polars DataFrame 需要 register
conn.register("df_name", df_polars)
conn.execute("CREATE TABLE ... AS SELECT * FROM df_name")

# 或使用 DuckDB 的 polars 集成
result = conn.execute(sql).pl()  # 返回 polars DataFrame
```

**新建** `src/my_finance_etl/io/polars_parquet_dataset.py`：
```python
class PolarsParquetDataset(AbstractDataset):
    def _load(self) -> pl.DataFrame:
        return pl.read_parquet(self._filepath)
    def _save(self, data: pl.DataFrame) -> None:
        data.write_parquet(self._filepath)
```

### 阶段 4: ETL 节点接入 Schema Registry

在 `data_processing.py`、`data_warehouse.py` 等节点中：

```python
def build_dimension_tables(..., parameters: dict) -> dict:
    use_new = parameters.get("data_standard", {}).get("use_new_standard", False)
    if use_new:
        registry = SchemaRegistry(parameters["data_standard"]["schema_registry_path"])
        return build_dimensions_from_registry(...)
    else:
        return build_dimensions_legacy(...)
```

### 阶段 5: 灰度切换与清理

同原方案，通过 `parameters.yml` 中 `data_standard.use_new_standard` 开关控制。

## 三、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `standards/finance_treasury_standard.yaml` | **新建** | 司库数据标准（YAML schema） |
| `standards/finance_ddl.sql` | **新建** | 从 YAML 自动生成的 DuckDB DDL |
| `src/my_finance_etl/schema_registry.py` | **新建** | Schema Registry 核心模块 |
| `src/my_finance_etl/io/polars_parquet_dataset.py` | **新建** | Polars Parquet Kedro Dataset |
| `conf/base/schema_registry.yml` | **新建** | 运行时 schema 配置（从 YAML 生成） |
| `conf/base/parameters.yml` | 修改 | 添加 `data_standard` 配置段 |
| `conf/base/catalog.yml` | 修改 | 14 个 dataset 从 `pandas.ParquetDataset` → `PolarsParquetDataset` |
| `src/my_finance_etl/polars_optimizer.py` | 修改 | 去掉 `to_pandas()` 桥接 |
| `src/my_finance_etl/pipelines/data_processing.py` | 修改 | pandas → polars + registry 接入 |
| `src/my_finance_etl/pipelines/data_warehouse.py` | 修改 | pandas → polars + lookup 优化 |
| `src/my_finance_etl/duckdb_data_warehouse.py` | 修改 | `.fetch_df()` → `.pl()`，DF register |
| `src/my_finance_etl/pipelines/treasury_processing.py` | 修改 | pandas → polars + .apply 向量化 |
| `src/my_finance_etl/pipelines/treasury_ingestion.py` | 修改 | pandas → polars |
| `src/my_finance_etl/pipelines/treasury_warehouse.py` | 修改 | 类型标注 |
| `src/my_finance_etl/treasury_parser.py` | 修改 | pandas → polars |
| `src/my_finance_etl/tree_builder.py` | 修改 | pandas → polars |
| `src/my_finance_etl/geocoder.py` | 修改 | 去掉 pandas 桥接 |
| `flask_app.py` | 无需改动 | 读 DuckDB，不受 ETL 内部 DataFrame 框架影响 |

## 四、关键决策

1. **司库标准仅作参考** — `standards/treasury_data.yaml` 的 19 模块定义不直接用于当前项目，但其 YAML 格式和校验规则体系作为 schema registry 的设计模板。

2. **新建 finance_treasury_standard.yaml** — 将 `standard_accounts.json`（124 科目）扩展为完整的维度表+事实表 schema 定义，补齐集团财务数据标准空白。

3. **Polars 优先，DuckDB 桥接** — ETL 计算全用 polars，仅在写入 DuckDB 时通过 `conn.register()` 桥接。

4. **matcher.py 不动** — 它是纯 Python dict 操作，与 DataFrame 框架无关，性能瓶颈在匹配逻辑（O(n²) 索引查找），不在 DataFrame 迭代。

## 五、验证方案

1. **单元测试**：schema_registry.py 解析/DDL生成/校验 全覆盖
2. **集成测试**：`kedro run` 全量运行，新旧 DataFrame 结果 `equals()` 比对
3. **API 测试**：Flask 全部端点 curl 比对响应 JSON
4. **性能基准**：记录 `kedro run` 执行时间，polars 迁移后应有提升
5. **DuckDB 一致性**：`SELECT ... EXCEPT` 新旧表数据差异

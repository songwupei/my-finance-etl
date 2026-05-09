# 集团财务数据标准化处理与可视化平台

基于 Kedro 数据管道框架的财务数据 ETL 与可视化平台，支持动态 Excel 文件扫描、指标标准化处理、组织树构建、资金账户解析、地理编码与可视化展示。

**版本**: 1.2

## 项目结构

```
skdata-etl/
├── conf/                          # 配置文件
│   ├── base/                      # 基础配置
│   │   ├── catalog.yml            # Kedro 数据目录
│   │   ├── parameters.yml         # 全局参数 (数据库路径等)
│   │   ├── hooks.yml              # 钩子配置
│   │   ├── finance_loader.yml     # Excel 解析规则
│   │   ├── treasury_loader.yml    # 资金账户解析规则
│   │   ├── indicator_mapping.yml  # 指标标准化配置
│   │   ├── standard_accounts.json # 标准科目库 (v2.0, 2018年版企业财务报表格式)
│   │   ├── standard_accountsv1.0.json
│   │   └── finance_mapping_standard.yaml # 财务指标映射标准配置
│   └── local/
│       └── credentials.yml        # 数据库凭证
├── src/my_finance_etl/            # 源码
│   ├── hooks/
│   │   └── hooks.py               # Kedro 钩子 (动态 Excel 加载)
│   ├── pipelines/
│   │   ├── data_ingestion.py      # 财务数据摄入 (Pandas)
│   │   ├── data_ingestion_polars.py # 财务数据摄入 (Polars 优化)
│   │   ├── data_processing.py     # 指标标准化处理
│   │   ├── data_warehouse.py      # 财务数据仓库构建
│   │   ├── treasury_ingestion.py  # 资金数据摄入
│   │   ├── treasury_processing.py # 资金数据处理
│   │   └── treasury_warehouse.py  # 资金数据仓库构建
│   ├── nodes/                     # Kedro 节点
│   ├── io/                        # 自定义 I/O
│   ├── utils/                     # 工具函数
│   ├── parser.py                  # Excel 财务快报解析器
│   ├── treasury_parser.py         # 资金账户 Excel 解析器
│   ├── matcher.py                 # 标准科目匹配器
│   ├── tree_builder.py            # 组织树构建器
│   ├── duckdb_data_warehouse.py   # DuckDB 星型模型构建
│   ├── polars_optimizer.py        # Polars 并行优化
│   ├── geocoder.py                # 高德地图地理编码
│   ├── pipeline_registry.py       # 管道注册
│   └── settings.py                # 项目设置
├── scripts/                      # (geocode_units.py 已删除，统一用 geocoder.py)
├── doc/
│   ├── finance_warehouse_schema.md # 数据仓库 Schema 文档
│   └── 指标对比键匹配规则.md       # 指标匹配算法说明
├── data/
│   ├── 01_raw/                    # 原始 Excel 文件
│   ├── 02_intermediate/           # 中间数据
│   └── warehouse/                 # DuckDB 数据仓库
├── templates/
│   └── index.html                 # Flask 前端界面
├── generated_reports/             # 生成的报告文件
├── flask_app.py                   # Flask 可视化服务 (含 Vizro 仪表板)
├── pyproject.toml                 # 项目配置
└── README.md                      # 本文档
```

## 功能特性

### ETL 管道

1. **动态 Excel 加载**: 自动扫描月度文件夹，根据正则表达式提取元数据
2. **智能解析**: 自动识别基本信息工作表和报表工作表，支持章节命名空间隔离
3. **指标标准化**: 基于标准科目库（v2.0，2018年版企业财务报表格式）的层级路径匹配，支持上下文消歧
4. **组织树构建**: 自动构建集团多层级组织架构树 (2830 个节点)，支持本部口径 (suffix=0) 优先
5. **资金账户解析**: 解析银行账户信息，构建资金账户维度表 (27085 个账户)，优先匹配本部口径单位
6. **星型数据模型**: 生成维度表和事实表，存储在 DuckDB (`finance_warehouse.duckdb`)
7. **Polars 加速**: 针对 1500+ Excel 文件的并行处理优化，parent_code 选填化处理
8. **自动地理编码**: 在维度表构建完成后，通过 Kedro 钩子自动执行高德地理编码

### 可视化服务

8. **组织树浏览**: Flask + jsTree 交互式组织树，点击节点查看财务指标详情
9. **财务数据查询**: 支持资产负债表/利润表/现金流量表的月度/累计/同比数据
10. **资金账户查询**: 按单位查看银行账户余额、类型、合作银行等
11. **指标对比**: 标准科目 vs 原始报表指标的自动匹配验证
12. **Vizro 仪表板**: 穿透监控大屏 (散点图 + 直方图)、中国地图单位分布
13. **日报生成**: 基于 Quarto 模板的自动报告生成

### 地理编码

14. **单位地理定位**: 通过高德地图 API 将企业地址转换为经纬度坐标

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置数据源

将集团月度财务 Excel 文件按以下结构放置：

```
data/01_raw/
├── 2024年1月/
│   ├── 集团A-202401-财务.xlsx
│   ├── 集团B-202401-财务.xlsx
│   └── ...
├── 2024年2月/
└── ...
```

文件命名格式：`{集团名称}-{年月}-财务.xlsx`

### 3. 配置项目

编辑配置文件：
- `conf/base/parameters.yml`: 设置集团根代码等参数
- `conf/base/finance_loader.yml`: 调整 Excel 解析规则
- `conf/base/indicator_mapping.yml`: 配置标准科目映射规则
- `conf/base/standard_accounts.json`: 维护标准科目库 (v2.0, 2018年版企业财务报表格式层级结构)
- `conf/base/finance_mapping_standard.yaml`: 财务指标映射标准配置
- `conf/base/hooks.yml`: Kedro 钩子配置 (自动触发地理编码等)

### 4. 运行 ETL 管道

```bash
# 运行完整管道 (财务报表 + 资金账户)
python -m src.my_finance_etl

# 仅财务报表
kedro run --pipeline finance_report

# 仅资金账户数据
kedro run --pipeline treasury_data

# Polars 优化模式
kedro run --pipeline ingest_polars
```

### 5. 地理编码 (可选)

```bash
python scripts/geocode_units.py
```

### 6. 启动可视化服务

```bash
python flask_app.py
```

访问:
- 组织树界面: http://localhost:5001
- Vizro 仪表板: http://localhost:5001/vizro/

## 数据模型

详见 [`doc/finance_warehouse_schema.md`](doc/finance_warehouse_schema.md)。

### 维度表

| 表名 | 说明 | 行数 |
|---|---|---|
| `dim_period` | 会计期间 | 2 |
| `dim_caliber` | 口径 | 1 |
| `dim_report_category` | 报表类别 (资产负债表/利润表/现金流量表/所有者权益变动表) | 4 |
| `dim_standard_account` | 标准科目树 (含层级路径, v2.0) | 151 |
| `dim_unit_report` | 报送单位 | 2830 |
| `dim_organization_tree` | 组织架构树 | 2830 |
| `dim_treasury_account` | 资金账户 | 27085 |
| `dim_treasury_account_type` | 账户类型 | 34 |
| `dim_unit_geo` | 单位地理坐标 | 1419 |

### 事实表

| 表名 | 说明 | 行数 |
|---|---|---|
| `fact_finance_data` | 财务快报数据 (本月/累计/同比) | 1,234,917 |
| `fact_treasury_account_balance` | 资金账户余额 | 10,533 |

### 视图

| 视图 | 说明 |
|---|---|
| `v_monthly_summary` | 按月-单位-报表类别的汇总 |
| `v_organization_hierarchy` | 组织架构递归展开 (含层级深度) |

## 技术栈

| 组件 | 技术 |
|---|---|
| ETL 框架 | Kedro ≥ 0.19.0 |
| 数据处理 | Polars（Pandas 仅遗留 parser 兼容层） |
| 数据仓库 | DuckDB |
| 可视化 | Flask, jsTree, Vizro, Plotly |
| 报告生成 | Quarto |
| 地理编码 | 高德地图 API |
| 包管理 | setuptools + pyproject.toml |

## 开发指南

### 管道列表

```bash
kedro registry list    # 查看所有已注册管道
```

| 管道名 | 说明 |
|---|---|
| `__default__` | 完整管道 (财务 + 资金) |
| `ingest` | 财务数据摄入 (Pandas) |
| `ingest_polars` | 财务数据摄入 (Polars 优化) |
| `process` | 指标标准化处理 |
| `warehouse` | 财务数据仓库构建 |
| `finance_report` | 财务快报完整链路 (Polars 摄入 → 处理 → 入库) |
| `treasury_data` | 资金数据完整链路 |

### 配置说明

**Excel 解析配置** (`finance_loader.yml`):
- `file_pattern`: 文件命名正则表达式
- `sheet_type_rules`: 工作表识别规则
- `numbering_rules`: 指标编号解析规则
- `default_parsing_rules`: 默认解析规则

**指标标准化配置** (`indicator_mapping.yml`):
- `standard_account_library`: 标准科目库引用路径
- `context_disambiguation`: 上下文消歧规则
- `hierarchical_matching`: 层级匹配规则

**数据目录配置** (`catalog.yml`):
- 中间数据: `parsed_excel.*`, `normalized_indicators.*`
- 维度表: `dim_period`, `dim_unit_report`, `dim_standard_account`, `dim_organization_tree`
- 事实表: `fact_finance_data`

### 扩展功能

- **添加新的数据源**: 在 `parser.py` 中扩展 `FinanceExcelParser` 类
- **添加新的指标类型**: 在 `matcher.py` 中扩展 `StandardAccountMatcher` 类
- **修改可视化界面**: 编辑 `templates/index.html` 和 `flask_app.py`
- **添加新的 Vizro 页面**: 在 `flask_app.py` 中添加 `vm.Page`

## 故障排除

### 常见问题

1. **Kedro 运行时缺少 `kedro_init_version` 错误**: 已在 `pyproject.toml` 中配置 `kedro_init_version = "1.1.1"`
2. **Excel 文件无法解析**: 检查文件格式和命名规则，参考 `finance_loader.yml` 配置
3. **标准科目匹配失败**: 验证 `standard_accounts.json` 格式和 `indicator_mapping.yml` 配置
4. **可视化服务无法连接数据库**: 检查 DuckDB 文件路径和权限
5. **Polars 优化不可用**: 系统自动回退到 Pandas 实现，检查 `data_ingestion_polars.py` 日志

### 日志查看

```bash
tail -f logs/my_finance_etl.log
```

## 版本历史

### v1.2 (2026-05-09)

- **匹配引擎重构为 YAML 查表式匹配** 🔥: `matcher.py` 完全重写 — 从 JSON 标准科目库多级匹配（名称→别名→路径→上下文消歧）切换为基于 `finance_mapping_standard.yaml` 的预计算三级索引查表，彻底消除跨报表类别污染问题
- **指标映射标准全面修正**: `finance_mapping_standard.yaml` 165+ 处修正 — 汇总项代码精确化（`01`→`01.01`、`02`→`02.01`、`02`→`02.10` 等）、资产/负债类别混淆修复 8 处（应收票据→应付票据、应收账款→预付款项/合同资产等）、子项数据类型 `TOTAL`→`SUB_DETAIL` 修正 40+ 处、层级路径补齐
- **离线科目映射脚本**: 新增 `scripts/run_mapping_standards.py` — 从 Excel 模板 + `standard_accounts.json` 自动生成完整 YAML 映射表，支持编号层级检测、父级约束匹配、乱序行定位
- **Vizro 穿透监控大屏重设计**: 货币资金散点 → **资产负债气泡散点**（资产 vs 负债，气泡=账户数，颜色=资产负债率）+ **杠杆率 vs 账户规模散点**（30-80% 正常区间高亮）；排除差额口径 (suffix=1) 和合并口径 (suffix=9) 单位；单位维度只保留最新期间数据；中国地图 UI 优化
- **Flask API 匹配验证增强**: `/api/node_data` 改用 YAML 查表 + 标准科目代码交叉验证，替代不可靠的文本清洗比较；`/api/units_geo` 新增 `DISTINCT ON` 最新期间过滤
- **数据仓库 schema 扩展**: `duckdb_data_warehouse.py` 维度表注册表新增 `dim_unit_geo`，支持地理编码表关联
- **Parser 重构文档化**: `parser.py` 标注为遗留代码，新增 `load_yaml_mapping()` 辅助函数，活跃解析器指向 `polars_optimizer.py`
- **配置简化**: `indicator_mapping.yml` 标准科目源从 JSON 切换到 YAML，移除 `context_rules` 上下文消歧规则块
- **数据质量增强**: `data_warehouse.py` 事实表 `raw_path` 增加空格规范化（`\s+`→单空格）

### v1.1 (2026-05-09)

- **标准科目库升级**: `standard_accounts.json` 升级至 v2.0，基于 2018 年版一般企业财务报表格式重构三层级科目树 (151 个科目，新增所有者权益变动表)，增强 `standard_path` 层级路径和结构化 `match_rules`
- **新增配置**: `finance_mapping_standard.yaml` 财务指标映射标准配置
- **自动地理编码**: 启用 `hooks.yml` 中的 `after_nodes` 钩子，维度表构建后自动执行高德地理编码
- **本部口径优先**: `treasury_processing.py` 资金账户实体匹配改为 suffix=0（本部口径）优先，排除合并口径 (suffix=9) 和差额口径 (suffix=1)
- **parent_code 选填**: `polars_optimizer.py` 放宽必填字段校验，parent_code 为空不再拒绝文件
- **组织树后处理文档化**: `tree_builder.py` 将自引用/父节点失踪/根节点口径统一处理逻辑暂时禁用，添加详细边界情况注释，待基础数据质量提升后重新启用
- **Flask 写入修复**: `flask_app.py` 中 geo parquet 同步 DuckDB 改用独立可写连接，避免只读连接写入报错
- **代码清理**: `treasury_parser.py` 移除未使用的 `logging` import

### v1.0 (2026-04)

- 首个完整版本：财务 ETL、DuckDB 星型模型、Flask 可视化、Vizro 仪表板

## 许可证

MIT License

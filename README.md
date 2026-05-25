# 集团财务数据标准化处理与可视化平台

基于 Kedro 数据管道框架的财务数据 ETL 与可视化平台，支持动态 Excel 文件扫描、指标标准化处理、组织树构建、资金账户解析、地理编码与可视化展示。**Vizro + Shiny 双引擎架构** — Vizro 面向领导汇报大屏，Shiny 面向个人电脑办公大屏。

**版本**: 1.6.0

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
│   │   ├── treasury_warehouse.py  # 资金数据仓库构建
│   │   ├── dim_bank_branch.py     # 银行网点维度构建 (CNAPS XML 丰富)
│   │   └── enrich_geo_coordinates.py # 地理编码节点 (高德 API + 双缓存)
│   ├── nodes/                     # Kedro 节点
│   ├── io/                        # 自定义 I/O
│   ├── utils/                     # 工具函数
│   ├── parser.py                  # Excel 财务快报解析器
│   ├── treasury_parser.py         # 资金账户 Excel 解析器
│   ├── matcher.py                 # 标准科目匹配器
│   ├── tree_builder.py            # 组织树构建器
│   ├── duckdb_data_warehouse.py   # DuckDB 星型模型构建
│   ├── polars_optimizer.py        # Polars 并行优化
│   ├── file_cache.py              # 文件 MD5 缓存 (跳过未变更 Excel)
│   ├── geocoder.py                # 高德地图地理编码 (已迁移至 scripts/)
│   ├── pipeline_registry.py       # 管道注册
│   └── settings.py                # 项目设置
├── scripts/                      # 独立工具脚本 (geocoder.py 等)
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
├── src/my_finance_shared/           # 共享模块 (v1.6)
│   ├── __init__.py
│   ├── config.py                   # 共享配置 (_proj_dir, DB_PATH, get_db_path)
│   └── database.py                 # DuckDB 连接 (带重试) + geo parquet 同步
├── src/my_finance_shiny/           # Shiny 仪表板 (v1.6 新增)
│   ├── app.py                      # Shiny 入口 (14页 + main() CLI)
│   ├── config.py                   # → 导入共享模块
│   ├── data.py                     # DuckDB SQL → Polars DataFrame 预加载
│   ├── database.py                 # → 导入共享模块
│   ├── components/                 # 可复用组件 (kpi_card, fallback)
│   ├── figures/                    # Plotly 图表工厂
│   └── pages/                      # 14 个页面模块 (home/smart_query/balance/...)
├── src/my_finance_web/             # Vizro/Flask Web 模块包 (v1.5)
│   ├── __init__.py                 # Flask 工厂函数 + CLI 入口
│   ├── config.py                   # 集中配置 → 导入共享模块
│   ├── database.py                 # DuckDB 连接与查询工具
│   ├── callbacks.py                # Dash 级联筛选回调
│   ├── routes/                     # 路由蓝图 (tree/treasury/report/geo/panreg)
│   └── dashboard/                  # Vizro 仪表板模块 (home/map/balance/panreg/…)
├── flask_app.py                   # Flask 入口 (6行薄壳 → src/my_finance_web)
├── start.sh                       # whiptail 双引擎启动器 (v1.6)
├── stop.sh                        # 统一停止脚本 (v1.6)
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
8. **文件缓存加速**: 基于 MD5 的文件级缓存 (FileCache)，跳过未变更的 Excel 文件，财报和司库数据均适用，大幅减少重复解析时间
9. **银行网点维度**: 从司库账户信息提取银行网点，通过 CNAPS XML (中国人民银行现代化支付系统行名行号) 丰富银行元数据，关联地理坐标缓存
10. **地理编码管道化**: `enrich_geo_coordinates` 节点通过高德 API 为银行网点和企业进行地理编码，使用双层缓存策略（实体缓存 + 地址缓存），支持 TTL 过期和失败重试冷却，独立 `geocoder.py` 脚本迁移至 `scripts/` 目录
11. **Web 模块化架构** 🏗️: `flask_app.py` 从 ~1436 行单体文件重构为 `src/my_finance_web/` 模块包 — 配置集中化 (`config.py`)、数据库层抽象 (`database.py`)、路由蓝图分离 (`routes/`)、Dash 回调独立 (`callbacks.py`)、Vizro 仪表板子模块化 (`dashboard/`)，支持 `my-finance-web` CLI 入口
12. **穿透监管报告** 🔍: 新增 PanReg 穿透监管模块 — 集团成员单位账户数量异常检测报告，Vizro 页面嵌入 Card 链接，Flask 路由 `/panreg-report` 直接返回 HTML 报告文件

### 可视化服务

13. **双引擎架构** 🚀 (v1.6 新增): Vizro（领导汇报大屏）+ Shiny（个人电脑办公大屏）双引擎并存，`whiptail` 图形化启动器 `start.sh` 一键启动两个服务
14. **AI 智能查询** 🤖 (v1.6 新增): QueryChat 自然语言数据探索 — 基于 LLM (Claude) 的自然语言转 SQL 过滤，联动 KPI 卡片、地理分布图、`great_tables` 细分维度表（含财务快报数据）、交互式明细表，支持 CSV 导出
15. **Shiny 多页面仪表板** 📊 (v1.6 新增): 14 页 Shiny for Python 仪表板 — 首页、智能查询、地理分布、穿透监控、账户分析、余额统计分析，与 Vizro 共享 `my_finance_shared` 数据层
16. **组织树浏览**: Flask + jsTree 交互式组织树，点击节点查看财务指标详情
17. **财务数据查询**: 支持资产负债表/利润表/现金流量表的月度/累计/同比数据
18. **资金账户查询**: 按单位查看银行账户余额、类型、合作银行等
19. **指标对比**: 标准科目 vs 原始报表指标的自动匹配验证
20. **Vizro 仪表板**: 穿透监控大屏（资产负债气泡散点 + 杠杆率分析）、单位地理分布（中国地图）
21. **账户地图**: 全国银行账户地理分布，四维筛选（子集团/银行/省份/城市），省份→城市级联
22. **账户余额统计分析**: 5 个分析页面（整体/子集团/银行/地理/交叉维度），柱状图+饼图+Treemap+箱线图+散点图
23. **日报生成**: 基于 Quarto 模板的自动报告生成
24. **日报邮件发送**: 一键生成 PDF 并通过 SMTP 脚本发送日报邮件，支持自动生成 PDF 后发送，日期参数联动

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

**方式一: whiptail 图形启动器 (推荐)**

```bash
bash start.sh
# 选择 领导汇报大屏 (Vizro) 或 个人电脑办公大屏 (Shiny)
# 两个服务同时启动，浏览器自动打开选中页面
bash stop.sh   # 停止所有服务
```

**方式二: 手动启动**

```bash
# Vizro (Flask, port 5001)
micromamba run -n shiny_vizro python -c "
from src.my_finance_web import create_app
create_app().run(debug=False, host='0.0.0.0', port=5001)
"

# Shiny (port 8000)
micromamba run -n shiny_vizro shiny run --host 0.0.0.0 --port 8000 src.my_finance_shiny.app
```

**方式三: CLI 入口**

```bash
my-finance-web    # Vizro → http://localhost:5001
my-finance-shiny  # Shiny → http://localhost:8000
```

访问:
- Vizro 领导汇报大屏: http://localhost:5001
- Shiny 个人电脑办公大屏: http://localhost:8000

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
| `dim_bank_branch` | 银行网点 (含 CNAPS 元数据) | 2,590 |
| `dim_unit_geo` | 单位地理坐标 | 1,419 |

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
| 可视化 | Flask, jsTree, Vizro, Shiny for Python, Plotly |
| AI 查询 | QueryChat + Anthropic Claude (自然语言 → SQL) |
| 精美表格 | great_tables (GT) |
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
| `treasury_data` | 资金数据完整链路 (含银行网点维度 + 地理编码) |
| `dim_bank_branch` | 银行网点维度构建 (独立运行) |

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

### v1.6.0 (2026-05-25)

- **Shiny 双引擎架构** 🚀: 新增 `src/my_finance_shiny/` 14 页 Shiny for Python 仪表板 — Vizro（领导汇报大屏，port 5001）+ Shiny（个人电脑办公大屏，port 8000）双引擎并存，覆盖首页、地理分布、穿透监控、账户分析、余额统计分析五大模块
- **AI 智能查询** 🤖: 新增 `smart_query` 页面 — 基于 QueryChat + Anthropic Claude 的自然语言数据探索，联动 KPI 卡片（账户总数/余额合计/银行类型分布）、Plotly 地理分布图（国内城市 + 海外国家）、`great_tables` 细分维度表（含财务快报财务公司存款/商业银行存款数据）、交互式明细表，支持 CSV 导出
- **共享模块重构** 🏗️: 抽取 `src/my_finance_shared/` — 消除 Vizro 与 Shiny 间的 `config.py` 和 `database.py` 重复代码，统一 DuckDB 连接（带重试锁）和 geo parquet 同步逻辑
- **whiptail 图形启动器** 🎛️: `start.sh`/`stop.sh` — whiptail 伪图形界面，一键启动双服务并自动打开浏览器，日志写入 `logs/` 目录
- **micromamba 环境**: 新建 `shiny_vizro` 环境 (Python 3.13)，预装 shiny、vizro、dash、querychat、anthropic、great-tables 等全套依赖
- **CLI 入口**: `pyproject.toml` 新增 `my-finance-shiny` 脚本入口，版本号升至 1.6.0
- **财务快报数据集成**: 子集团维度表关联资产负债表（货币资金 → 财务公司存款 + 商业银行存款），双日期标注（司库数据截至日期 + 财务快报截至日期）
- **KPI 美化**: 银行类型分布三列彩色展示（合作银行蓝/非合作银行橙/财务公司绿）

### v1.5.1 (2026-05-14)

- **穿透监管报告** 🔍: 新增 PanReg 穿透监管功能模块 — 集团成员单位账户数量异常检测报告
  - `routes/panreg.py`: 路由蓝印 `panreg_bp`，端点 `/panreg-report` 返回 `account_PanReg_report.html` 静态报告文件
  - `dashboard/panreg.py`: Vizro 页面 "穿透监管"（Card 组件嵌入 Markdown 链接）
  - `navigation.py`: 导航菜单"分析"板块新增 "panreg" 页面入口（NavBar 二级菜单同步）
  - `__init__.py` + `routes/__init__.py`: 注册 `panreg_bp` 蓝印

### v1.5.2 (2026-05-14)

- **穿透监管报告扩展** 🔍: PanReg 模块新增第二个报告端点
  - `dashboard/panreg.py`: 原有 Card 重构为"逃逸账户检测报告"（`/panreg-report`），新增"账户数量异常检测报告" Card（`/panreg-report1`）
  - `routes/panreg.py`: 新增 `/panreg-report1` 端点，指向 `accountpro_PanReg_report.html` 静态报告文件

### v1.5 (2026-05-14)

- **Web 模块化架构重构** 🏗️: `flask_app.py` 从约 1,436 行单体文件完全拆解为 `src/my_finance_web/` 模块包，遵循 Flask 工厂模式 + Blueprint 路由分离 + Vizro 仪表板子模块化，大幅提升可维护性与代码组织——配置集中至 `config.py`（DB 路径/YAML 查表/邮件配置/Quarto 路径），数据库层抽象至 `database.py`（DuckDB 连接 + 表存在检测 + 实体 ID 解析），4 个路由蓝印拆分为 `routes/` 子包（tree/treasury/report/geo），Dash 级联筛选回调独立为 `callbacks.py`，7 个 Vizro 页面模块移至 `dashboard/` 子包（home/data/navigation/map/balance/account_map/account_detail）
- **CLI 入口新增** 🚀: `pyproject.toml` 注册 `my-finance-web` 脚本入口，映射至 `src.my_finance_web:main`，支持 `pip install -e .` 后直接使用
- **入口精简**: `flask_app.py` 缩减为 6 行薄壳——仅导入 `create_app()` 并启动，原 ~1,430 行业务逻辑全部迁移至 `my_finance_web` 包
- **辅助工具**: 新增 `kill.sh` 端口/进程快捷终止脚本
- **依赖声明补全**: `pyproject.toml` 补充 `vizro`/`dash`/`numpy`/`plotly`/`polars` 显式依赖声明

### v1.4.4 (2026-05-14)

- **日报一键发送** 📧: 新增 `/api/send_report` API — 自动生成 Quarto PDF（如不存在）并调用 SMTP shell 脚本发送日报邮件；前端新增「发送日报」按钮（绿色），点击后自动取当前日期、展示发送状态，失败时显示具体错误信息
- **邮件配置独立化** ⚙️: `parameters.yml` 新增 `email` 配置节（from/to/subject_prefix），Flask 运行时动态读取，支持环境变量传递，解耦凭证与代码

### v1.4.3 (2026-05-13)

- **日报生成日期参数恢复** 🔧: `flask_app.py` `/api/generate_report` 恢复 year/month/day 查询参数，移除临时时间戳占位逻辑，日期参数正确传递至 Quarto 渲染命令（`-P year/month/day`），报告文件命名从时间戳改为日期格式
- **清理过期生成文件**: 移除 `generated_reports/` 中的临时报告文件

### v1.4.2 (2026-05-13)

- **AgGrid 筛选修复** 🔧: 修复 v1.4.1 中 5 维筛选对 AgGrid 不生效的 bug — `_account_detail_df` 保留英文列名匹配 Vizro Filter，改用 `columnDefs.headerName` 设置中文显示名；删除无效 `rowData` 手动回调（目标组件 ID 错误 + 与 Vizro 内部竞态）
- **新增账户户名列** 📋: SQL 查询增加 `ta.account_name`，AgGrid 第二列显示具体开户企业名称
- **代码清理**: 移除冗余的 `_account_detail_df` 列 rename 和重复的 `开户网点` 列

### v1.4.1 (2026-05-13)

- **账户明细表页面** 📋: 新增独立 Vizro 页面 `account-detail`，使用 AgGrid 交互式表格展示全量账户明细（子集团/账户户名/所属银行/城市/省份/余额/开户网点），支持分页和排序
- **账户地图内嵌表格** 🗺️: `bank-account-map` 地图页面新增加 AgGrid 明细表，通过 Vizro 自动筛选联动地图气泡；5 维筛选（子集团/所属银行/省份/城市/开户网点）统一作用于图表和表格，Dash 回调实现省份→城市级联选项更新
- **AgGrid 列名对齐修复** 🔧: `_account_detail_df` 保留英文列名匹配 Vizro Filter 列名要求（不再 rename 为中文），改用 `columnDefs.headerName` 设置中文显示名；删除无效的 `rowData` 手动回调（目标组件 ID 错误 + 与 Vizro 内部 `_on_page_load` 竞态），筛选由 Vizro 自动托管
- **导航菜单更新**: "分析"菜单新增"账户明细表"入口

### v1.4 (2026-05-13)

- **文件缓存加速** ⚡: 新增 `file_cache.py` — 基于 MD5 的文件级缓存模块，跳过未变更的 Excel 文件解析；`polars_optimizer.py` 和 `treasury_ingestion.py` 均已集成，支持财报（base_info + report_data）和司库（treasury）双模式缓存；参数通过 `parameters.yml` 的 `processing.enable_file_cache` 开关控制
- **银行网点维度管道** 🏦: 新增 `dim_bank_branch.py` pipeline 节点 — 从司库账户信息的 `institution_code` 提取唯一银行网点 (2,590 个)，关联 CNAPS XML (中国人民银行现代化支付系统行名行号) 丰富银行名称、类型、地区代码等 15 个元数据字段，通过 `geo_bank.parquet` 缓存关联经纬度坐标
- **地理编码管道化** 🌍: 新增 `enrich_geo_coordinates.py` pipeline 节点 — 将地理编码从 `after_nodes` 钩子重构为正式 pipeline 节点，银行网点通过高德 POI 搜索编码，企业通过高德 geocode 编码；采用双层缓存策略（实体缓存 geo_enterprise/geo_bank + 地址缓存 geo_address），支持地址 TTL 过期 (12 个月) 和失败重试冷却 (3 个月)；`geocoder.py` 从 `src/` 迁移至 `scripts/`，保留为独立修复脚本
- **DuckDB 数仓扩展** 📦: `duckdb_data_warehouse.py` 新增 `dim_bank_branch` 表加载 (含 `institution_code` 索引)；`treasury_warehouse.py` 新增 `dim_bank_branch_enriched` 和 `dim_unit_geo` 同步写入
- **Pipeline 注册重构** 🔗: `pipeline_registry.py` 注册 `dim_bank_branch` 和 `enrich_geo_coordinates` pipeline；`treasury_full` 重构为 5 阶段链式管道 (摄入 → 处理 → 银行网点 → 地理编码 → 数仓)；新增 `dim_bank_branch` 独立管道入口
- **配置扩展** 📝: `catalog.yml` 新增 `dim_bank_branch`、`dim_bank_branch_enriched`、`dim_unit_geo` 三个数据集；`parameters.yml` 新增 `processing.enable_file_cache`/`processing.file_cache_dir`、`bank_branch.cnaps_xml_path`/`bank_branch.geo_cache_path`、`geo.*` 配置节；`hooks.yml` 地理编码钩子注释更新为 `enrich_geo_coordinates` 管道引用
- **可视化优化** 🎨: `flask_app.py` 账户地图散点图颜色方案从 Viridis_r 改为 Viridis；银行网点关联 `customdata` 字段支持点击查看网点名称；`dim_unit_geo` 同步逻辑从 `CREATE TABLE IF NOT EXISTS` 改为 `CREATE OR REPLACE TABLE IF NOT EXISTS` 确保数据刷新；移除已删除 `geocoder` 的直接 import 依赖
- **安全修复** 🔧: `hooks.py` `after_nodes` 钩子读取增加中间 None 安全访问（`.get(hook_type, {}).get(...)` → `.get(hook_type) or {}`），避免 YAML 注释导致 `NoneType` 报错

### v1.3 (2026-05-12)

- **Vizro 多页面仪表板重构** 🔥: 新增 HOME 欢迎页，导航从单层改为 NavBar 二级菜单（HOME/账户），账户下设监控、分析、账户余额统计分析三大模块
- **银行账户地图** 🗺️: 新增全国账户地理分布图，按网点聚合余额，悬浮框展示子集团明细；支持子集团/所属银行/省份/城市四维筛选（Dash 回调级联联动），省份→城市自然级联；气泡大小 log10(余额)² 缩放，颜色 Viridis_r 渐变
- **账户余额统计分析模块** 📊: 5 个分析页面 — 整体情况（KPI 卡片+直方图+饼图+柱状图）、子集团维度（水平柱状图+Treemap）、所属银行维度（柱状图+饼图+堆叠柱状图）、地理维度（城市排名柱状图）、交叉维度（散点图+箱线图）；一条基础查询支持全模块聚合
- **城市→省份映射** 📍: 内置 188 个城市→34 个省级行政区映射字典，解决 `dim_bank_branch` 无省份字段问题
- **数据维度增强**: `dim_bank_branch` 表纳入数据仓库（2,590 个银行网点，94.4% 已地理编码），通过 `institution_code` 关联资金账户表
- **筛选交互优化**: 移除故障 Dash 全联动回调，保留省份→城市单向级联；城市变化不反驱省份（已注释说明）
- **数据展示优化**: 余额单位统一为万元（hover + colorbar），气泡公式迭代至 `log10**2 * 2`

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

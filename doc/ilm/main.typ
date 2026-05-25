#import "@preview/ilm:2.1.0": *

#set text(lang: "zh", font: ("FandolSong", "FandolHei"), size: 11pt)

#show: ilm.with(
  title: [财务数据分析平台 操作手册],
  authors: "v1.6.0",
  date: datetime(year: 2026, month: 05, day: 25),
  abstract: [
    本手册面向集团财务数据分析平台的日常使用者，涵盖环境准备、ETL 数据管道、
    Vizro 领导汇报大屏、Shiny 个人电脑办公大屏、AI 智能查询、报告生成、
    故障排除等内容。
  ],
  paper-size: "a4",
  footer: "page-number-center",
  figure-index: (enabled: false),
  table-index: (enabled: false),
  listing-index: (enabled: false),
  raw-text: (font: ("Fira Code", "Courier New"), size: 9pt),
)

// ============================================================
// 第1章 平台概述
// ============================================================

= 平台概述

本平台是集团财务数据标准化处理与可视化系统，基于 *Vizro + Shiny 双引擎架构*。

#table(
  columns: (1fr, 1fr, 1fr),
  table.header(
    [*引擎*], [*定位*], [*端口*],
  ),
  [Vizro], [领导汇报大屏 --- 穿透监控、地理分布、日报邮件], [5001],
  [Shiny], [个人电脑办公大屏 --- 14 页交互分析、AI 智能查询], [8000],
)

两者共享同一个 DuckDB 数据仓库，底层数据通过 ETL 管道统一处理。

== 架构示意

```text
Excel 原始文件 -> Kedro ETL 管道 -> DuckDB 数据仓库
                                      ├── Vizro (Flask, :5001)
                                      ├── Shiny (Shiny for Python, :8000)
                                      └── 共享模块 (my_finance_shared)
```

// ============================================================
// 第2章 环境准备
// ============================================================

= 环境准备

== 系统要求

- Linux（推荐） macOS
- Python >= 3.13
- micromamba（推荐）或 conda
- whiptail（图形启动器依赖，`sudo apt install whiptail`）

== 创建环境

```bash
micromamba create -n shiny_vizro python=3.13 -y
micromamba activate shiny_vizro

pip install shiny shinywidgets shinychat plotly pandas polars duckdb \
    flask pyyaml python-dotenv numpy openpyxl vizro dash kedro \
    great-tables querychat anthropic fastexcel pyarrow
```

== 配置文件

#table(
  columns: (1fr, 2fr),
  table.header([*文件*], [*用途*]),
  [`conf/base/parameters.yml`], [数据库路径、邮件配置、文件缓存开关],
  [`conf/base/catalog.yml`], [Kedro 数据目录定义],
  [`conf/base/finance_loader.yml`], [Excel 解析规则],
  [`conf/base/treasury_loader.yml`], [资金账户解析规则],
  [`.env`], [*必须*包含 `ANTHROPIC_API_KEY`（AI 智能查询需要）],
)

=== .env 示例

```ini
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxx
```

// ============================================================
// 第3章 数据准备与 ETL
// ============================================================

= 数据准备与 ETL

== 原始数据目录结构

```text
data/01_raw/
├── 2026年02月财务快报数据/
│   ├── 单位A-202602-财务.xlsx
│   └── ...
├── 2026年03月财务快报数据/
└── 2026年4月司库账户数据/
```

== 运行 ETL 管道

```bash
python -m src.my_finance_etl               # 完整管道

kedro run --pipeline finance_report        # 仅财务快报
kedro run --pipeline treasury_data         # 仅资金账户
kedro run --pipeline ingest_polars         # Polars 加速模式
kedro registry list                        # 查看所有管道
```

== 管道说明

#table(
  columns: (1fr, 1fr, 3fr),
  table.header([*管道名*], [*功能*], [*说明*]),
  [`__default__`], [完整管道], [财务 + 资金 + 数仓 + 地理编码],
  [`ingest`], [财务摄入 (Pandas)], [兼容模式],
  [`ingest_polars`], [财务摄入 (Polars)], [高性能模式],
  [`process`], [指标标准化], [科目匹配 + 标准化],
  [`warehouse`], [数仓构建], [DuckDB 星型模型],
  [`finance_report`], [财务快报链路], [摄入->处理->入库],
  [`treasury_data`], [资金数据链路], [摄入->银行网点->地理编码->入库],
  [`dim_bank_branch`], [银行网点维度], [CNAPS XML 丰富],
  [`enrich_geo_coordinates`], [地理编码], [高德 API 坐标获取],
)

// ============================================================
// 第4章 启动与停止服务
// ============================================================

= 启动与停止服务

== 图形启动器（推荐）

```bash
bash start.sh
```

弹出 whiptail 菜单，两个服务同时启动，浏览器自动打开选中页面。日志写入 `logs/` 目录。

== 手动启动

```bash
# Vizro（领导汇报大屏, port 5001）
micromamba run -n shiny_vizro python -c "
from src.my_finance_web import create_app
create_app().run(debug=False, host='0.0.0.0', port=5001)
" > logs/vizro.log 2>&1 &

# Shiny（个人电脑办公大屏, port 8000）
micromamba run -n shiny_vizro shiny run \
    --host 0.0.0.0 --port 8000 \
    src.my_finance_shiny.app \
    > logs/shiny.log 2>&1 &
```

== 停止服务

```bash
bash stop.sh
```

== 服务地址

#table(
  columns: (1fr, 2fr),
  table.header([*服务*], [*地址*]),
  [Vizro 领导汇报大屏], [#link("http://localhost:5001")],
  [Shiny 个人电脑办公大屏], [#link("http://localhost:8000")],
)

// ============================================================
// 第5章 Vizro 领导汇报大屏
// ============================================================

= Vizro 领导汇报大屏

Vizro 是面向*领导汇报场景*的仪表板，运行在端口 5001。

== 页面导航

- 首页
- *穿透监控大屏* --- 资产负债气泡散点 + 杠杆率分析
- *账户地图* --- 全国账户地理分布（四维筛选）
- *账户明细表* --- AgGrid 交互式表格
- *穿透监管* --- 逃逸账户 + 账户数量异常检测报告
- *余额统计分析*
  - 整体情况 --- KPI + 直方图 + 饼图
  - 子集团维度 --- 水平柱状图 + Treemap
  - 所属银行维度 --- 柱状图 + 饼图 + 堆叠柱状图
  - 地理维度 --- Top 20 城市排名
  - 交叉维度 --- 散点图 + 箱线图

== 关键交互

- *账户地图*：支持子集团/所属银行/省份/城市四维筛选，省份->城市级联
- *AgGrid 明细表*：支持排序、筛选、分页
- *穿透监管报告*：直接返回 HTML 报告文件

// ============================================================
// 第6章 Shiny 个人电脑办公大屏
// ============================================================

= Shiny 个人电脑办公大屏

Shiny 是面向*个人办公场景*的仪表板，运行在端口 8000，共 14 个页面。

== 页面导航

- *首页* --- 欢迎页 + 快速导航
- *智能查询* --- AI 自然语言数据探索（详见第 7 章）
- *地理分布* --- 单位地理坐标中国地图

*穿透监控*:
- 监控大屏 --- 资产负债散点分析
- 账户地图 --- 账户地理分布气泡图

*账户分析*:
- 账户明细表 --- 交互式数据表
- 穿透监管 --- PanReg 报告入口

*余额统计分析*:
- 整体情况 --- KPI + 分布图
- 子集团维度 --- 排名 + Treemap
- 所属银行维度 --- 多图表分析
- 地理维度 --- 城市排名
- 交叉维度 --- 散点 + 箱线

== 关键交互

- *导航栏*：顶部 Tab 切换，支持两级下拉菜单
- *图表*：全部 Plotly 交互图表（缩放/悬停/选择）
- *数据表*：支持排序和导出 CSV

// ============================================================
// 第7章 AI 智能查询
// ============================================================

= AI 智能查询

智能查询是 Shiny 仪表板的核心页面，基于 *QueryChat + Anthropic Claude* 实现自然语言数据探索。

== 使用方式

+ 切换到「智能查询」页面
+ 在左侧聊天框输入自然语言问题
+ LLM 自动将问题转换为 SQL 过滤条件
+ 页面所有组件*联动更新*：KPI 卡片、地图、表格

== 查询示例

#table(
  columns: (1fr, 2fr),
  table.header([*类型*], [*示例*]),
  [按子集团筛选], ["显示北方公司的所有账户"],
  [按金额筛选], ["余额大于1000万的账户有哪些"],
  [按地区筛选], ["香港地区有哪些美元账户"],
  [按银行筛选], ["合作银行的账户，按余额从高到低"],
  [组合条件], ["凌云集团在中国工商银行的账户"],
  [统计分析], ["各子集团的账户数量和余额总和"],
)

== 页面组件

#table(
  columns: (1fr, 2fr, 3fr),
  table.header([*区域*], [*组件*], [*说明*]),
  [顶部], [KPI 卡片 x3], [账户总数、余额合计、银行类型分布（三列彩色）],
  [中部], [地理分布图], [国内城市 + 海外国家散点地图],
  [下部], [子集团细分维度表], [great_tables 表格，含财务快报数据],
  [底部], [账户明细表], [交互式 DataTable，支持导出 CSV],
)

== 导出功能

每个表格右上角有「导出 CSV」按钮，文件名格式：
```text
智能查询_子集团细分维度_20260525_143021.csv
智能查询_账户明细_20260525_143021.csv
```

== 财务快报数据集成

子集团维度表中的 *财务公司存款(快报)* 和 *商业银行存款(快报)* 来源于资产负债表*货币资金*科目，单位已转换为_亿元_。

表格标题显示双日期：
```text
司库数据截至 2026-04-30　　财务快报数据截至 2026-03-31
```

// ============================================================
// 第8章 常见操作速查
// ============================================================

= 常见操作速查

== 环境

```bash
micromamba activate shiny_vizro
```

== ETL

```bash
python -m src.my_finance_etl
kedro run --pipeline finance_report
kedro run --pipeline treasury_data
```

== 服务

```bash
bash start.sh                              # 图形启动器
bash stop.sh                               # 停止
```

== 日志

```bash
tail -f logs/shiny.log
tail -f logs/vizro.log
tail -f logs/my_finance_etl.log
```

== 进程检查

```bash
lsof -i :5001
lsof -i :8000
```

// ============================================================
// 第9章 故障排除
// ============================================================

= 故障排除

== 服务无法启动

#table(
  columns: (2fr, 2fr, 3fr),
  table.header([*症状*], [*原因*], [*解决*]),
  [`ModuleNotFoundError`], [缺少依赖], [pip install xxx],
  [`Port already in use`], [端口被占用], [bash stop.sh 后重启],
  [`ImportError`], [模块路径有误], [确保在项目根目录运行],
  [`ANTHROPIC_API_KEY`], [缺少 API 密钥], [检查 .env 文件],
)

== DuckDB 锁定

多个进程同时写 DuckDB 时会冲突：

```bash
bash stop.sh
lsof data/warehouse/finance_warehouse.duckdb   # 检查残留
bash start.sh                                  # 重启
```

== AI 查询无响应

- 检查 `.env` 文件中的 `ANTHROPIC_API_KEY` 是否有效
- 检查网络是否能访问 Anthropic API
- 查看 `logs/shiny.log` 中的错误信息

== 数据不更新

运行 ETL 管道后数据才会刷新：

```bash
micromamba activate shiny_vizro
python -m src.my_finance_etl
bash stop.sh && bash start.sh
```

== 浏览器无法打开

手动在浏览器中输入地址：
- Vizro: `http://localhost:5001`
- Shiny: `http://localhost:8000`

---

*技术支持：查看 `logs/` 目录下的日志文件获取详细错误信息。*

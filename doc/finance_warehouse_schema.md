# finance_warehouse.duckdb — Schema 参考

**数据库**: `data/warehouse/finance_warehouse.duckdb` (2.0 GB)  
**Schema**: `finance_data`  
**数据期间**: 2026-02, 2026-03 (财务报表), 2026-04 (资金账户)  
**ETL 时间**: 2026-04-24  
**版本**: 1.0

---

## 实体关系总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                          DIMENSION (维度层)                           │
│                                                                      │
│  dim_period ──────────┐    dim_caliber                               │
│  (会计期间)            │    (口径)                                    │
│                        │                                              │
│  dim_report_category ──┤    dim_standard_account                     │
│  (报表类别)            │    (标准科目, 124 rows)                       │
│                        │         │                                    │
│  dim_unit_report ──────┼────────┼──── dim_organization_tree          │
│  (报送单位, 2830 rows)  │        │     (组织架构树, 2830 rows)         │
│         │              │        │              │                      │
│         │    ┌─────────┘        │              │                      │
│         ▼    ▼                  ▼              │                      │
│  ┌──────────────────────┐                      │                      │
│  │   fact_finance_data  │  ◄── foreign keys ──┘                      │
│  │   (1,234,917 rows)   │                                             │
│  └──────────────────────┘                                             │
│                                                                      │
│  dim_treasury_account ──── dim_treasury_account_type                 │
│  (资金账户, 27085 rows)    (账户类型, 34 rows)                        │
│         │                                                             │
│         ▼                                                             │
│  fact_treasury_account_balance                                        │
│  (资金账户余额, 10,533 rows)                                          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 维度表 (Dimension)

### dim_period — 会计期间 (2 rows)

| 列 | 类型 | 说明 |
|---|---|---|
| period_id | VARCHAR | 主键，格式 `YYYY-MM-DD`（月末日期） |
| period_name | VARCHAR | 中文名，如 `2026年02月` |
| year | BIGINT | 年份 |
| month | BIGINT | 月份 |

### dim_caliber — 口径 (1 row)

| 列 | 类型 | 说明 |
|---|---|---|
| caliber_id | VARCHAR | 主键 (`1`) |
| caliber_name | VARCHAR | `合并口径` |
| description | VARCHAR | 说明 |

### dim_report_category — 报表类别 (3 rows)

| 列 | 类型 | 说明 |
|---|---|---|
| category_id | VARCHAR | `1`=资产负债表, `2`=利润表, `3`=现金流量表 |
| category_name | VARCHAR | 中文类别名 |

### dim_standard_account — 标准科目 (124 rows)

财务标准科目树，含层级路径。account_code 用点号分隔层级（`01` > `01.01` > `01.02`）。

| 列 | 类型 | 说明 |
|---|---|---|
| account_code | VARCHAR | 科目编码，如 `01.02.01` |
| account_name | VARCHAR | 科目名称 |
| report_category | VARCHAR | 所属报表类别 |
| account_code_dash | VARCHAR | 短横格式编码，如 `01-02-01` |
| standard_path | VARCHAR | 完整路径，如 `资产总额 > 流动资产合计 > 货币资金` |
| match_priority | BIGINT | 匹配优先级 |
| sort_order | BIGINT | 排序 |

**顶级科目**: 资产总额(01), 负债总额(02), 所有者权益(03), 营业收入(04), 营业成本(05)...

### dim_unit_report — 报送单位 (2830 rows)

| 列 | 类型 | 说明 |
|---|---|---|
| entity_report_id | VARCHAR | 主键 |
| unit_name | VARCHAR | 单位全称 |
| code | VARCHAR | 单位信用代码 |
| suffix | VARCHAR | 后缀 (0=本部, 其他数字=子公司) |
| unit | VARCHAR | 所属上级单位 |
| period | VARCHAR | 所属期间 |
| province | VARCHAR | 省份 |
| city | VARCHAR | 城市 |
| area | VARCHAR | 区县 |
| enterprise_address | VARCHAR | 企业地址 |
| sasac_area_name | VARCHAR | 国资委区域名称 |

### dim_organization_tree — 组织架构树 (2830 rows)

组织架构的父子关系（与 dim_unit_report 构成树形结构）。

| 列 | 类型 | 说明 |
|---|---|---|
| node_id | VARCHAR | 节点 ID |
| parent_id | VARCHAR | 父节点 ID (`#`=根节点) |
| node_name | VARCHAR | 节点名称 |
| unit_code | VARCHAR | 单位编码 |
| suffix | VARCHAR | 后缀 |
| period | VARCHAR | 所属期间 |
| entity_report_id | VARCHAR | 关联 dim_unit_report |

### dim_treasury_account — 资金账户 (27085 rows)

| 列 | 类型 | 说明 |
|---|---|---|
| account_id | VARCHAR | 主键 |
| account_number | VARCHAR | 银行账号 |
| account_name | VARCHAR | 账户名称 |
| financial_institution | VARCHAR | 金融机构 |
| opening_institution | VARCHAR | 开户机构全称 |
| institution_code | VARCHAR | 机构编码 |
| account_status | VARCHAR | 账户状态 |
| country_region | VARCHAR | 国家地区 |
| account_nature | VARCHAR | 账户性质 |
| is_overseas | VARCHAR | 境内/境外 |
| bank_city | VARCHAR | 开户城市 |
| is_partner_bank | VARCHAR | 合作银行/非合作银行 |
| currency | VARCHAR | 币种 |
| account_usage | VARCHAR | 账户用途 |
| is_visible | VARCHAR | 是否可见 |
| type_id | VARCHAR | 关联 dim_treasury_account_type |
| type_label | VARCHAR | 账户类型标签 |
| entity_report_id | VARCHAR | 关联 dim_unit_report |
| org_code | VARCHAR | 组织机构代码 |
| unit_name | VARCHAR | 单位名称 |
| unit_id | VARCHAR | 单位 ID |
| sub_group_name | VARCHAR | 子集团 |
| source_file | VARCHAR | 数据来源文件 |
| period | VARCHAR | 数据期间 |

### dim_treasury_account_type — 账户类型 (34 rows)

| 列 | 类型 | 说明 |
|---|---|---|
| type_id | VARCHAR | 主键 |
| type_label | VARCHAR | 类型标签（基本账户/支出账户/收入账户/保证金户/境外账户...） |
| category_label | VARCHAR | 父类别标签 |

### dim_unit_geo — 单位地理信息

| 列 | 类型 | 说明 |
|---|---|---|
| entity_report_id | VARCHAR | 关联 dim_unit_report |
| longitude | DOUBLE | 经度 |
| latitude | DOUBLE | 纬度 |

---

## 事实表 (Fact)

### fact_finance_data — 财务数据 (1,234,917 rows)

**核心事实表**，存储各单位的财务报表数据。

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR | 主键 UUID |
| entity_report_id | VARCHAR | 关联 dim_unit_report |
| period_id | VARCHAR | 关联 dim_period (`2026-02-28` / `2026-03-31`) |
| account_code | VARCHAR | 关联 dim_standard_account |
| caliber_id | VARCHAR | 关联 dim_caliber |
| category_id | VARCHAR | 关联 dim_report_category |
| value | DOUBLE | 金额 |
| value_column | VARCHAR | `本月数` / `本年累计` / `上年同期` |
| is_standardized | BOOLEAN | 是否已标准化 |
| source_file | VARCHAR | 来源文件 (`司库报表_主要财务指标快报表`) |
| raw_path | VARCHAR | 原始报表行路径 |
| top_level_account_name | VARCHAR | 顶级科目名称 |
| etl_created_at | VARCHAR | ETL 时间戳 |

**常用查询提示**:
- value_column 区分月度/累计/同比数据
- 多条记录对应同一 entity+period+account 的不同 value_column
- 要查"本月资产负债"：`WHERE category_id='1' AND value_column='本月数'`

### fact_treasury_account_balance — 资金账户余额 (10,533 rows)

| 列 | 类型 | 说明 |
|---|---|---|
| account_id | VARCHAR | 关联 dim_treasury_account |
| entity_report_id | VARCHAR | 关联 dim_unit_report |
| period | VARCHAR | 数据期间 |
| balance_amount | DOUBLE | 余额（原币） |
| converted_amount | DOUBLE | 折算金额 |
| currency | VARCHAR | 币种 |
| balance_date | VARCHAR | 余额日期 |
| is_partner_bank | VARCHAR | 合作银行/非合作银行 |
| is_overseas | VARCHAR | 境内/境外 |

---

## 视图 (View)

### v_monthly_summary — 月度汇总

按月-单位-报表类别的汇总，含 total_value / avg_value / record_count。

```sql
-- 来源: fact_finance_data + dim_period + dim_unit_report + dim_report_category
SELECT
    f.period_id,
    u.unit_name,
    rc.category_name,
    SUM(f.value) AS total_value,
    AVG(f.value) AS avg_value,
    COUNT(*)     AS record_count
FROM finance_data.fact_finance_data f
JOIN finance_data.dim_unit_report u ON f.entity_report_id = u.entity_report_id
JOIN finance_data.dim_report_category rc ON f.category_id = rc.category_id
WHERE f.value_column = '本月数'
GROUP BY f.period_id, u.unit_name, rc.category_name
```

### v_organization_hierarchy — 组织架构层级

基于 dim_organization_tree 的递归 CTE，展开完整的组织层级。

| level | 说明 |
|---|---|
| 0 | 根节点 |
| 1,2,3... | 子级深度 |

```sql
WITH RECURSIVE org_tree AS (
    SELECT node_id, parent_id, node_name, 0 AS level,
           node_name AS path
    FROM finance_data.dim_organization_tree
    WHERE parent_id = '#'

    UNION ALL

    SELECT t.node_id, t.parent_id, t.node_name, ot.level + 1,
           ot.path || ' > ' || t.node_name
    FROM finance_data.dim_organization_tree t
    JOIN org_tree ot ON t.parent_id = ot.node_id
    WHERE ot.level < 10
)
SELECT * FROM org_tree ORDER BY level, node_name
```

---

## 关联关系速查

```
fact_finance_data.entity_report_id  → dim_unit_report.entity_report_id
fact_finance_data.period_id         → dim_period.period_id
fact_finance_data.account_code      → dim_standard_account.account_code
fact_finance_data.caliber_id        → dim_caliber.caliber_id
fact_finance_data.category_id       → dim_report_category.category_id

fact_treasury_account_balance.account_id       → dim_treasury_account.account_id
fact_treasury_account_balance.entity_report_id → dim_unit_report.entity_report_id

dim_organization_tree.entity_report_id → dim_unit_report.entity_report_id
dim_treasury_account.entity_report_id  → dim_unit_report.entity_report_id
dim_treasury_account.type_id           → dim_treasury_account_type.type_id

dim_unit_geo.entity_report_id          → dim_unit_report.entity_report_id
```

---

## 查询食谱 (Query Cookbook)

### 1. 查询某单位最新期间资产负债表

```sql
SELECT
    sa.account_name                  AS 科目名称,
    sa.standard_path                 AS 科目路径,
    SUM(CASE WHEN f.value_column = '本月数'    THEN f.value END) AS 本月数,
    SUM(CASE WHEN f.value_column = '本年累计'  THEN f.value END) AS 本年累计,
    SUM(CASE WHEN f.value_column = '上年同期'  THEN f.value END) AS 上年同期
FROM finance_data.fact_finance_data f
JOIN finance_data.dim_standard_account sa
    ON f.account_code = sa.account_code
   AND sa.report_category = '资产负债表'
WHERE f.entity_report_id = '<entity_id>'
  AND f.period_id = (SELECT MAX(period_id) FROM finance_data.fact_finance_data)
  AND f.category_id = '1'
GROUP BY sa.account_name, sa.standard_path, sa.sort_order
ORDER BY sa.sort_order
```

### 2. 所有单位资产总额排名

```sql
SELECT
    u.unit_name                      AS 单位名称,
    SUM(f.value)                     AS 资产总额
FROM finance_data.fact_finance_data f
JOIN finance_data.dim_unit_report u ON f.entity_report_id = u.entity_report_id
JOIN finance_data.dim_standard_account sa ON f.account_code = sa.account_code
WHERE sa.account_name = '资产总额'
  AND f.value_column = '本月数'
  AND f.period_id = (SELECT MAX(period_id) FROM finance_data.fact_finance_data)
GROUP BY u.unit_name
ORDER BY 资产总额 DESC
```

### 3. 资金账户余额按金融机构汇总

```sql
SELECT
    COALESCE(NULLIF(ta.financial_institution, ''), ta.opening_institution) AS 金融机构,
    COUNT(DISTINCT fb.account_id)     AS 账户数量,
    SUM(fb.converted_amount)          AS 可用余额合计
FROM finance_data.fact_treasury_account_balance fb
JOIN finance_data.dim_treasury_account ta ON fb.account_id = ta.account_id
WHERE fb.converted_amount IS NOT NULL
  AND fb.period = (SELECT MAX(period) FROM finance_data.fact_treasury_account_balance)
GROUP BY 金融机构
ORDER BY 可用余额合计 DESC
```

### 4. 月度趋势 — 资产总额环比变化

```sql
SELECT
    p.period_name                     AS 期间,
    SUM(f.value)                      AS 资产总额,
    LAG(SUM(f.value)) OVER (ORDER BY p.period_id) AS 上期资产总额,
    SUM(f.value) - LAG(SUM(f.value)) OVER (ORDER BY p.period_id) AS 环比变化
FROM finance_data.fact_finance_data f
JOIN finance_data.dim_period p ON f.period_id = p.period_id
JOIN finance_data.dim_standard_account sa ON f.account_code = sa.account_code
WHERE sa.account_name = '资产总额'
  AND f.value_column = '本月数'
GROUP BY p.period_id, p.period_name
ORDER BY p.period_id
```

### 5. 组织架构下钻查询 — 某节点下所有子单位的汇总

```sql
WITH RECURSIVE subtree AS (
    SELECT node_id, entity_report_id
    FROM finance_data.dim_organization_tree
    WHERE node_id = '<node_id>'

    UNION ALL

    SELECT t.node_id, t.entity_report_id
    FROM finance_data.dim_organization_tree t
    JOIN subtree s ON t.parent_id = s.node_id
)
SELECT
    SUM(CASE WHEN sa.account_name = '资产总额' AND f.value_column = '本月数'
        THEN f.value END) AS 汇总资产总额,
    COUNT(DISTINCT f.entity_report_id) AS 单位数
FROM finance_data.fact_finance_data f
JOIN subtree s ON f.entity_report_id = s.entity_report_id
JOIN finance_data.dim_standard_account sa ON f.account_code = sa.account_code
WHERE f.period_id = (SELECT MAX(period_id) FROM finance_data.fact_finance_data)
```

---

## 数据血缘 (Data Lineage)

### ETL 管道 → 目标表映射

| Pipeline | 入口 | 输出表 |
|---|---|---|
| `data_ingestion` / `data_ingestion_polars` | Excel 原始文件 → `parser.py` | 解析后的中间数据集 |
| `data_processing` | 中间数据 → `matcher.py` | 标准化指标数据集 |
| `data_warehouse` | 标准化数据 → `duckdb_data_warehouse.py` | `dim_period`, `dim_unit_report`, `dim_standard_account`, `dim_organization_tree`, `dim_caliber`, `dim_report_category`, `fact_finance_data` |
| `treasury_ingestion` | 资金 Excel 文件 → `treasury_parser.py` | 资金中间数据集 |
| `treasury_processing` | 资金中间数据 | 标准化资金数据 |
| `treasury_warehouse` | 标准化资金数据 | `dim_treasury_account`, `dim_treasury_account_type`, `fact_treasury_account_balance` |
| `geocoder.py` | 单位地址 → 高德地图 API（优先 BQ 缓存） | `dim_unit_geo` |

### 核心模块

| 模块 | 职责 |
|---|---|
| `parser.py` | Excel 财务快报解析（含章节检测、命名空间隔离） |
| `matcher.py` | 标准科目匹配（顶层科目名称匹配 + 层级消歧） |
| `tree_builder.py` | 集团组织树构建 |
| `treasury_parser.py` | 资金账户 Excel 解析 |
| `duckdb_data_warehouse.py` | DuckDB 星型模型构建 |
| `polars_optimizer.py` | Polars 并行处理优化 |
| `geocoder.py` | 高德地图地理编码 |

---

## Flask API 参考

| 端点 | 方法 | 查询表 | 说明 |
|---|---|---|---|
| `/api/periods` | GET | `dim_period`, `fact_treasury_account_balance` | 获取可用期间列表 |
| `/api/tree_periods` | GET | `dim_organization_tree` | 获取组织树可用期间 |
| `/api/report_categories` | GET | `dim_standard_account` | 获取报表类别 |
| `/api/tree` | GET | `dim_organization_tree` | 获取 jsTree 格式的组织树 |
| `/api/node_data` | GET | `fact_finance_data` + 多维度表 JOIN | 获取某节点的财务指标详情 |
| `/api/treasury_data` | GET | `fact_treasury_account_balance` + 维度表 JOIN | 获取某节点的资金账户详情 |
| `/api/time_options` | GET | `fact_finance_data`, `fact_treasury_account_balance` | 获取可选时间范围 |
| `/api/units_geo` | GET | `dim_unit_report` + `dim_unit_geo` + `fact_finance_data` | 获取单位地理坐标 + 资产汇总 |
| `/api/generate_report` | GET | — | 触发 Quarto 日报生成 |
| `/download_report/<filename>` | GET | — | 下载生成的报告文件 |

### Vizro 仪表板

内嵌于 Flask 应用 (`/vizro/`)，包含四个页面：

| 页面 | 内容 |
|---|---|
| 穿透监控大屏 | 资产负债表散点图 (货币资金 vs 资产总额) + 账户余额分布 |
| 关系分析 | 关联交易分析 (待开发) |
| 概览 | 全局概览 (待开发) |
| 地理分布 | 中国地图 + 单位资产规模气泡 |

---

## 查询注意事项

1. **表名必须带 schema 前缀**: `finance_data.fact_finance_data`
2. **value_column 过滤**: 查月度数据需 `WHERE value_column='本月数'`，累计数据用 `'本年累计'`
3. **NULL / 零值**: 很多值为 0 的记录，过滤可用 `WHERE value != 0`
4. **组织树查询**: 用 `v_organization_hierarchy` 视图可直接获得完整层级
5. **期间格式**: `period_id` 格式为 `YYYY-MM-DD`（月末日期）
6. **同表多 code 歧义**: Excel 中 code `03` 在资产负债表中是"货币资金"，在利润表中是"营业利润"——ETL 通过章节命名空间隔离处理
7. **标准库 vs Excel code 独立**: `standard_accounts.json` 的编码体系与 Excel 报表行号无直接对应关系，匹配通过**科目名称**实现

---

## 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-04-24 | 初始版本：财务快报 + 资金账户双重事实表，组织架构树，Vizro 仪表板 |

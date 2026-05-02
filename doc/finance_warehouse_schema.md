# finance_warehouse.duckdb — Schema 参考

**数据库**: `data/warehouse/finance_warehouse.duckdb` (2.0 GB)
**Schema**: `finance_data`
**数据期间**: 2026-02, 2026-03 (财务报表), 2026-04 (资金账户)
**ETL 时间**: 2026-04-24

---

## 维度表 (Dimension)

### dim_period — 会计期间 (2 rows)
| 列 | 类型 | 说明 |
|---|---|---|
| period_id | VARCHAR | 主键，如 `2026-02-28` |
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
```

### v_organization_hierarchy — 组织架构层级
基于 dim_organization_tree 的递归 CTE，展开完整的组织层级。
| level | 说明 |
|---|---|
| 0 | 根节点 |
| 1,2,3... | 子级深度 |

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
```

## 查询注意事项

1. **表名必须带 schema 前缀**: `finance_data.fact_finance_data`
2. **value_column 过滤**: 查月度数据需 WHERE value_column='本月数'，累计数据用 '本年累计'
3. **NULL values**: 很多值为0的记录，过滤可用 `WHERE value != 0`
4. **组织树查询**: 用 `v_organization_hierarchy` 视图可直接获得完整层级
5. **期间格式**: period_id 格式为 `YYYY-MM-DD`（月末日期）

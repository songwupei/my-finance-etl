---
name: finance-query
description: Query the DuckDB finance data warehouse (司库/财务数据库) with proper schema awareness
triggers:
  - finance
  - 财务
  - duckdb
  - 司库
  - 资金
  - 科目
  - 报表
  - query warehouse
  - 查询数据库
argument-hint: "<natural language question about finance data>"
---

# Finance Query Skill

## Purpose

Query the DuckDB finance data warehouse at `data/warehouse/finance_warehouse.duckdb` (2.0 GB). The schema is in the `finance_data` schema — all tables must be prefixed with `finance_data.`.

Full schema reference: `data/warehouse/finance_warehouse_schema.md`

## When to Activate

When the user asks questions about:
- 财务报表数据 (资产负债表/利润表/现金流量表)
- 资金账户、银行账户、账户余额
- 组织架构中的单位/子公司数据
- 科目、会计期间、报表口径
- Any analysis requiring DuckDB queries on this specific database

## Workflow

### Step 1: Understand the question

Read the user's question and identify which tables are needed.

### Step 2: Read the schema reference (if needed)

If unsure about column names or relationships, read:
```
data/warehouse/finance_warehouse_schema.md
```

### Step 3: Build and execute the SQL query

Always use the `duckdb` CLI. The database path is:
```
data/warehouse/finance_warehouse.duckdb
```

**Critical rules:**
- ALL table references MUST use `finance_data.` prefix (e.g., `finance_data.fact_finance_data`)
- Use `-json` flag for structured output when the result is large
- Use `-csv` flag for counts and simple values
- Default to `LIMIT 100` for exploratory queries, remove when user wants full data

**Example command format:**
```bash
duckdb data/warehouse/finance_warehouse.duckdb -c "SELECT ... FROM finance_data.fact_finance_data ..."
```

### Step 4: Present results

Translate results back into the user's business language. Show both the SQL and a readable summary.

## Schema Quick Reference

### Key tables

| Table | Rows | Purpose |
|---|---|---|
| fact_finance_data | 1,234,917 | Core financial data (资产/负债/利润/现金流) |
| fact_treasury_account_balance | 10,533 | Bank account balances |
| dim_standard_account | 124 | Standard account hierarchy (科目树) |
| dim_period | 2 | Accounting periods (2026-02, 2026-03) |
| dim_report_category | 3 | Report types (资产负债表/利润表/现金流量表) |
| dim_caliber | 1 | Report caliber (合并口径) |
| dim_unit_report | 2,830 | Reporting units |
| dim_organization_tree | 2,830 | Org hierarchy (parent-child) |
| dim_treasury_account | 27,085 | Bank accounts master data |
| dim_treasury_account_type | 34 | Account type classification |
| v_monthly_summary | VIEW | Pre-aggregated monthly summary |
| v_organization_hierarchy | VIEW | Recursive org tree with levels |

### Key JOIN patterns

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

### Critical query patterns

1. **value_column filtering** (fact_finance_data):
   - `本月数` — current month value
   - `本年累计` — year-to-date cumulative
   - `上年同期` — same period last year

2. **category_id mapping**:
   - `1` = 资产负债表 (Balance Sheet)
   - `2` = 利润表 (Income Statement)
   - `3` = 现金流量表 (Cash Flow)

3. **date range**: Data is from 2026-02, 2026-03 for financial reports; 2026-04 for treasury accounts

4. **NULL/zero values**: Many records have value=0, filter with `WHERE value != 0` for meaningful data

5. **period format**: `period_id` is `YYYY-MM-DD` (month-end dates, e.g. `2026-02-28`)

6. **Organization tree**: Use `v_organization_hierarchy` view for recursive parent-child queries with `level` column (0=root)

## Examples

### Query 1: 某单位某月资产负债表
```bash
duckdb data/warehouse/finance_warehouse.duckdb -c "
SELECT sa.account_name, f.value, f.value_column
FROM finance_data.fact_finance_data f
JOIN finance_data.dim_standard_account sa ON f.account_code = sa.account_code
JOIN finance_data.dim_unit_report u ON f.entity_report_id = u.entity_report_id
WHERE u.unit_name LIKE '%安徽金星%'
  AND f.period_id = '2026-02-28'
  AND f.category_id = '1'
  AND f.value_column = '本月数'
  AND f.value != 0
ORDER BY sa.account_code;
"
```

### Query 2: 各子公司资产总额排名
```bash
duckdb data/warehouse/finance_warehouse.duckdb -c "
SELECT u.unit_name, f.value AS 资产总额
FROM finance_data.fact_finance_data f
JOIN finance_data.dim_unit_report u ON f.entity_report_id = u.entity_report_id
WHERE f.account_code = '01'
  AND f.period_id = '2026-03-31'
  AND f.value_column = '本月数'
  AND f.value != 0
ORDER BY f.value DESC
LIMIT 20;
"
```

### Query 3: 资金账户余额查询
```bash
duckdb data/warehouse/finance_warehouse.duckdb -c "
SELECT ta.account_name, ta.financial_institution, ta.currency,
       b.balance_amount, b.balance_date
FROM finance_data.fact_treasury_account_balance b
JOIN finance_data.dim_treasury_account ta ON b.account_id = ta.account_id
WHERE ta.unit_name LIKE '%安徽金星%'
ORDER BY b.balance_amount DESC;
"
```

### Query 4: 月度汇总
```bash
duckdb data/warehouse/finance_warehouse.duckdb -c "
SELECT * FROM finance_data.v_monthly_summary
WHERE unit_name LIKE '%安徽金星%'
ORDER BY total_value DESC;
"
```

## Notes

- The database is ~2GB, queries typically complete in seconds
- Always use `finance_data.` schema prefix — DuckDB does not default to it
- The `dim_standard_account.standard_path` column has human-readable paths like `资产总额 > 流动资产合计 > 货币资金`
- `dim_organization_tree` uses `parent_id = '#'` to mark root nodes
- The `suffix` column in org tables: `0` = entity itself (本部), other numbers = subsidiaries

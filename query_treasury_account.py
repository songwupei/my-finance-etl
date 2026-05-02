"""查询指定节点和日期的司库账户数据"""
import duckdb
import pandas as pd
import sys

DB_PATH = "data/warehouse/finance_warehouse.duckdb"


def query_account_data(node_name_pattern: str, period: str):
    conn = duckdb.connect(DB_PATH)

    # 1. 查组织树获取 entity_report_id
    tree = conn.execute("""
        SELECT node_id, entity_report_id FROM finance_data.dim_organization_tree
        WHERE node_name LIKE ? LIMIT 1
    """, [f"%{node_name_pattern}%"]).fetchone()

    if not tree:
        print(f"未找到匹配 '{node_name_pattern}' 的节点")
        conn.close()
        return

    node_id, entity_id = tree
    print(f"节点: {node_id}")
    print(f"entity_report_id: {entity_id}\n")

    # 2. 查询账户余额
    df = conn.execute("""
        SELECT
            ta.account_number        AS "账户编号",
            ta.account_name          AS "账户名称",
            ta.opening_institution   AS "开户银行",
            tat.type_label           AS "账户类型",
            ta.currency              AS "币种",
            fb.balance_amount        AS "期末余额",
            fb.converted_amount      AS "可用余额",
            fb.balance_date          AS "余额日期",
            ta.is_partner_bank       AS "是否合作银行",
            ta.is_overseas           AS "是否境外账户"
        FROM finance_data.fact_treasury_account_balance fb
        JOIN finance_data.dim_treasury_account ta ON fb.account_id = ta.account_id
        LEFT JOIN finance_data.dim_treasury_account_type tat ON ta.type_id = tat.type_id
        WHERE fb.entity_report_id = ? AND fb.period = ?
        ORDER BY ta.opening_institution, ta.account_number
    """, [entity_id, period]).fetchdf()

    pd.set_option('display.max_columns', 20)
    pd.set_option('display.width', 300)
    pd.set_option('display.max_colwidth', 40)
    pd.set_option('display.float_format', '{:,.2f}'.format)

    print(f"共 {len(df)} 条记录")
    print(df.to_string(index=False))

    conn.close()
    return df


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "北方华锦化学工业集团有限公司（本部）_0"
    period = sys.argv[2] if len(sys.argv) > 2 else "2026-04-24"
    query_account_data(name, period)

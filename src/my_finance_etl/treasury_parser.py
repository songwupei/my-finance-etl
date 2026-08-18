"""司库数据 Excel 列映射器 — 对已加载的 DataFrame 做列名标准化。"""
import polars as pl
from typing import Dict


ACCOUNT_INFO_COLUMNS = {
    '单位编号': 'unit_id',
    '单位名称': 'unit_name',
    '开户单位编码': 'org_code',
    '所属子集团名称': 'sub_group_name',
    '银行账号': 'account_number',
    '账户名称': 'account_name',
    '金融机构': 'financial_institution',
    '开户机构': 'opening_institution',
    '开户机构联行号': 'institution_code',
    '账户状态': 'account_status',
    '国家/地区': 'country_region',
    '账户性质': 'account_nature',
    '是否境外账户': 'is_overseas',
    '银行城市': 'bank_city',
    '开户日期': 'open_date',
    '销户日期': 'close_date',
    '是否合作银行': 'is_partner_bank',
    '授权通道': 'auth_channel',
    '授权日期': 'auth_date',
    '是否授权归集': 'is_auth_collection',
    '是否授权支付': 'is_auth_payment',
    '账户类型': 'account_type',
    '币种': 'currency',
    '管理限额（万元）': 'management_limit_wan',
    '是否限额': 'is_limited',
    '批文文号': 'approval_doc_no',
    '账户用途': 'account_usage',
    '是否可视': 'is_visible',
    '是否系统结算': 'is_system_settlement',
}

ACCOUNT_BALANCE_COLUMNS = {
    '单位名称': 'unit_name',
    '所属子集团名称': 'sub_group_name',
    '银行账号': 'account_number',
    '账户名称': 'account_name',
    '金融机构': 'financial_institution',
    '开户机构': 'opening_institution',
    '余额': 'balance',
    '币种': 'currency',
    '折算金额': 'converted_amount',
    '余额时间': 'balance_date',
    '是否合作银行': 'is_partner_bank',
    '是否境外账户': 'is_overseas',
    '账户性质': 'account_nature',
}

COLUMN_MAP_REGISTRY: Dict[str, dict] = {
    "account_info": ACCOUNT_INFO_COLUMNS,
    "account_balance": ACCOUNT_BALANCE_COLUMNS,
}

# 余额类列统一为 String，避免历史缓存(Float64)与当前 dtype=str 解析(String)不一致
BALANCE_TEXT_COLUMNS = ("balance", "converted_amount")


def normalize_treasury_schema(df: pl.DataFrame, file_type: str) -> pl.DataFrame:
    """统一同一业务类型的列类型（余额类列统一为 String）。"""
    if file_type != "account_balance":
        return df
    for col in BALANCE_TEXT_COLUMNS:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.String))
    return df


def transform_treasury_data(df: pl.DataFrame, file_type: str) -> pl.DataFrame:
    """对已加载的 DataFrame 做列名标准化和基本清洗。

    Args:
        df: 从 ExcelDataset.load() 返回的 DataFrame（已含 header）
        file_type: "account_info" 或 "account_balance"

    Returns:
        列名标准化后的 DataFrame
    """
    column_map = COLUMN_MAP_REGISTRY.get(file_type, {})
    if not column_map:
        raise ValueError(f"Unknown treasury file_type: {file_type}")

    # 只保留映射中存在的列，并重命名
    existing = [(k, v) for k, v in column_map.items() if k in df.columns]
    df = df.select([pl.col(k).alias(v) for k, v in existing])

    # 删除全空行和重复标题行
    df = df.filter(~pl.all_horizontal(pl.all().is_null()))

    # 统一列类型，保证不同来源（新解析/旧缓存）能纵向合并
    return normalize_treasury_schema(df, file_type)

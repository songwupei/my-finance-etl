"""Vizro dashboard module-level data loading.

All SQL queries and DataFrame construction happens at import time,
as required by Vizro's @capture("graph") pattern (closure over pre-built DataFrames).
"""

import duckdb
import numpy as np
import pandas as pd
import polars as pl
import yaml

from ..config import _get_db_path, _proj_dir

_vizro_db = _get_db_path()
_vizro_con = duckdb.connect(_vizro_db, read_only=True)

# ============================================================
# 图1: 资产负债气泡散点 + 图2: 杠杆率 vs 账户规模
# ============================================================

_vizro_df1 = _vizro_con.execute("""
    WITH asset_liability AS (
        SELECT
            f.entity_report_id,
            f.period_id AS 期间,
            COALESCE(ot.node_name, f.entity_report_id) AS 单位名称,
            SUM(CASE WHEN sa.account_code = '01' THEN f.value END) AS 资产总额,
            SUM(CASE WHEN sa.account_code = '02' THEN f.value END) AS 负债总额
        FROM finance_data.fact_finance_data f
        JOIN finance_data.dim_standard_account sa ON f.account_code = sa.account_code
        JOIN finance_data.dim_report_category rc ON f.category_id = rc.category_id
        LEFT JOIN finance_data.dim_organization_tree ot
            ON f.entity_report_id = ot.entity_report_id AND ot.period = f.period_id
        WHERE rc.category_name = '资产负债表'
          AND sa.account_code IN ('01', '02')
          AND f.value_column = '本年累计'
        GROUP BY f.entity_report_id, 期间, ot.node_name
        HAVING "资产总额" > 0 AND "负债总额" > 0
    ),
    account_count AS (
        SELECT entity_report_id, COUNT(DISTINCT account_id) AS 账户数
        FROM finance_data.dim_treasury_account
        WHERE account_status = '存续'
        GROUP BY entity_report_id
    )
    SELECT
        al.*,
        COALESCE(ac.账户数, 0) AS 账户数,
        al.负债总额 / NULLIF(al.资产总额, 0) AS 资产负债率
    FROM asset_liability al
    LEFT JOIN account_count ac ON al.entity_report_id = ac.entity_report_id
""").fetchdf()

_exclude_ids = _vizro_con.execute("""
    SELECT DISTINCT entity_report_id FROM finance_data.dim_unit_report WHERE suffix IN ('1', '9')
""").fetchdf()
if not _exclude_ids.empty:
    _exclude_set = set(_exclude_ids.iloc[:, 0])
    _vizro_df1 = _vizro_df1[~_vizro_df1["entity_report_id"].isin(_exclude_set)]

_vizro_df1 = _vizro_df1.sort_values("期间").groupby("entity_report_id").last().reset_index()

_vizro_df1["log10_资产总额"] = np.log10(_vizro_df1["资产总额"])
_vizro_df1["log10_负债总额"] = np.log10(_vizro_df1["负债总额"])
_vizro_df1["log10_账户数"] = np.log10(_vizro_df1["账户数"].clip(lower=1))
_vizro_df1["资产总额_万"] = _vizro_df1["资产总额"]
_vizro_df1["负债总额_万"] = _vizro_df1["负债总额"]

# ============================================================
# 图3: 中国地图 — 单位地理分布 + 资产规模
# ============================================================

_geo_parquet = _proj_dir / "data/03_primary/dim_unit_geo.parquet"
try:
    if _geo_parquet.exists():
        _sync_conn = duckdb.connect(_vizro_db)
        try:
            geo_df = pl.read_parquet(str(_geo_parquet))
            if not geo_df.is_empty():
                _sync_conn.register("_geo", geo_df.to_pandas())
                _sync_conn.execute(
                    "CREATE OR REPLACE TABLE IF NOT EXISTS finance_data.dim_unit_geo AS SELECT * FROM _geo"
                )
                print(f"[flask] Synced {geo_df.height} geo rows to DuckDB from parquet")
        finally:
            _sync_conn.close()
except Exception as e:
    print(f"[flask] Geo sync failed: {e}")

_vizro_geo_data = pl.DataFrame()
try:
    _vizro_geo_data = _vizro_con.execute("""
        WITH latest_unit AS (
            SELECT DISTINCT ON (entity_report_id) *
            FROM finance_data.dim_unit_report
            ORDER BY entity_report_id, period DESC
        )
        SELECT
            u.unit_name,
            u.province,
            u.city,
            u.enterprise_address,
            g.longitude,
            g.latitude,
            COALESCE(SUM(CASE WHEN f.value_column = '本年累计' AND f.account_code = '01'
                         THEN f.value END), 0) AS total_assets,
            COALESCE(SUM(CASE WHEN f.value_column = '本年累计' AND f.account_code = '54'
                         THEN f.value END), 0) AS total_revenue
        FROM latest_unit u
        JOIN finance_data.dim_unit_geo g
            ON u.entity_report_id = g.entity_report_id
        LEFT JOIN finance_data.fact_finance_data f
            ON u.entity_report_id = f.entity_report_id
           AND f.period_id = (SELECT MAX(period_id) FROM finance_data.fact_finance_data)
        WHERE g.longitude IS NOT NULL AND u.suffix NOT IN ('1', '9')
        GROUP BY u.entity_report_id, u.unit_name, u.province, u.city,
                 u.enterprise_address, g.longitude, g.latitude
    """).fetchdf()
except Exception:
    pass

# ============================================================
# 账户地图数据
# ============================================================

_bank_map_account_data = pl.DataFrame()
try:
    _bank_map_account_data = _vizro_con.execute("""
        SELECT
            ta.institution_code,
            ta.sub_group_name,
            ta.account_name,
            COALESCE(NULLIF(ta.financial_institution, ''), '未知银行') AS financial_institution,
            COALESCE(NULLIF(ta.bank_city, ''), '未知城市') AS bank_city,
            fb.balance_amount,
            bb.opening_institution AS branch_name,
            bb.longitude,
            bb.latitude,
            bb.formatted_address
        FROM finance_data.fact_treasury_account_balance fb
        JOIN finance_data.dim_treasury_account ta ON fb.account_id = ta.account_id
        JOIN finance_data.dim_bank_branch bb ON ta.institution_code = bb.institution_code
        WHERE fb.period = (SELECT MAX(period) FROM finance_data.fact_treasury_account_balance)
          AND ta.account_status = '存续'
          AND fb.balance_amount > 0
          AND bb.longitude IS NOT NULL
          AND bb.financial_institution != '财务公司'
    """).fetchdf()
except Exception:
    pass

# 城市→省份映射 (覆盖34个省级行政区的188个城市)
_CITY_PROVINCE = {
    "北京市": "北京市", "上海市": "上海市", "天津市": "天津市", "重庆市": "重庆市",
    "石家庄市": "河北省", "唐山市": "河北省", "秦皇岛市": "河北省", "邯郸市": "河北省", "邢台市": "河北省", "保定市": "河北省", "张家口市": "河北省", "承德市": "河北省", "沧州市": "河北省", "廊坊市": "河北省", "衡水市": "河北省", "雄安新区": "河北省",
    "太原市": "山西省", "大同市": "山西省", "阳泉市": "山西省", "长治市": "山西省", "晋城市": "山西省", "朔州市": "山西省", "晋中市": "山西省", "运城市": "山西省", "临汾市": "山西省", "吕梁市": "山西省",
    "呼和浩特市": "内蒙古自治区", "包头市": "内蒙古自治区", "乌海市": "内蒙古自治区", "赤峰市": "内蒙古自治区", "鄂尔多斯市": "内蒙古自治区", "巴彦淖尔市": "内蒙古自治区", "阿拉善盟": "内蒙古自治区", "锡林郭勒盟": "内蒙古自治区",
    "沈阳市": "辽宁省", "大连市": "辽宁省", "鞍山市": "辽宁省", "抚顺市": "辽宁省", "锦州市": "辽宁省", "营口市": "辽宁省", "辽阳市": "辽宁省", "盘锦市": "辽宁省", "朝阳市": "辽宁省", "葫芦岛市": "辽宁省",
    "长春市": "吉林省", "吉林市": "吉林省", "通化市": "吉林省", "白城市": "吉林省",
    "哈尔滨市": "黑龙江省", "齐齐哈尔市": "黑龙江省", "鸡西市": "黑龙江省", "鹤岗市": "黑龙江省", "大庆市": "黑龙江省", "牡丹江市": "黑龙江省", "绥化市": "黑龙江省",
    "南京市": "江苏省", "无锡市": "江苏省", "徐州市": "江苏省", "苏州市": "江苏省", "南通市": "江苏省", "连云港市": "江苏省", "淮安市": "江苏省", "盐城市": "江苏省", "扬州市": "江苏省", "泰州市": "江苏省",
    "杭州市": "浙江省", "宁波市": "浙江省", "嘉兴市": "浙江省", "金华市": "浙江省", "台州市": "浙江省",
    "合肥市": "安徽省", "芜湖市": "安徽省", "蚌埠市": "安徽省", "马鞍山市": "安徽省", "安庆市": "安徽省", "滁州市": "安徽省", "六安市": "安徽省", "池州市": "安徽省", "宣城市": "安徽省", "巢湖市": "安徽省",
    "福州市": "福建省", "厦门市": "福建省", "泉州市": "福建省", "漳州市": "福建省", "宁德市": "福建省",
    "南昌市": "江西省", "九江市": "江西省", "赣州市": "江西省", "吉安市": "江西省", "宜春市": "江西省",
    "济南市": "山东省", "青岛市": "山东省", "淄博市": "山东省", "烟台市": "山东省", "潍坊市": "山东省", "泰安市": "山东省", "威海市": "山东省",
    "郑州市": "河南省", "开封市": "河南省", "洛阳市": "河南省", "平顶山市": "河南省", "新乡市": "河南省", "焦作市": "河南省", "三门峡市": "河南省", "南阳市": "河南省", "信阳市": "河南省", "驻马店市": "河南省",
    "武汉市": "湖北省", "黄石市": "湖北省", "十堰市": "湖北省", "宜昌市": "湖北省", "襄阳市": "湖北省", "襄樊市": "湖北省", "孝感市": "湖北省", "黄冈市": "湖北省", "咸宁市": "湖北省", "随州市": "湖北省", "潜江市": "湖北省",
    "长沙市": "湖南省", "湘潭市": "湖南省", "衡阳市": "湖南省", "常德市": "湖南省", "怀化市": "湖南省",
    "广州市": "广东省", "深圳市": "广东省", "珠海市": "广东省", "佛山市": "广东省", "湛江市": "广东省", "惠州市": "广东省", "东莞市": "广东省", "揭阳市": "广东省",
    "南宁市": "广西壮族自治区", "柳州市": "广西壮族自治区", "桂林市": "广西壮族自治区", "梧州市": "广西壮族自治区", "防城港市": "广西壮族自治区", "钦州市": "广西壮族自治区", "贵港市": "广西壮族自治区", "玉林市": "广西壮族自治区", "百色市": "广西壮族自治区", "贺州市": "广西壮族自治区", "河池市": "广西壮族自治区", "来宾市": "广西壮族自治区", "崇左市": "广西壮族自治区",
    "海口市": "海南省", "三亚市": "海南省",
    "成都市": "四川省", "绵阳市": "四川省", "泸州市": "四川省", "德阳市": "四川省", "内江市": "四川省", "乐山市": "四川省", "南充市": "四川省", "宜宾市": "四川省", "雅安市": "四川省", "凉山彝族自治州": "四川省", "甘孜藏族自治州": "四川省",
    "贵阳市": "贵州省", "安顺市": "贵州省", "黔南布依族苗族自治州": "贵州省",
    "昆明市": "云南省", "曲靖市": "云南省", "玉溪市": "云南省", "普洱市": "云南省", "迪庆藏族自治州": "云南省",
    "拉萨市": "西藏自治区", "林芝市": "西藏自治区", "林芝地区": "西藏自治区", "阿里地区": "西藏自治区",
    "西安市": "陕西省", "铜川市": "陕西省", "宝鸡市": "陕西省", "咸阳市": "陕西省", "渭南市": "陕西省", "延安市": "陕西省", "榆林市": "陕西省", "安康市": "陕西省", "商洛市": "陕西省",
    "兰州市": "甘肃省", "白银市": "甘肃省", "酒泉市": "甘肃省",
    "西宁市": "青海省", "海西蒙古族藏族自治州": "青海省",
    "银川市": "宁夏回族自治区", "固原市": "宁夏回族自治区",
    "乌鲁木齐市": "新疆维吾尔自治区", "克拉玛依市": "新疆维吾尔自治区", "吐鲁番地区": "新疆维吾尔自治区", "哈密地区": "新疆维吾尔自治区", "阿克苏地区": "新疆维吾尔自治区", "喀什地区": "新疆维吾尔自治区", "和田地区": "新疆维吾尔自治区", "塔城地区": "新疆维吾尔自治区", "克孜勒苏柯尔克孜自治州": "新疆维吾尔自治区", "昌吉回族自治州": "新疆维吾尔自治区", "巴音郭楞蒙古自治州": "新疆维吾尔自治区", "伊犁哈萨克自治州": "新疆维吾尔自治区",
}
if _bank_map_account_data.shape[0] > 0:
    _bank_map_account_data["province"] = _bank_map_account_data["bank_city"].map(_CITY_PROVINCE).fillna("其他")

_account_detail_df = None
if _bank_map_account_data.shape[0] > 0:
    _account_detail_df = _bank_map_account_data[[
        "sub_group_name", "account_name", "financial_institution",
        "bank_city", "province", "branch_name", "balance_amount",
    ]].sort_values("balance_amount", ascending=False)

_account_detail_column_defs = [
    {"field": "sub_group_name", "headerName": "子集团"},
    {"field": "account_name", "headerName": "账户户名"},
    {"field": "financial_institution", "headerName": "所属银行"},
    {"field": "bank_city", "headerName": "城市"},
    {"field": "province", "headerName": "省份"},
    {"field": "balance_amount", "headerName": "余额"},
    {"field": "branch_name", "headerName": "开户网点"},
]

# ============================================================
# 余额统计分析数据
# ============================================================

_balance_base_data = pl.DataFrame()
try:
    _balance_base_data = _vizro_con.execute("""
        SELECT
            ta.account_id,
            ta.sub_group_name,
            COALESCE(NULLIF(ta.financial_institution, ''), '未知银行') AS financial_institution,
            COALESCE(NULLIF(ta.bank_city, ''), '未知城市') AS bank_city,
            ta.account_usage,
            ta.is_partner_bank,
            ta.is_overseas,
            fb.balance_amount
        FROM finance_data.fact_treasury_account_balance fb
        JOIN finance_data.dim_treasury_account ta ON fb.account_id = ta.account_id
        WHERE fb.period = (SELECT MAX(period) FROM finance_data.fact_treasury_account_balance)
          AND ta.account_status = '存续'
          AND fb.balance_amount > 0
    """).fetchdf()
    _balance_base_data["log10_balance"] = np.log10(_balance_base_data["balance_amount"].clip(lower=1))
except Exception:
    pass

# 预聚合: 子集团维度
_balance_by_subgroup = None
if _balance_base_data.shape[0] > 0:
    _balance_by_subgroup = _balance_base_data.groupby("sub_group_name").agg(
        total_balance=("balance_amount", "sum"),
        account_count=("account_id", "nunique"),
        avg_balance=("balance_amount", "mean"),
        median_balance=("balance_amount", "median"),
    ).reset_index().sort_values("total_balance", ascending=False)

# 预聚合: 银行维度
_balance_by_bank = None
if _balance_base_data.shape[0] > 0:
    _balance_by_bank = _balance_base_data.groupby("financial_institution").agg(
        total_balance=("balance_amount", "sum"),
        account_count=("account_id", "nunique"),
        avg_balance=("balance_amount", "mean"),
    ).reset_index().sort_values("total_balance", ascending=False)

# 预聚合: 城市维度
_balance_by_city = None
if _balance_base_data.shape[0] > 0:
    _balance_by_city = _balance_base_data.groupby("bank_city").agg(
        total_balance=("balance_amount", "sum"),
        account_count=("account_id", "nunique"),
    ).reset_index().sort_values("total_balance", ascending=False)

# 余额层级分桶
_tier_data = None
if _balance_base_data.shape[0] > 0:
    _bins = [0, 1e5, 1e6, 1e7, 1e8, float("inf")]
    _labels = ["<10万", "10万-100万", "100万-1000万", "1000万-1亿", ">1亿"]
    _balance_base_data["tier"] = pd.cut(_balance_base_data["balance_amount"], bins=_bins, labels=_labels, right=False)
    _tier_data = _balance_base_data.groupby("tier", observed=False).agg(
        total_balance=("balance_amount", "sum"),
        account_count=("account_id", "nunique"),
    ).reset_index()

# Top N 快捷引用
_top10_sg = _balance_by_subgroup.head(10) if _balance_by_subgroup is not None else None
_top20_sg = _balance_by_subgroup.head(20) if _balance_by_subgroup is not None else None

# 散点: 账户数 vs 平均余额 (交叉维度)
_cross_data = None
if _balance_by_subgroup is not None:
    _cross_data = _balance_by_subgroup.copy()
    _cross_data["log10_avg_balance"] = np.log10(_cross_data["avg_balance"].clip(lower=1))
    _cross_data["log10_account_count"] = np.log10(_cross_data["account_count"].clip(lower=1))
    _cross_data["size_scaled"] = np.log10(_cross_data["total_balance"].clip(lower=1)) * 4

# 箱线图数据
_box_data = None
_top8_banks = None
if _balance_by_bank is not None:
    _top8_banks = _balance_by_bank.head(8)["financial_institution"].tolist()
    _box_data = _balance_base_data[_balance_base_data["financial_institution"].isin(_top8_banks)]

# 银行 x 账户用途交叉
_bank_usage_pivot = None
if _balance_base_data.shape[0] > 0:
    _bank_usage_data = _balance_base_data.groupby(["financial_institution", "account_usage"]).agg(
        total_balance=("balance_amount", "sum"),
    ).reset_index()
    _bank_usage_pivot = _bank_usage_data.pivot(index="financial_institution", columns="account_usage", values="total_balance").fillna(0)
    _bank_usage_pivot = _bank_usage_pivot.loc[_bank_usage_pivot.sum(axis=1).sort_values(ascending=False).index].head(10)

# 银行维度数据 (剔除财务公司)
_bank_data_for_chart = None
if _balance_by_bank is not None:
    _bank_data_for_chart = _balance_by_bank[_balance_by_bank["financial_institution"] != "财务公司"]

# 城市维度数据 (剔除未知)
_city_known = None
if _balance_by_city is not None:
    _city_known = _balance_by_city[_balance_by_city["bank_city"] != "未知城市"]
_top20_city = _city_known.head(20) if _city_known is not None else None

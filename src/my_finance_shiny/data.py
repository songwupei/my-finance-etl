"""Shiny dashboard data loading — DuckDB SQL → Polars DataFrames.

Pre-loads at import time; each Shiny session clones via @reactive.calc.
"""
import polars as pl

from ..my_finance_shared.database import connect_with_retry, sync_geo_to_duckdb
from .config import DB_PATH

# Geo parquet sync must happen BEFORE opening the read_only connection
_sync_conn = connect_with_retry(read_only=False)
try:
    sync_geo_to_duckdb(_sync_conn)
finally:
    _sync_conn.close()

_vizro_con = connect_with_retry(read_only=True)

# ============================================================
# Asset-liability bubble + leverage scatter data
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
""").pl()

_exclude_ids = _vizro_con.execute("""
    SELECT DISTINCT entity_report_id FROM finance_data.dim_unit_report WHERE suffix IN ('1', '9')
""").pl()

if _exclude_ids.height > 0:
    _exclude_list = _exclude_ids["entity_report_id"].to_list()
    _vizro_df1 = _vizro_df1.filter(~pl.col("entity_report_id").is_in(_exclude_list))

_vizro_df1 = _vizro_df1.sort("期间").group_by("entity_report_id").last()

_vizro_df1 = _vizro_df1.with_columns(
    pl.col("资产总额").log10().alias("log10_资产总额"),
    pl.col("负债总额").log10().alias("log10_负债总额"),
    pl.col("账户数").clip(1, None).log10().alias("log10_账户数"),
    pl.col("资产总额").alias("资产总额_万"),
    pl.col("负债总额").alias("负债总额_万"),
)

# ============================================================
# China geo map data — unit geographic distribution
# ============================================================

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
    """).pl()
except Exception:
    pass

# ============================================================
# Bank account map data
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
    """).pl()
except Exception:
    pass

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

if _bank_map_account_data.height > 0:
    _bank_map_account_data = _bank_map_account_data.with_columns(
        pl.col("bank_city").replace_strict(_CITY_PROVINCE, default="其他").alias("province")
    )

_account_detail_df = pl.DataFrame()
if _bank_map_account_data.height > 0:
    _account_detail_df = (
        _bank_map_account_data
        .select(["sub_group_name", "account_name", "financial_institution",
                 "bank_city", "province", "branch_name", "balance_amount"])
        .sort("balance_amount", descending=True)
    )

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
# Balance analysis data
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
    """).pl()
    _balance_base_data = _balance_base_data.with_columns(
        pl.col("balance_amount").clip(1, None).log10().alias("log10_balance")
    )
except Exception:
    pass

# Pre-aggregation: by subgroup
_balance_by_subgroup = pl.DataFrame()
if _balance_base_data.height > 0:
    _balance_by_subgroup = (
        _balance_base_data
        .group_by("sub_group_name")
        .agg(
            pl.col("balance_amount").sum().alias("total_balance"),
            pl.col("account_id").n_unique().alias("account_count"),
            pl.col("balance_amount").mean().alias("avg_balance"),
            pl.col("balance_amount").median().alias("median_balance"),
        )
        .sort("total_balance", descending=True)
    )

# Pre-aggregation: by bank
_balance_by_bank = pl.DataFrame()
if _balance_base_data.height > 0:
    _balance_by_bank = (
        _balance_base_data
        .group_by("financial_institution")
        .agg(
            pl.col("balance_amount").sum().alias("total_balance"),
            pl.col("account_id").n_unique().alias("account_count"),
            pl.col("balance_amount").mean().alias("avg_balance"),
        )
        .sort("total_balance", descending=True)
    )

# Pre-aggregation: by city
_balance_by_city = pl.DataFrame()
if _balance_base_data.height > 0:
    _balance_by_city = (
        _balance_base_data
        .group_by("bank_city")
        .agg(
            pl.col("balance_amount").sum().alias("total_balance"),
            pl.col("account_id").n_unique().alias("account_count"),
        )
        .sort("total_balance", descending=True)
    )

# Balance tier bucketing
_tier_data = pl.DataFrame()
if _balance_base_data.height > 0:
    _breaks = [1e5, 1e6, 1e7, 1e8]
    _labels = ["<10万", "10万-100万", "100万-1000万", "1000万-1亿", ">1亿"]
    _tier_data = (
        _balance_base_data
        .with_columns(
            pl.col("balance_amount").cut(breaks=_breaks, labels=_labels, left_closed=True).alias("tier")
        )
        .group_by("tier")
        .agg(
            pl.col("balance_amount").sum().alias("total_balance"),
            pl.col("account_id").n_unique().alias("account_count"),
        )
    )

# Top N shortcuts
_top10_sg = _balance_by_subgroup.head(10) if _balance_by_subgroup.height > 0 else pl.DataFrame()
_top20_sg = _balance_by_subgroup.head(20) if _balance_by_subgroup.height > 0 else pl.DataFrame()

# Cross-dimension scatter data
_cross_data = pl.DataFrame()
if _balance_by_subgroup.height > 0:
    _cross_data = _balance_by_subgroup.with_columns(
        pl.col("avg_balance").clip(1, None).log10().alias("log10_avg_balance"),
        pl.col("account_count").clip(1, None).log10().alias("log10_account_count"),
        (pl.col("total_balance").clip(1, None).log10() * 4).alias("size_scaled"),
    )

# Box plot data
_box_data = pl.DataFrame()
_top8_banks = []
if _balance_by_bank.height > 0:
    _top8_banks = _balance_by_bank.head(8)["financial_institution"].to_list()
    _box_data = _balance_base_data.filter(pl.col("financial_institution").is_in(_top8_banks))

# Bank x account_usage pivot
_bank_usage_pivot = pl.DataFrame()
if _balance_base_data.height > 0:
    _bank_usage_data = (
        _balance_base_data
        .group_by(["financial_institution", "account_usage"])
        .agg(pl.col("balance_amount").sum().alias("total_balance"))
    )
    _pivot_df = _bank_usage_data.pivot(
        index="financial_institution",
        on="account_usage",
        values="total_balance",
    ).fill_null(0)
    _totals = _pivot_df.select(
        pl.sum_horizontal(pl.exclude("financial_institution"))
    ).to_series()
    _pivot_df = _pivot_df.with_columns(_totals.alias("_total"))
    _pivot_df = _pivot_df.sort("_total", descending=True).drop("_total").head(10)
    _bank_usage_pivot = _pivot_df

# Bank chart data (exclude 财务公司)
_bank_data_for_chart = pl.DataFrame()
if _balance_by_bank.height > 0:
    _bank_data_for_chart = _balance_by_bank.filter(pl.col("financial_institution") != "财务公司")

# City known data
_city_known = pl.DataFrame()
if _balance_by_city.height > 0:
    _city_known = _balance_by_city.filter(pl.col("bank_city") != "未知城市")
_top20_city = _city_known.head(20) if _city_known.height > 0 else pl.DataFrame()

# ============================================================
# Smart Query (QueryChat) data — clean wide table for LLM querying
# ============================================================

_querychat_data = pl.DataFrame()
try:
    _querychat_data = _vizro_con.execute("""
        SELECT
            ta.account_id,
            ta.account_name,
            ta.account_number,
            ta.account_status,
            ta.account_nature,
            ta.account_usage,
            COALESCE(NULLIF(ta.financial_institution, ''), '未知') AS financial_institution,
            COALESCE(NULLIF(ta.opening_institution, ''), '未知') AS opening_institution,
            COALESCE(NULLIF(ta.bank_city, ''), '未知城市') AS bank_city,
            COALESCE(NULLIF(ta.country_region, ''), '未知') AS country_region,
            ta.is_overseas,
            ta.is_partner_bank,
            ta.currency,
            COALESCE(NULLIF(ta.sub_group_name, ''), '未知') AS sub_group_name,
            ta.unit_name,
            ta.is_limited,
            ta.management_limit_wan,
            ta.open_date,
            ta.close_date,
            ta.auth_channel,
            ta.is_auth_collection,
            ta.is_auth_payment,
            fb.balance_amount,
            fb.converted_amount,
            fb.balance_date,
            bb.longitude,
            bb.latitude
        FROM finance_data.dim_treasury_account ta
        JOIN finance_data.fact_treasury_account_balance fb ON ta.account_id = fb.account_id
        LEFT JOIN finance_data.dim_bank_branch bb ON ta.institution_code = bb.institution_code
        WHERE fb.period = (SELECT MAX(period) FROM finance_data.fact_treasury_account_balance)
          AND ta.account_status = '存续'
    """).pl()
except Exception:
    pass

# ============================================================
# Smart Query — financial report data per sub_group
# ============================================================

_querychat_finance_by_subgroup = pl.DataFrame()
_querychat_finance_period_label = ""
try:
    _fin_raw = _vizro_con.execute("""
        SELECT
            ff.entity_report_id,
            ff.account_code,
            ff.value,
            ff.period_id
        FROM finance_data.fact_finance_data ff
        JOIN finance_data.dim_report_category rc ON ff.category_id = rc.category_id
        WHERE rc.category_name = '资产负债表'
          AND ff.account_code IN ('01.02.01', '01.02.02')
          AND ff.value_column = '本年累计'
          AND ff.period_id = (SELECT MAX(period_id) FROM finance_data.fact_finance_data)
    """).pl()

    if _fin_raw.height > 0:
        _fin_period = _fin_raw["period_id"][0]
        _querychat_finance_period_label = str(_fin_period)

        _entity_subgroup = _vizro_con.execute("""
            SELECT DISTINCT entity_report_id, sub_group_name
            FROM finance_data.dim_treasury_account
            WHERE entity_report_id IS NOT NULL AND sub_group_name IS NOT NULL
        """).pl()

        _fin_joined = _fin_raw.join(_entity_subgroup, on="entity_report_id", how="inner")
        _querychat_finance_by_subgroup = (
            _fin_joined
            .group_by("sub_group_name")
            .agg([
                pl.col("value").filter(pl.col("account_code") == "01.02.01").sum().alias("fin_company_deposit"),
                pl.col("value").filter(pl.col("account_code") == "01.02.02").sum().alias("commercial_bank_deposit"),
            ])
        )
except Exception:
    pass

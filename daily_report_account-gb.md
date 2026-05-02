---
title: "司库账户管理日报"
author: "司库部"
date: ""
format:
  gb9704-pdf:
    keep-tex: true  
    include-in-header:
      text: |
        \makeatletter
        \renewcommand{\title}[1]{\gdef\@title{#1}}
        \renewcommand{\date}[1]{\gdef\@date{#1}}
        \renewcommand{\author}[1]{}
        \renewcommand{\maketitle}{%
          \ifx\@title\@empty\else
            \gongwentitle{\@title}\par
          \fi
          \ifx\@date\@empty\else
            \gongwensubtitle{（\@date）}\par   % ← 这里加了括号
          \fi
        }
        \makeatother
    echo: false
    code-fold: true
  gb9704-docx:  
    echo: false
    shift-heading-level-by: 0
    code-fold: true
jupyter: python3
lang: zh
---

```{python}
# title: "司库账户管理日报"
# 本期情况
year:int = 2026
month:int = 4
day:int = 29

from siku_utils.helpers import GetSkdata
import polars as pl

SKDATA_CLS = GetSkdata(year, month, day)
Todaystr, LastMonthstr, LastMonthLastDaystr = SKDATA_CLS.get_datestr()

## 管理各类账户数量
(ZHNum_Total, ZHNum_CWGS, ZHNum_ThisMonth_Type1, ZHNum_ThisMonth_Type2,
 ZHNumType1, ZHNumType2, ZHNum_Total_mainland, ZHNumType1_mainland, ZHNumType2_mainland) = SKDATA_CLS.get_ZHNumInfo()

## Type1-不纳入司库管理账户的分类：数量不纳入、账户余额纳入
ZHNumTotalNotIncludeCount_df, _ = SKDATA_CLS.get_df_TotalNotIncludeCountBankAccounts()

# 使用 polars 分组聚合
ZHNumTotalNotIncludeCount_账户性质_count = (
    ZHNumTotalNotIncludeCount_df
    .group_by("账户性质")
    .agg(pl.len().cast(pl.Int64).alias("账户数量"))
    .sort("账户性质")
)
# 计算合计并追加行
total_count = ZHNumTotalNotIncludeCount_账户性质_count["账户数量"].sum()
total_row = pl.DataFrame({"账户性质": ["合计"], "账户数量": [total_count]})
ZHNumTotalNotIncludeCount_账户性质_count_series = pl.concat([ZHNumTotalNotIncludeCount_账户性质_count, total_row])

## Type2-不纳入司库管理账户的分类：数量不纳入、账户余额也纳入
ZHNumTotalNotIncludeAmount_df, _ = SKDATA_CLS.get_df_TotalNotIncludeAmountBankAccounts()

ZHNumTotalNotIncludeAmount_账户性质_count = (
    ZHNumTotalNotIncludeAmount_df
    .group_by("账户性质")
    .agg(pl.len().cast(pl.Int64).alias("账户数量"))
    .sort("账户性质")
)
total_count_amount = ZHNumTotalNotIncludeAmount_账户性质_count["账户数量"].sum()
total_row_amount = pl.DataFrame({"账户性质": ["合计"], "账户数量": [total_count_amount]})
ZHNumTotalNotIncludeAmount_账户性质_count_series = pl.concat([ZHNumTotalNotIncludeAmount_账户性质_count, total_row_amount])

## 账户余额情况
(ZHBalanceBankTotal, ZHBalanceCWGS, ZHBalanceType1, ZHBalanceType2,
 ZHBalanceBankTotal_mainland, ZHBalanceType1_mainland, ZHBalanceType2_mainland) = SKDATA_CLS.get_ZHBalanceInfo()
```


```{python}
import calendar
from siku_utils.helpers import GetSkdata
# 上期情况
YearOfPreviousIssue: int = year if month !=1 else year - 1
MonthOfPreviousIssue: int = month -1 if month!=1 else 12 
DayOfPreviousIssue: int = calendar.monthrange(YearOfPreviousIssue, MonthOfPreviousIssue)[1]

CLS_SKDATAOFPREVIOUSISSUE = GetSkdata(YearOfPreviousIssue, MonthOfPreviousIssue, DayOfPreviousIssue)

(PIZHNum_Total, PIZHNum_CWGS, PIZHNum_ThisMonth_Type1, PIZHNum_ThisMonth_Type2,
 PIZHNumType1, PIZHNumType2, PIZHNum_Total_mainland, PIZHNumType1_mainland, PIZHNumType2_mainland) = CLS_SKDATAOFPREVIOUSISSUE.get_ZHNumInfo()

# 上期 Type1
PIZHNumTotalNotIncludeCount_df, _ = CLS_SKDATAOFPREVIOUSISSUE.get_df_TotalNotIncludeCountBankAccounts()
PIZHNumTotalNotIncludeCount_账户性质_count = (
    PIZHNumTotalNotIncludeCount_df
    .group_by("账户性质")
     .agg(pl.len().cast(pl.Int64).alias("账户数量"))
    .sort("账户性质")
)
total_count_prev = PIZHNumTotalNotIncludeCount_账户性质_count["账户数量"].sum()
total_row_prev = pl.DataFrame({"账户性质": ["合计"], "账户数量": [total_count_prev]})
PIZHNumTotalNotIncludeCount_账户性质_count_series = pl.concat([PIZHNumTotalNotIncludeCount_账户性质_count, total_row_prev])

# 上期 Type2
PIZHNumTotalNotIncludeAmount_df, _ = CLS_SKDATAOFPREVIOUSISSUE.get_df_TotalNotIncludeAmountBankAccounts()
PIZHNumTotalNotIncludeAmount_账户性质_count = (
    PIZHNumTotalNotIncludeAmount_df
    .group_by("账户性质")
    .agg(pl.len().cast(pl.Int64).alias("账户数量"))
    .sort("账户性质")
)
total_count_amount_prev = PIZHNumTotalNotIncludeAmount_账户性质_count["账户数量"].sum()
total_row_amount_prev = pl.DataFrame({"账户性质": ["合计"], "账户数量": [total_count_amount_prev]})
PIZHNumTotalNotIncludeAmount_账户性质_count_series = pl.concat([PIZHNumTotalNotIncludeAmount_账户性质_count, total_row_amount_prev])

# 上期余额
(PIZHBalanceBankTotal, PIZHBalanceCWGS, PIZHBalanceType1, PIZHBalanceType2,
 PIZHBalanceBankTotal_mainland, PIZHBalanceType1_mainland, PIZHBalanceType2_mainland) = CLS_SKDATAOFPREVIOUSISSUE.get_ZHBalanceInfo()
```

::: {.content-visible when-format="pdf"}

\gongwensubtitle{（`{python} Todaystr`）}

:::

::: {.content-visible when-format="docx"}
::: {custom-style="Subtitle"}
（`{python} Todaystr`）
:::

:::


```{python}
## 未纳入司库账户情况
ZHNUM_NOTINCLUDE_SK: int = 0
PIZHNUM_NOTINCLUDE_SK: int = 0
ZHNum_All: int = ZHNum_Total + ZHNUM_NOTINCLUDE_SK
```

各单位在银行共开立账户`{python} ZHNum_All`个，其中：已纳入司库管理账户`{python} ZHNum_Total`个(境内开立账户`{python} ZHNum_Total_mainland`个)，未纳入司库管理账户`{python} ZHNUM_NOTINCLUDE_SK`个，账户可视率`{python} round(ZHNum_Total/ZHNum_All*100, 1)`%。

除此之外，各单位共开立虚拟账户[^1] `{python} total_count`个，共在司库登记党团工会等账户`{python} total_count_amount`个。

```{python}
#| label: tbl-sk-account
#| tbl-cap: 司库账户构成

from IPython.display import Markdown
from tabulate import tabulate

ZHNumTotal_Delta = SKDATA_CLS.sign_num(ZHNumType1 - PIZHNumType1 + ZHNumType2 - PIZHNumType2)
ZHNumTotal_mainland_Delta = SKDATA_CLS.sign_num(ZHNum_Total_mainland - PIZHNum_Total_mainland)
ZHNUM_NOTINCLUDE_SK_Delta = SKDATA_CLS.sign_num(ZHNUM_NOTINCLUDE_SK - PIZHNUM_NOTINCLUDE_SK)

table = [
    ["已纳入司库管理（境内开立账户）", f'{ZHNum_Total}({ZHNum_Total_mainland})', f'{PIZHNum_Total}({PIZHNum_Total_mainland})', f'{ZHNumTotal_Delta}({ZHNumTotal_mainland_Delta})'],
    ["未纳入司库管理", ZHNUM_NOTINCLUDE_SK, PIZHNUM_NOTINCLUDE_SK, ZHNUM_NOTINCLUDE_SK_Delta],
    ["合计", ZHNum_Total+ZHNUM_NOTINCLUDE_SK, PIZHNum_Total+PIZHNUM_NOTINCLUDE_SK, SKDATA_CLS.sign_num(ZHNum_Total+ZHNUM_NOTINCLUDE_SK - PIZHNum_Total - ZHNUM_NOTINCLUDE_SK)],
]
Markdown(tabulate(table, headers=["项目", Todaystr, LastMonthLastDaystr, "变化情况"]))
```

# 一、在财务公司开立账户情况

```{python}
ZHNum_CWGS_Delta = SKDATA_CLS.sign_num(ZHNum_CWGS - PIZHNum_CWGS)
ZHBalanceCWGS_Delta = SKDATA_CLS.sign_num(round(ZHBalanceCWGS - PIZHBalanceCWGS, 1), "金额", quantifier="亿元")
```

各单位在财务公司开立账户数量为`{python} ZHNum_CWGS`个，与`{python} LastMonthstr`月末相比`{python} ZHNum_CWGS_Delta`。

各单位在财务公司开立账户余额为`{python} round(ZHBalanceCWGS,2)`亿元，与`{python} LastMonthstr`月末相比`{python} ZHBalanceCWGS_Delta`。

```{python}
#| label: tbl-cwgs-account
#| tbl-cap: 财务公司账户构成

table = [
    ["财务公司账户数量(个)", ZHNum_CWGS, PIZHNum_CWGS, f"{ZHNum_CWGS_Delta}"],
    ["财务公司账户余额(亿元)", round(ZHBalanceCWGS,2), round(PIZHBalanceCWGS,2), f"{ZHBalanceCWGS_Delta}"],
]
Markdown(tabulate(table, headers=["项目", Todaystr, LastMonthLastDaystr, "变化情况"]))
```

# 二、在银行开立账户情况

```{python}
ZHNumType1_Delta = SKDATA_CLS.sign_num(ZHNumType1 - PIZHNumType1)
ZHNumType2_Delta = SKDATA_CLS.sign_num(ZHNumType2 - PIZHNumType2)
ZHNumTotal_Delta = SKDATA_CLS.sign_num(ZHNumType1 - PIZHNumType1 + ZHNumType2 - PIZHNumType2)
ZHBalanceType1_Delta = SKDATA_CLS.sign_num(round(ZHBalanceType1 - PIZHBalanceType1, 2), quantifier='亿元')
ZHBalanceType2_Delta = SKDATA_CLS.sign_num(round(ZHBalanceType2 - PIZHBalanceType2, 2), quantifier='亿元')
ZHBalanceTotal_Delta = SKDATA_CLS.sign_num(round(ZHBalanceType1 - PIZHBalanceType1 + ZHBalanceType2 - PIZHBalanceType2, 2), quantifier='亿元')
ZHNumType1_mainland_Delta = SKDATA_CLS.sign_num(ZHNumType1_mainland - PIZHNumType1_mainland)
ZHNumType2_mainland_Delta = SKDATA_CLS.sign_num(ZHNumType2_mainland - PIZHNumType2_mainland)
```

各单位已纳入司库管理银行账户`{python} ZHNum_Total`个，其中：合作银行账户`{python} ZHNumType1`个(境内开立账户`{python} ZHNumType1_mainland`个)，非合作银行账户`{python} ZHNumType2`个(境内开立账户`{python} ZHNumType2_mainland`个)。与`{python} LastMonthstr`月末相比，合作银行账户数量`{python} ZHNumType1_Delta`(境内开立账户`{python} ZHNumType1_mainland_Delta`)，非合作银行账户数量`{python} ZHNumType2_Delta`(境内开立账户`{python} ZHNumType2_mainland_Delta`)。

```{python}
#| label: tbl-type1&2-account
#| tbl-cap: 在银行开立账户情况

table = [
    ["在银行开立账户数量(个)", ZHNum_Total, PIZHNum_Total, f'{ZHNumTotal_Delta}'],
    ["在银行开立账户余额(亿元)", round(ZHBalanceType1 + ZHBalanceType2, 2), round(PIZHBalanceType1 + PIZHBalanceType2, 2), f"{ZHBalanceTotal_Delta}"],
]
Markdown(tabulate(table, headers=["项目", Todaystr, LastMonthLastDaystr, "变化情况"]))
```

```{python}
#| label: tbl-type1-account
#| tbl-cap: 在合作银行开立账户情况

table = [
    ["在合作银行开立账户数量(个)", ZHNumType1, PIZHNumType1, f'{ZHNumType1_Delta}'],
    ["在合作银行开立账户余额(亿元)", round(ZHBalanceType1, 2), round(PIZHBalanceType1, 2), f'{ZHBalanceType1_Delta}'],
]
Markdown(tabulate(table, headers=["项目", Todaystr, LastMonthLastDaystr, "变化情况"]))
```

```{python}
#| label: tbl-type2-account
#| tbl-cap: 在非合作银行开立账户情况

table = [
    ["在非合作银行开立账户数量(个)", ZHNumType2, PIZHNumType2, f'{ZHNumType2_Delta}'],
    ["在非合作银行开立账户余额(亿元)", round(ZHBalanceType2, 2), round(PIZHBalanceType2, 2), f'{ZHBalanceType2_Delta}'],
]
Markdown(tabulate(table, headers=["项目", Todaystr, LastMonthLastDaystr, "变化情况"]))
```

# 三、司库系统开立虚拟账户情况

```{python}
total_count_current = ZHNumTotalNotIncludeCount_账户性质_count_series.filter(pl.col("账户性质") == "合计")["账户数量"][0]
total_count_previous = PIZHNumTotalNotIncludeCount_账户性质_count_series.filter(pl.col("账户性质") == "合计")["账户数量"][0]
ZHNumTotalNotIncludeCount_账户性质_sum_Delta = SKDATA_CLS.sign_num(round(total_count_current - total_count_previous, 1))
```

各单位在司库系统开立的虚拟账户`{python} total_count_current`个。与`{python} LastMonthstr`月末相比，虚拟账户`{python} ZHNumTotalNotIncludeCount_账户性质_sum_Delta`。

```{python}
#| label: tbl-NouInclude-account
#| tbl-cap: 虚拟账户情况


# 合并本期和上期数据，并计算变化
pivot_prev = PIZHNumTotalNotIncludeCount_账户性质_count_series.rename({"账户数量": "账户数量_上期"})
joined = ZHNumTotalNotIncludeCount_账户性质_count_series.join(
    pivot_prev,
    on="账户性质",
    how="full",
).fill_null(0)
joined = joined.rename({"账户数量": "账户数量_本期"})
joined = joined.with_columns(
    (pl.col("账户数量_本期") - pl.col("账户数量_上期")).alias("diff")
)
diff_list = joined["diff"].to_list()
sign_list = [SKDATA_CLS.sign_num(int(d)) for d in diff_list]
joined = joined.with_columns(pl.Series("变化情况", sign_list))

# 不使用 to_pandas()，直接提取行数据
rows = []
for row in joined.iter_rows():
    # row 顺序: (账户性质, 账户数量_本期, 账户数量_上期, diff, 变化情况)
    rows.append([row[0], row[1], row[3], row[4]])  # 跳过 diff 列

headers = [Todaystr, LastMonthLastDaystr, "变化情况"]
from tabulate import tabulate
Markdown(tabulate(rows, headers=headers, tablefmt="github"))

```

# 四、在途流程办理情况

暂无数据权限。
```{python}
# ZHFlow_金融处, ZHFlow_部领导, ZHFlow_集团总会, ZHFlow_补录 = SKDATA_CLS.get_ZHFlow("开户申请")

# 1.  账户新开立申请。集团公司财金部金融处尚有`{python} ZHFlow_金融处`个流程未办理完毕，部领导尚有`{python} ZHFlow_部领导`个流程未办理完毕，集团公司领导尚有`{python} ZHFlow_集团总会`个非合作银行未审批。子集团经办尚有`{python} ZHFlow_补录`个流程未提交账号补录申请。

# ZHFlow_金融处, ZHFlow_部领导, ZHFlow_集团总会, ZHFlow_补录 = SKDATA_CLS.get_ZHFlow("变更备案")

# 2. 账户变更申请。集团公司财金部金融处尚有`{python} ZHFlow_金融处`个流程未办理完毕，部领导尚有`{python} ZHFlow_部领导`个流程未办理完毕。
```
# 五、下一步工作重点任务

一是跟踪账户配额方案制订情况。

二是久悬、低效账户压减进度。

三是非合作银行账户清理进度。

四是暂停归集账户清单。

五是关注支出户余额较大情况，研究预警方案（如累计余额占货币资金比大于2%）。


[^1]: `{python} f'各单位在司库系统开立的虚拟账户余额计入集团公司银行存款余额，但是账户数量不计入司库管理账户数量。此类账户包括：{" ， ".join(ZHNumTotalNotIncludeCount_账户性质_count_series.filter(pl.col("账户性质") != "合计")["账户性质"].to_list())}。'`

"""
离线科目映射脚本 — 将司库快报 Excel 科目映射到标准科目库 (standard_accounts.json)

层级检测: 基于 Excel 编号格式 (01, 03-1, 03-1-1) 而非缩进
匹配策略: 名称 + 别名匹配，利用标准科目 parent_code 做父级约束

用法: python3 scripts/run_mapping_standards.py
输入: scripts/financereport_template.xlsx
输出: conf/base/finance_mapping_standard.yaml
"""

import json
import re
import polars as pl
from pathlib import Path
from datetime import datetime
import yaml

_PROJ_DIR = Path(__file__).parent.parent

# =====================
# 1. 加载标准科目库
# =====================
def load_standard_accounts(json_path: str) -> pl.DataFrame:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = []
    for report in data["reports"]:
        for acct in report["accounts"]:
            rules = acct.get("match_rules", {})
            records.append({
                "account_code": acct["account_code"],
                "account_code_dash": acct["account_code_dash"],
                "account_name": acct["account_name"],
                "standard_path": acct["standard_path"],
                "report_category": acct["report_category"],
                "report_type": report["report_type"],
                "parent_code": acct["parent_code"],
                "level": acct["level"],
                "is_summary": acct["is_summary"],
                "is_leaf_for_fact": acct["is_leaf_for_fact"],
                "aliases": rules.get("aliases", []),
                "scope_parent_code": rules.get("scope_parent_code", ""),
                "ignore_prefix": rules.get("ignore_prefix", []),
                "exact_match_only": rules.get("exact_match_only", False),
                "match_priority": rules.get("match_priority", 100),
            })

    return pl.DataFrame(records)


# =====================
# 2. 解析 Excel
# =====================
CN_CATEGORY_MAP = {
    "资产负债表": "资产负债表",
    "利润表": "利润表",
    "现金流量表": "现金流量表",
    "所有者权益": "所有者权益变动表",
}


def find_section_header_idx(df_raw: pl.DataFrame) -> int | None:
    """找到列标题行 (包含 '项' and '行号')"""
    for i, row in enumerate(df_raw.iter_rows(named=False)):
        val0 = str(row[0]) if row[0] else ""
        val1 = str(row[1]) if len(row) > 1 and row[1] else ""
        if "项" in val0 and "行号" in val1:
            return i
    return None


def parse_excel_number(raw: str) -> tuple[str, str, int]:
    """
    从原始项目文本提取编号信息。
    返回: (excel_num, parent_excel_num, level)

    例:
      "01.资产总额" → ("01", "", 1)
      "03-1 ... 其中：现金" → ("03-1", "03", 2)
      "07-1-1 ... 票据贴现" → ("07-1-1", "07-1", 3)
    """
    stripped = raw.lstrip(" ")

    # 匹配编号模式: 如 "01.", "03-1", "03-3-2"
    m = re.match(r"^(\d+(?:[\.\-]\d+)*)[\.\s]*", stripped)
    if not m:
        return ("", "", 0)

    excel_num = m.group(1).rstrip(".-")  # "03-1"
    segments = re.split(r"[.\-]", excel_num)
    level = len(segments)

    parent_excel_num = ""
    if level > 1:
        parent_excel_num = "-".join(segments[:-1]) if "-" in m.group(1) else ".".join(segments[:-1])
        # 检测分隔符: 主编号用 ".", 子编号用 "-"
        if "." in m.group(1) and level == 2:
            pass  # 保持原分隔符
        if "-" in excel_num:
            parent_excel_num = "-".join(segments[:-1])
        elif "." in excel_num:
            parent_excel_num = ".".join(segments[:-1])

    return (excel_num, parent_excel_num, level)


def clean_item_name(raw: str) -> tuple[str, bool]:
    """
    清洗项目名称: 去除编号前缀、其中前缀、前后空格。
    返回: (cleaned_name, has_qizhong)
    """
    stripped = raw.strip()
    has_qizhong = "其中" in stripped

    # 去除编号前缀 "01.", "03-1", "07-1-1"
    cleaned = re.sub(r"^\d+(?:[\.\-]\d+)*[\.\s]*", "", stripped)

    # 去除 "其中：", "其中:"
    cleaned = re.sub(r"其中[：:]\s*", "", cleaned)

    cleaned = cleaned.strip()
    return (cleaned, has_qizhong)


def detect_report_category(section_title: str) -> str | None:
    """从分区标题判断报表类别"""
    if section_title is None:
        return None
    for cn, cat in CN_CATEGORY_MAP.items():
        if cn in section_title:
            return cat
    return None


def parse_main_sheet(file_path: str, sheet_name: str) -> pl.DataFrame:
    """
    解析快报表/附表: 分区标题 → section-based, 编号层级 → level/parent
    """
    df_raw = pl.read_excel(file_path, sheet_name=sheet_name, engine="calamine", has_header=False)

    header_idx = find_section_header_idx(df_raw)
    if header_idx is None:
        raise ValueError(f"Sheet [{sheet_name}] 找不到列标题行")

    df_data = df_raw.slice(header_idx + 1)
    col_names = {f"column_{i+1}": name for i, name in enumerate(["item_raw", "row_num", "monthly", "ytd", "last_year"])}
    df_data = df_data.rename(col_names)

    # 标记分区标题 (row_num 为非数字 或 item 本身是 section header)
    df_data = df_data.with_columns(
        pl.when(
            ~pl.col("row_num").cast(pl.Utf8).str.contains(r"^\d+$")
        )
        .then(pl.col("item_raw"))
        .otherwise(None)
        .alias("section_title_from_nondigit")
    )

    # 同时从 item_raw 检测 section header 文字 (如 "一、资产负债表指标")
    # 这些行有数字 row_num 但实际是分区标题
    df_data = df_data.with_columns(
        pl.when(
            pl.col("item_raw").cast(pl.Utf8).str.contains(r"^[  \t]*[一二三四五六七八九十]、")
        )
        .then(pl.col("item_raw"))
        .otherwise(pl.col("section_title_from_nondigit"))
        .alias("section_title")
    )
    df_data = df_data.with_columns(pl.col("section_title").forward_fill())

    # 映射报表类别
    df_data = df_data.with_columns(
        pl.col("section_title").map_elements(
            detect_report_category, return_dtype=pl.Utf8
        ).alias("report_category")
    )

    # 只保留数据行 (row_num 为纯数字 且 不是 section header)
    df_data = df_data.filter(
        pl.col("row_num").cast(pl.Utf8).str.contains(r"^\d+$")
        & ~pl.col("item_raw").cast(pl.Utf8).str.contains(r"^[  \t]*[一二三四五六七八九十]、")
    )
    df_data = df_data.with_columns(pl.col("row_num").cast(pl.Int32).alias("row_num_int"))

    # 解析编号
    parsed = []
    for row in df_data.iter_rows(named=True):
        excel_num, parent_excel_num, level = parse_excel_number(row["item_raw"])
        item_clean, has_qizhong = clean_item_name(row["item_raw"])
        parsed.append({
            "item_raw": row["item_raw"].strip(),
            "item_clean": item_clean,
            "has_qizhong": has_qizhong,
            "excel_num": excel_num,
            "parent_excel_num": parent_excel_num,
            "level": level,
            "report_category": row["report_category"],
            "row_num_int": row["row_num_int"],
            "ytd": row.get("ytd", ""),
        })

    result = pl.DataFrame(parsed)
    return result.sort("row_num_int")


# =====================
# 3. 匹配器
# =====================
class StandardAccountMatcher:
    def __init__(self, df_std: pl.DataFrame):
        self.df_std = df_std
        self.grouped = {}   # {(report_category, parent_code): [accounts]}
        self.flat_by_category = {}

        for row in df_std.iter_rows(named=True):
            cat = row["report_category"]
            parent = row["parent_code"]
            key = (cat, parent)
            if key not in self.grouped:
                self.grouped[key] = []
            self.grouped[key].append(row)

            if cat not in self.flat_by_category:
                self.flat_by_category[cat] = []
            self.flat_by_category[cat].append(row)

    def match_scoped(self, item_clean: str, parent_code: str, report_category: str) -> dict | None:
        """仅在父级约束范围内匹配，不回退到全局搜索。"""
        if not parent_code or not report_category:
            return None
        key = (report_category, parent_code)
        candidates = []
        for acct in self.grouped.get(key, []):
            if self._name_matches(item_clean, acct):
                candidates.append(acct)
        if candidates:
            return max(candidates, key=lambda x: x["match_priority"])
        return None

    def match(self, item_clean: str, parent_code: str, report_category: str) -> dict | None:
        """匹配单个清洗后的科目名称"""
        candidates = []

        # 1. 在父级约束范围内查找
        if parent_code and report_category:
            key = (report_category, parent_code)
            if key in self.grouped:
                for acct in self.grouped[key]:
                    if self._name_matches(item_clean, acct):
                        candidates.append(acct)

        # 2. 全局查找（同报表类别）
        if not candidates and report_category:
            for acct in self.flat_by_category.get(report_category, []):
                if self._name_matches(item_clean, acct):
                    candidates.append(acct)

        # 3. 跨报表全局查找
        if not candidates:
            for acct in self.flat_by_category.get("利润表", []):
                if self._name_matches(item_clean, acct):
                    candidates.append(acct)

        if candidates:
            best = max(candidates, key=lambda x: x["match_priority"])
            return best
        return None

    def _name_matches(self, item_clean: str, acct: dict) -> bool:
        if acct["exact_match_only"]:
            return item_clean == acct["account_name"]
        if item_clean == acct["account_name"]:
            return True
        for alias in acct["aliases"]:
            if item_clean == alias:
                return True
        return False


# =====================
# 4. 逐行映射
# =====================
def map_sheet_rows(df: pl.DataFrame, matcher: StandardAccountMatcher,
                   is_indicator_sheet: bool = False) -> pl.DataFrame:
    """
    对单张 Sheet 的所有行执行逐行映射。
    使用: excel_num 层级 + 标准科目 code parent_stack。
    """
    if is_indicator_sheet:
        results = []
        for row in df.iter_rows(named=True):
            results.append({
                "原始项目": row["item_raw"],
                "清理后名称": row["item_clean"],
                "是否其中项": False,
                "报表分区": "分析指标表",
                "标准科目代码": None,
                "标准科目路径": None,
                "数据类型": "INDICATOR_UNMATCHED",
                "匹配状态": "UNMATCHED",
            })
        return pl.DataFrame(results)

    # parent_stack: [(excel_num, 标准_account_code, 标准_path), ...]
    parent_stack = []
    path_map = {}  # excel_num → (code, path)，支持乱序行查找父级
    results = []

    for row in df.iter_rows(named=True):
        item_clean = row["item_clean"]
        has_qizhong = row["has_qizhong"]
        report_cat = row["report_category"]
        excel_num = row["excel_num"]
        parent_excel_num = row["parent_excel_num"]
        level = row["level"]
        ytd_val = row.get("ytd", "")

        if report_cat is None:
            # 附表 section 无法确定报表类别，尝试所有类别匹配
            report_cat = ""

        # 栈维护: 在整个栈中查找父级编号（支持乱序排列的行）
        if parent_excel_num:
            found_idx = -1
            for i in range(len(parent_stack) - 1, -1, -1):
                if parent_stack[i][0] == parent_excel_num:
                    found_idx = i
                    break
            if found_idx >= 0:
                parent_stack = parent_stack[:found_idx + 1]
        else:
            parent_stack = []

        # 优先用 path_map 按编号查父级（支持乱序行），回退到栈顶
        if parent_excel_num and parent_excel_num in path_map:
            current_parent_code, current_parent_path = path_map[parent_excel_num]
        else:
            current_parent_code = parent_stack[-1][1] if parent_stack else ""
            current_parent_path = parent_stack[-1][2] if parent_stack else ""

        matched = matcher.match(item_clean, current_parent_code, report_cat)

        # 子项匹配: 以父科目范围为优先，消歧同名子项
        if current_parent_code and item_clean:
            scoped_match = matcher.match_scoped(item_clean, current_parent_code, report_cat)
            if scoped_match:
                code = scoped_match["account_code"]
                path = f"{current_parent_path} > {item_clean}"
            else:
                code = f"{current_parent_code}.{item_clean}"
                path = f"{current_parent_path} > {item_clean}"

            parent_stack.append((excel_num, code, path))
            path_map[excel_num] = (code, path)
            results.append({
                "原始项目": row["item_raw"],
                "清理后名称": item_clean,
                "是否其中项": has_qizhong,
                "报表分区": report_cat,
                "标准科目代码": code,
                "标准科目路径": path,
                "数据类型": "SUB_DETAIL",
                "匹配状态": "MATCHED",
            })
            continue

        if matched:
            code = matched["account_code"]
            path = matched["standard_path"]

            # 数据类型
            if matched["is_summary"]:
                detail_type = "SUMMARY"
            elif has_qizhong:
                detail_type = "SUB_DETAIL"
                # 其中项匹配到父科目时，追加子项名称到路径和代码
                if item_clean != matched["account_name"]:
                    path = f"{path} > {item_clean}"
                    code = f"{code}.{item_clean}"
            else:
                detail_type = "TOTAL"

            parent_stack.append((excel_num, code, path))
            path_map[excel_num] = (code, path)

            results.append({
                "原始项目": row["item_raw"],
                "清理后名称": item_clean,
                "是否其中项": has_qizhong,
                "报表分区": report_cat,
                "标准科目代码": code,
                "标准科目路径": path,
                "数据类型": detail_type,
                "匹配状态": "MATCHED",
            })
        else:
            parent_stack.append((excel_num, "", ""))

            results.append({
                "原始项目": row["item_raw"],
                "清理后名称": item_clean,
                "是否其中项": has_qizhong,
                "报表分区": report_cat,
                "标准科目代码": None,
                "标准科目路径": None,
                "数据类型": "UNMATCHED",
                "匹配状态": "UNMATCHED",
            })

    return pl.DataFrame(results)


# =====================
# 5. 主流程
# =====================
def main():
    excel_file = str(_PROJ_DIR / "scripts/financereport_template.xlsx")
    standard_json = str(_PROJ_DIR / "conf/base/standard_accounts.json")
    output_yaml = str(_PROJ_DIR / "conf/base/finance_mapping_standard.yaml")

    # 从封面提取企业信息（模板可能无具体企业，作为通用映射表）
    company_name = "通用模板"
    try:
        df_cover = pl.read_excel(excel_file, sheet_name="司库报表_封面代码", engine="calamine", has_header=False)
        for row in df_cover.iter_rows(named=False):
            if row[0] == "企业名称":
                company_name = str(row[1]) if row[1] else company_name
                break
    except Exception:
        pass  # 模板文件可能无封面，使用默认值

    print(f"企业: {company_name}")

    # 加载标准库
    print("[1/4] 加载标准科目库...")
    df_std = load_standard_accounts(standard_json)
    matcher = StandardAccountMatcher(df_std)
    print(f"  已加载 {len(df_std)} 个标准科目 (资产负债表 64 + 利润表 43 + 现金流量表 38 + 权益变动 5)")

    all_mappings = []
    all_unmatched = []

    # === 快报表 ===
    print("\n[2/4] 处理主要财务指标快报表...")
    df_main = parse_main_sheet(excel_file, "司库报表_主要财务指标快报表")
    df_mapped_main = map_sheet_rows(df_main, matcher)
    matched = df_mapped_main.filter(pl.col("匹配状态") == "MATCHED").height
    unmatched = df_mapped_main.filter(pl.col("匹配状态") == "UNMATCHED").height
    print(f"  总行数: {df_mapped_main.height}, 匹配: {matched}, 未匹配: {unmatched}")

    # 分报表类别统计
    for cat in ["资产负债表", "利润表", "现金流量表"]:
        sub = df_mapped_main.filter(pl.col("报表分区") == cat)
        m = sub.filter(pl.col("匹配状态") == "MATCHED").height
        t = sub.height
        print(f"    {cat}: {m}/{t} 匹配")

    all_mappings.append(df_mapped_main)
    unmatched_main = df_mapped_main.filter(pl.col("匹配状态") == "UNMATCHED")
    if unmatched_main.height > 0:
        all_unmatched.append(unmatched_main.with_columns(pl.lit("主要财务指标快报表").alias("来源表")))

    # === 快报附表 ===
    print("\n[3/4] 处理主要财务指标快报附表...")
    df_supp = parse_main_sheet(excel_file, "司库报表_主要财务指标快报附表")
    df_mapped_supp = map_sheet_rows(df_supp, matcher)
    matched = df_mapped_supp.filter(pl.col("匹配状态") == "MATCHED").height
    unmatched = df_mapped_supp.filter(pl.col("匹配状态") == "UNMATCHED").height
    print(f"  总行数: {df_mapped_supp.height}, 匹配: {matched}, 未匹配: {unmatched}")

    all_mappings.append(df_mapped_supp)
    unmatched_supp = df_mapped_supp.filter(pl.col("匹配状态") == "UNMATCHED")
    if unmatched_supp.height > 0:
        all_unmatched.append(unmatched_supp.with_columns(pl.lit("主要财务指标快报附表").alias("来源表")))

    # === 分析指标表 (全部 UNMATCHED) ===
    print("\n[4/4] 处理主要分析指标表 (全部标记 UNMATCHED)...")
    df_ind = pl.read_excel(excel_file, sheet_name="司库报表_主要分析指标表", engine="calamine", has_header=False)
    header_idx = None
    for i, row in enumerate(df_ind.iter_rows(named=False)):
        val0 = str(row[0]) if row[0] else ""
        val1 = str(row[1]) if len(row) > 1 and row[1] else ""
        if "指标名称" in val0 and "行次" in val1:
            header_idx = i
            break

    indicator_rows = []
    if header_idx is not None:
        df_data = df_ind.slice(header_idx + 1)
        for row in df_data.iter_rows(named=False):
            raw = str(row[0]).strip() if row[0] else ""
            if not raw:
                continue
            # 跳过 section 标题
            if re.match(r"^[一二三四五六七八九十]", raw):
                continue
            row_num = str(row[1]) if len(row) > 1 and row[1] else ""
            if row_num == "--":
                continue
            ytd = str(row[2]) if len(row) > 2 and row[2] else ""
            cleaned, _ = clean_item_name(raw)
            indicator_rows.append({
                "item_raw": raw,
                "item_clean": cleaned,
                "has_qizhong": False,
                "excel_num": "",
                "parent_excel_num": "",
                "level": 0,
                "report_category": "分析指标表",
                "row_num_int": 0,
                "ytd": ytd,
            })

    if indicator_rows:
        df_ind_parsed = pl.DataFrame(indicator_rows)
        df_mapped_ind = map_sheet_rows(df_ind_parsed, matcher, is_indicator_sheet=True)
        print(f"  总行数: {df_mapped_ind.height} (全部 UNMATCHED)")
        all_mappings.append(df_mapped_ind)
        all_unmatched.append(df_mapped_ind.with_columns(pl.lit("主要分析指标表").alias("来源表")))

    # === 合并 & 输出 ===
    df_all = pl.concat(all_mappings)

    total = df_all.height
    total_matched = df_all.filter(pl.col("匹配状态") == "MATCHED").height
    total_unmatched = df_all.filter(pl.col("匹配状态") == "UNMATCHED").height

    # YAML
    mapping_dict = {
        "metadata": {
            "standard_version": "2.0",
            "mapping_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_rows": total,
            "matched_rows": total_matched,
            "unmatched_rows": total_unmatched,
            "description": "司库快报通用科目映射表 — 基于2018年版企业财务报表标准层级结构",
        },
        "row_mappings": df_all.to_dicts(),
    }

    with open(output_yaml, "w", encoding="utf-8") as f:
        yaml.dump(mapping_dict, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"\n映射文件: {output_yaml}")

    print(f"\n{'='*60}")
    print(f"总计: {total} 行, 匹配: {total_matched}, 未匹配: {total_unmatched}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

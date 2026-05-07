import re
import pandas as pd
import yaml
from typing import Dict, List, Any, Optional, Tuple


# 章节标题检测：一、资产负债表指标 / 二、利润表指标 / 四、现金流量表指标
_SECTION_HEADER_PATTERN = re.compile(r'^([一二三四])、')
_CN_TO_REPORT_CATEGORY = {
    "一": "资产负债表",
    "二": "利润表",
    "三": "所有者权益变动表",
    "四": "现金流量表",
}


class FinanceExcelParser:
    """财务Excel解析器 - 配置驱动"""

    def __init__(self, config_path: str = "conf/base/finance_loader.yml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def identify_sheet_type(self, sheet_name: str) -> Tuple[str, Optional[Dict]]:
        patterns = self.config["sheet_identification"]
        for pattern in patterns["base_info_pattern"]:
            if pattern in sheet_name:
                return "base_info", self._get_sheet_override(sheet_name)
        for pattern in patterns["report_data_pattern"]:
            if pattern in sheet_name:
                return "report_data", self._get_sheet_override(sheet_name)
        return "other", self._get_sheet_override(sheet_name)

    def _get_sheet_override(self, sheet_name: str) -> Optional[Dict]:
        overrides = self.config.get("sheet_overrides", {})
        for pattern, cfg in overrides.items():
            if pattern in sheet_name:
                return cfg
        return None

    def parse_base_info_sheet(self, df: pd.DataFrame, override: Optional[Dict] = None) -> Dict:
        """解析基础信息工作表，返回字段字典。自动拆分 code | name 格式。"""
        result = {}
        field_mapping = (override or {}).get("field_mapping", {})

        if field_mapping:
            for idx in range(len(df)):
                if df.shape[1] < 2:
                    continue

                field_cell = df.iloc[idx, 0] if pd.notna(df.iloc[idx, 0]) else None
                if field_cell is None:
                    continue

                field_str = str(field_cell).strip()
                if not field_str:
                    continue

                for pattern, field_name in field_mapping.items():
                    if pattern in field_str:
                        value_cell = df.iloc[idx, 1] if df.shape[1] > 1 else None
                        if pd.notna(value_cell):
                            raw_value = str(value_cell).strip()
                            result[field_name] = raw_value
                            # 自动拆分 code | name 格式
                            self._split_code_name(result, field_name, raw_value)
                        break
        else:
            for _, row in df.iterrows():
                if df.shape[1] >= 2 and pd.notna(row.iloc[0]) and pd.notna(row.iloc[1]):
                    key = str(row.iloc[0]).strip()
                    val = str(row.iloc[1]).strip()
                    result[key] = val
        return result

    def _split_code_name(self, result: dict, field_name: str, raw_value: str):
        """检测 code | name 格式并拆分为 _code 和 _name 字段。"""
        import re
        m = re.match(r'^(\S+)\s*\|\s*(.+)$', raw_value)
        if m:
            code_part = m.group(1)
            name_part = m.group(2).strip()
            # 只有第一部分像代码（数字/字母组成）才拆分
            if re.match(r'^[0-9A-Za-z]+$', code_part):
                result[f"{field_name}_code"] = code_part
                result[f"{field_name}_name"] = name_part

    def parse_report_sheet(
        self,
        df: pd.DataFrame,
        sheet_name: str,
        override: Optional[Dict] = None,
        file_meta: Optional[Dict] = None,
    ) -> pd.DataFrame:
        """解析报表数据工作表，返回长格式DataFrame"""
        rules = self._merge_rules(override)

        # 跳过指定行数
        skip_rows = rules.get("skip_rows", self.config["default_rules"]["skip_rows"])
        df = df.iloc[skip_rows:].reset_index(drop=True)

        # 设置表头
        header_row = rules.get("header_row", self.config["default_rules"]["header_row"])
        if header_row is not None and header_row >= 0:
            # 设置表头 - 使用列表确保正确的列名
            df.columns = df.iloc[header_row].tolist()
            # 删除表头行及之前的行
            df = df.iloc[header_row + 1:].reset_index(drop=True)

        # 识别指标列
        indicator_col = rules.get("indicator_column", self.config["default_rules"]["indicator_column"])
        indicator_col_idx = self._find_column_index(df, indicator_col)

        # 识别数值列
        value_cols = rules.get("value_columns", [])
        if not value_cols:
            patterns = self.config["default_rules"]["value_columns_pattern"]
            value_cols = self._find_value_columns(df, patterns)

        # 构建路径并生成记录
        records = []
        path_stack = []
        namespace_code_map = {}  # 当前命名空间的 code → clean_name
        current_report_category = None  # 当前章节对应的报表类别

        for idx, row in df.iterrows():
            raw_text = str(row.iloc[indicator_col_idx]) if indicator_col_idx is not None else ""
            if not raw_text or raw_text == "nan":
                continue

            # Step A - 章节检测（命名空间）
            section_match = _SECTION_HEADER_PATTERN.match(raw_text)
            if section_match:
                cn_num = section_match.group(1)  # "一" / "二" / "三" / "四"
                current_report_category = _CN_TO_REPORT_CATEGORY[cn_num]
                namespace_code_map = {}  # 新命名空间重置映射
                path_stack = []          # 清空路径栈，防跨章节污染
                continue  # 跳过章节标题行

            # Step B - 提取编号和名称
            number, level, clean_name = self._extract_number_and_name(raw_text)
            if not number:
                continue

            # Step C - 存储顶层科目映射
            top_code = number.split("-")[0]  # "03-3-1" → "03"
            if level == 1:
                namespace_code_map[top_code] = clean_name

            # Step D - 查询顶层科目名
            top_level_name = namespace_code_map.get(top_code, "")

            # Step E - 管理路径栈
            while len(path_stack) >= level:
                path_stack.pop()
            path_stack.append(clean_name)
            full_path = " > ".join(path_stack)

            # 处理每个数值列
            for val_col in value_cols:
                val_col_name = str(df.columns[val_col])
                val = row.iloc[val_col]
                try:
                    val = float(val) if pd.notna(val) else 0.0
                except (ValueError, TypeError):
                    val = 0.0

                records.append({
                    "indicator_raw": raw_text,
                    "indicator_clean": clean_name,
                    "indicator_number": number,
                    "indicator_level": level,
                    "full_path": full_path,
                    "value_column": val_col_name,
                    "value": val,
                    "sheet_name": sheet_name,
                    "report_category": current_report_category,
                    "top_level_account_name": top_level_name,
                    **{k: v for k, v in (file_meta or {}).items()},
                })

        return pd.DataFrame(records)

    def _extract_number_and_name(self, raw_text: str) -> Tuple[Optional[str], int, str]:
        """提取编号、层级和清洗后的指标名"""
        rules = self.config["numbering_rules"]
        pattern = rules["pattern"]
        match = re.match(pattern, raw_text)

        number = None
        level = 1
        if match:
            number = match.group(1)
            if rules.get("normalize_to") == "dash":
                number = number.replace(".", "-")
            level = number.count(rules["separator"]) + 1

        # 清洗名称
        name = raw_text
        if number:
            name = name.replace(match.group(0), "", 1).strip()
        for prefix in rules.get("strip_prefixes", []):
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        name = name.strip()

        return number, level, name

    def _find_column_index(self, df: pd.DataFrame, pattern: str) -> Optional[int]:
        for i, col in enumerate(df.columns):
            if pattern in str(col):
                return i
        return None  # 没有找到

    def _find_value_columns(self, df: pd.DataFrame, patterns: List[str]) -> List[int]:
        indices = []
        for i, col in enumerate(df.columns):
            col_str = str(col)
            for pat in patterns:
                if pat in col_str:
                    indices.append(i)
                    break
        return indices

    def _merge_rules(self, override: Optional[Dict]) -> Dict:
        rules = self.config["default_rules"].copy()
        if override:
            rules.update({k: v for k, v in override.items() if k in rules})
        return rules
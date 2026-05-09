"""标准科目匹配器 — 基于 finance_mapping_standard.yaml 预计算映射表直接查表。"""
import re
import yaml
from typing import Dict, Optional, List


def _normalize_raw(text: str) -> str:
    """规范化原始指标文本，消除空格差异。"""
    return re.sub(r'\s+', ' ', text.strip())


class StandardAccountMatcher:
    """标准科目匹配器 — YAML 查表式匹配"""

    def __init__(self, yaml_path: str, report_type_names: Optional[Dict] = None):
        self.report_type_names = report_type_names or {}
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # (清理后名称, 报表分区) → [mapping rows]
        self._primary_index: Dict[tuple, List[Dict]] = {}
        self._fallback_index: Dict[str, List[Dict]] = {}
        # 规范化原始文本 → mapping row（精确消歧）
        self._raw_index: Dict[str, Dict] = {}

        for row in data.get("row_mappings", []):
            if row.get("匹配状态") != "MATCHED":
                continue
            code = row.get("标准科目代码")
            if code is None:
                continue

            clean_name = row.get("清理后名称", "")
            category = row.get("报表分区", "")

            key = (clean_name, category)
            if key not in self._primary_index:
                self._primary_index[key] = []
            self._primary_index[key].append(row)

            if clean_name not in self._fallback_index:
                self._fallback_index[clean_name] = []
            self._fallback_index[clean_name].append(row)

            raw_key = _normalize_raw(row.get("原始项目", ""))
            if raw_key and raw_key not in self._raw_index:
                self._raw_index[raw_key] = row

    def _build_result(self, yaml_row: Dict) -> Dict:
        path = yaml_row.get("标准科目路径", "")
        account_name = path.split(" > ")[-1] if path else yaml_row.get("清理后名称", "")

        return {
            "account_code": yaml_row["标准科目代码"],
            "account_name": account_name,
            "report_type": yaml_row["报表分区"],
            "standard_path": path,
            "data_type": yaml_row.get("数据类型", "TOTAL"),
        }

    def match(self, row: Dict) -> Optional[Dict]:
        # 0. 用原始文本精确查表（消除同名消歧依赖 full_path）
        indicator_raw = row.get("indicator_raw", "")
        if indicator_raw:
            raw_key = _normalize_raw(indicator_raw)
            yaml_row = self._raw_index.get(raw_key)
            if yaml_row:
                return self._build_result(yaml_row)

        clean_name = row.get("indicator_clean", "")
        if not clean_name:
            return None

        report_category = row.get("report_category", "")

        # 1. (名称 + 报表分区) 查主索引
        key = (clean_name, report_category)
        candidates = self._primary_index.get(key, [])
        if candidates:
            return self._build_result(candidates[0])

        # 2. 仅按名称查回退索引
        candidates = self._fallback_index.get(clean_name, [])
        if candidates:
            return self._build_result(candidates[0])

        return None

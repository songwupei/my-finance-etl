"""标准科目匹配器 — thin wrapper over polars-etl-kit NameMatcher.

Leverages polars-etl-kit's three-tier matching + optional Levenshtein fuzzy
fallback while keeping full backward compatibility with the existing
``account_code`` / ``account_name`` / ``report_type`` return format.
"""

import re
from typing import Dict, Optional

from polars_etl_kit.matching.matcher import NameMatcher


def _normalize_raw(text: str) -> str:
    """规范化原始指标文本，消除空格差异。"""
    return re.sub(r"\s+", " ", text.strip())


class StandardAccountMatcher:
    """标准科目匹配器 — polars-etl-kit NameMatcher wrapper.

    Uses NameMatcher with Chinese field-name mapping and enables
    Levenshtein fuzzy matching for typo-tolerant lookups.
    """

    # Field-name mapping: internal name → YAML field name
    _FIELD_MAP = {
        "raw_text": "原始项目",
        "clean_name": "清理后名称",
        "category": "报表分区",
        "code": "标准科目代码",
        "name": "标准科目名称",
        "path": "标准科目路径",
    }

    # Return-key mapping: polars-etl-kit key → legacy key
    _RETURN_MAP = {
        "code": "account_code",
        "name": "account_name",
        "category": "report_type",
        "path": "standard_path",
    }

    def __init__(self, yaml_path: str, report_type_names: Optional[Dict] = None):
        self.report_type_names = report_type_names or {}

        # Initialize polars-etl-kit NameMatcher with Chinese field config
        self._matcher = NameMatcher(
            yaml_path,
            enable_fuzzy=True,
            fuzzy_threshold=0.8,
            status_field="匹配状态",
            status_matched_value="MATCHED",
            raw_field=self._FIELD_MAP["raw_text"],
            clean_field=self._FIELD_MAP["clean_name"],
            category_field=self._FIELD_MAP["category"],
            code_field=self._FIELD_MAP["code"],
            name_field=self._FIELD_MAP["name"],
            path_field=self._FIELD_MAP["path"],
        )

    def match(self, row: Dict) -> Optional[Dict]:
        """Match a row against the mapping table.

        Args:
            row: Dict with keys: indicator_raw, indicator_clean, report_category.

        Returns:
            Dict with account_code, account_name, report_type, standard_path,
            data_type, fuzzy_score (if fuzzy match), or None.
        """
        # Map caller field names → polars-etl-kit NameMatcher expected field names
        # NameMatcher looks for self._raw_field / self._clean_field / self._category_field
        # which are configured as Chinese YAML field names (原始项目, 清理后名称, 报表分区)
        internal = {
            self._FIELD_MAP["raw_text"]: _normalize_raw(row.get("indicator_raw", "")),
            self._FIELD_MAP["clean_name"]: row.get("indicator_clean", ""),
            self._FIELD_MAP["category"]: row.get("report_category", ""),
        }

        result = self._matcher.match(internal)
        if result is None:
            return None

        # Map polars-etl-kit keys → legacy keys
        mapped = {}
        for kit_key, legacy_key in self._RETURN_MAP.items():
            if kit_key in result:
                mapped[legacy_key] = result[kit_key]

        # Pass through data_type and fuzzy_score
        if "data_type" in result:
            mapped["data_type"] = result["data_type"]
        if "fuzzy_score" in result:
            mapped["fuzzy_score"] = result["fuzzy_score"]

        return mapped

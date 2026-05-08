import json
from typing import Dict, Any, Optional


class StandardAccountMatcher:
    """标准科目匹配器"""

    def __init__(self, json_path: str, context_rules: list = None, report_type_names: dict = None):
        with open(json_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.context_rules = context_rules or []
        self.report_type_names = report_type_names or {}
        self.cn_to_en = {v: k for k, v in self.report_type_names.items()}
        self.indexes = self._build_indexes()

    def _build_indexes(self) -> Dict:
        indexes = {
            "code": {},
            "path": {},
            "name": {},
            "alias": {},
            "node": {},
        }
        for report in self.data["reports"]:
            for acc in report["accounts"]:
                code = acc["account_code"]
                # Store account with report_type included
                acc_with_report_type = {**acc, "report_type": report["report_type"]}
                if code not in indexes["node"]:
                    indexes["node"][code] = []
                indexes["node"][code].append(acc_with_report_type)
                # 短横线编码索引
                dash_code = acc.get("account_code_dash", code.replace(".", "-"))
                indexes["code"][dash_code] = acc_with_report_type
                # 标准路径索引
                if "standard_path" in acc:
                    indexes["path"][acc["standard_path"]] = acc_with_report_type
                # 科目名称索引（纯 account_name，不含 alias）
                account_name = acc.get("account_name", "")
                if account_name:
                    if account_name not in indexes["name"]:
                        indexes["name"][account_name] = []
                    indexes["name"][account_name].append(code)
                # 别名索引（包括科目名称本身 + 额外别名）
                if account_name:
                    if account_name not in indexes["alias"]:
                        indexes["alias"][account_name] = []
                    indexes["alias"][account_name].append(code)

                # 额外别名
                for alias in acc.get("match_rules", {}).get("aliases", []):
                    if alias not in indexes["alias"]:
                        indexes["alias"][alias] = []
                    indexes["alias"][alias].append(code)
        return indexes

    def _match_by_name(self, name: str, index_key: str, report_type: str) -> Optional[Dict]:
        """在指定索引中按名称查找科目，用 report_type 消歧"""
        candidate_codes = self.indexes.get(index_key, {}).get(name, [])
        if not candidate_codes:
            return None
        # 收集所有候选科目（一个 code 可能对应多条不同 report_type 的记录）
        candidates = []
        for code in candidate_codes:
            candidates.extend(self.indexes["node"].get(code, []))
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # 多个同名科目 → 用 report_type 消歧
        for acc in candidates:
            if report_type and acc.get("report_type") == report_type:
                return acc
        # report_type 为空时 → 用 account_name 精确匹配
        if not report_type and name:
            for acc in candidates:
                if acc.get("account_name") == name:
                    return acc
        # 仍无法消歧 → 返回第一个
        return candidates[0]

    def match(self, row: Dict) -> Optional[Dict]:
        """执行多级匹配，返回匹配到的科目节点"""
        top_level_name = row.get("top_level_account_name", "")
        report_category = row.get("report_category", "")
        report_type = self.cn_to_en.get(report_category, "")

        # 0a. 优先匹配 account_name（纯科目名）
        if top_level_name:
            result = self._match_by_name(top_level_name, "name", report_type)
            if result:
                return result

        # 0b. 其次匹配 alias（含科目名 + 额外别名）
        if top_level_name:
            result = self._match_by_name(top_level_name, "alias", report_type)
            if result:
                return result

        # 1. 精确路径匹配（直接路径匹配，跳过编号匹配）
        full_path = row.get("full_path")
        if full_path and full_path in self.indexes["path"]:
            return self.indexes["path"][full_path]

        # 2. 上下文规则匹配
        clean_name = row.get("indicator_clean")
        for rule in self.context_rules:
            if rule["raw_indicator"] == clean_name:
                if rule["parent_path_pattern"] in full_path:
                    target_code = rule["target_account_code"]
                    candidates = self.indexes["node"].get(target_code, [])
                    if candidates:
                        for acc in candidates:
                            if report_type and acc.get("report_type") == report_type:
                                return acc
                        return candidates[0]

        # 3. 别名+父级校验
        candidate_codes = self.indexes["alias"].get(clean_name, [])
        best_match = None
        best_priority = -1
        for code in candidate_codes:
            for acc in self.indexes["node"].get(code, []):
                priority = acc.get("match_rules", {}).get("match_priority", 0)
                if priority > best_priority:
                    best_priority = priority
                    best_match = acc
        return best_match
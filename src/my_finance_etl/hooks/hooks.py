import re
import os
import hashlib
import logging
from pathlib import Path
from calendar import monthrange
from typing import Dict, Any, List

import yaml
from kedro.framework.hooks import hook_impl
from kedro.io import DataCatalog
from kedro.config import OmegaConfigLoader
from kedro.framework.project import settings


class DynamicExcelLoaderHooks:
    """扫描月度文件夹，正则提取元数据，动态注册Excel数据集"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _is_enabled(self, data_source: dict, key: str) -> bool:
        """检查数据源是否启用。环境变量 > parameters.yml > 默认 True"""
        env_var = f"KEDRO_{key.upper()}_SCAN"
        env_val = os.environ.get(env_var)
        if env_val is not None:
            return env_val.lower() in ("1", "true", "yes")
        return data_source.get(key, True)

    @hook_impl
    def after_catalog_created(
        self,
        catalog: DataCatalog,
        conf_catalog: Dict[str, Any],
        conf_creds: Dict[str, Any],
    ) -> None:
        config_loader = OmegaConfigLoader(conf_source=settings.CONF_SOURCE)
        params = config_loader["parameters"]

        base_path = Path(params["data_source"]["base_path"])
        data_source = params["data_source"]

        # --- 财务数据扫描 ---
        if self._is_enabled(data_source, "enable_finance"):
            finance_config_path = Path(settings.CONF_SOURCE) / "base" / "finance_loader.yml"
            with open(finance_config_path, 'r') as f:
                finance_config = yaml.safe_load(f)
            month_pattern = data_source["month_folder_pattern"]
            excel_files = self._scan_excel_files(base_path, month_pattern, finance_config)
            self._register_datasets(catalog, excel_files, prefix="raw_")
            self.logger.info(f"Finance scan: {len(excel_files)} files registered")
        else:
            self.logger.info("Finance scan disabled (enable_finance=false)")

        # --- 司库数据扫描 ---
        if self._is_enabled(data_source, "enable_treasury"):
            treasury_config_path = Path(settings.CONF_SOURCE) / "base" / "treasury_loader.yml"
            try:
                with open(treasury_config_path, 'r') as f:
                    treasury_config = yaml.safe_load(f)
                treasury_month_pattern = data_source.get(
                    "treasury_month_folder_pattern",
                    treasury_config.get("month_folder_pattern", "{year}年{month}月司库账户数据"),
                )
                treasury_files = self._scan_treasury_files(base_path, treasury_month_pattern, treasury_config)
                self._register_datasets(catalog, treasury_files, prefix="treasury_")
                self.logger.info(f"Treasury scan: {len(treasury_files)} files registered")
            except FileNotFoundError:
                self.logger.info("treasury_loader.yml not found, skipping treasury scan")
        else:
            self.logger.info("Treasury scan disabled (enable_treasury=false)")

        # 注入 catalog 引用供 pipeline 使用
        from kedro.io import MemoryDataset
        catalog_ref_dataset = MemoryDataset(data=catalog)
        catalog._datasets["catalog"] = catalog_ref_dataset
        self.logger.info("Added 'catalog' dataset reference for pipeline access")

    # ==================== 通用方法 ====================

    def _register_datasets(self, catalog: DataCatalog, file_infos: List[Dict], prefix: str) -> None:
        """将文件信息列表注册为 catalog 数据集"""
        for file_info in file_infos:
            dataset_name = self._generate_dataset_name(file_info, prefix)
            dataset_config = self._create_dataset_config(file_info)
            try:
                from kedro.io.core import AbstractDataset
                dataset = AbstractDataset.from_config(dataset_name, dataset_config)
                catalog._datasets[dataset_name] = dataset
                self.logger.info(f"Added dataset: {dataset_name}")
            except Exception as e:
                self.logger.error(f"Failed to add dataset {dataset_name}: {e}")

    def _generate_dataset_name(self, file_info: Dict, prefix: str = "raw_") -> str:
        month_clean = file_info["month_folder"].replace(" ", "_")
        if prefix == "treasury_":
            business_type = file_info.get("business_type", "unknown")
            file_type = file_info.get("file_type", "unknown")
            date = file_info.get("date", "")
            if date:
                return f"treasury_{business_type}_{file_type}_{date}_{month_clean}"
            return f"treasury_{business_type}_{file_type}_{month_clean}"
        return f"raw_{file_info['code']}_{file_info['suffix']}_{month_clean}"

    def _create_dataset_config(self, file_info: Dict) -> Dict:
        is_treasury = "business_type" in file_info
        config = {
            "type": "pandas.ExcelDataset",
            "filepath": file_info["path"],
            "load_args": {
                "sheet_name": None,
                "engine": "openpyxl",
                "header": 1 if is_treasury else None,
            },
            "metadata": {
                "unit": file_info.get("unit"),
                "code": file_info.get("code"),
                "suffix": file_info.get("suffix"),
                "period": file_info.get("period"),
                "entity_report_id": file_info.get("entity_report_id"),
            },
        }
        if "business_type" in file_info:
            config["metadata"]["business_type"] = file_info["business_type"]
        if "file_type" in file_info:
            config["metadata"]["file_type"] = file_info["file_type"]
        return config

    def _parse_period_end_date(self, folder_name: str) -> str:
        """从文件夹名解析月末日期，如 '2026年2月司库财务数据' -> '2026-02-28'"""
        match = re.search(r"(\d{4})年(\d{1,2})月", folder_name)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            last_day = monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-{last_day:02d}"
        return None

    def _match_month_folder(self, folder_name: str, pattern: str) -> bool:
        """检查文件夹名是否符合模式。将 {year}/{month} 模板转为正则匹配。"""
        if not pattern:
            return self._parse_period_end_date(folder_name) is not None
        escaped = re.escape(pattern)
        regex = escaped.replace(r"\{year\}", r"\d{4}").replace(r"\{month\}", r"\d{1,2}")
        return bool(re.match(regex, folder_name))

    def _parse_filename(self, filename: str, patterns: List[Dict]) -> Dict:
        """用配置的正则模式解析文件名"""
        for pattern_config in patterns:
            match = re.match(pattern_config["regex"], filename)
            if match:
                result = {}
                for key, template in pattern_config["mapping"].items():
                    result[key] = template.format(**match.groupdict())
                return result
        return {"unit": "unknown", "code": None, "suffix": "unknown"}

    # ==================== 财务数据扫描 ====================

    def _scan_excel_files(self, base_path: Path, month_pattern: str, config: dict) -> List[Dict]:
        """扫描财务 Excel 文件"""
        files = []
        patterns = config["file_name_pattern"]["patterns"]

        for month_folder in base_path.glob("*"):
            if not month_folder.is_dir():
                continue
            if not self._match_month_folder(month_folder.name, month_pattern):
                continue

            period_end_date = self._parse_period_end_date(month_folder.name)

            for excel_file in month_folder.glob("*.xlsx"):
                file_info = self._parse_filename(excel_file.name, patterns)
                if file_info:
                    file_info["path"] = str(excel_file)
                    file_info["month_folder"] = month_folder.name
                    file_info["period"] = period_end_date
                    hash_input = f"{file_info['code']}|{file_info['suffix']}"
                    file_info["entity_report_id"] = hashlib.md5(hash_input.encode()).hexdigest()[:8]
                    files.append(file_info)
        return files

    # ==================== 司库数据扫描 ====================

    def _scan_treasury_files(self, base_path: Path, month_pattern: str, config: dict) -> List[Dict]:
        """扫描司库 Excel 文件（支持多业务类型）"""
        files = []
        business_types = config.get("business_types", {})

        for month_folder in base_path.glob("*"):
            if not month_folder.is_dir():
                continue
            if not self._match_month_folder(month_folder.name, month_pattern):
                continue

            period_end_date = self._parse_period_end_date(month_folder.name)

            for business_type, bt_config in business_types.items():
                bt_patterns = bt_config.get("files", [])
                for excel_file in month_folder.glob("*.xlsx"):
                    file_info = self._parse_treasury_filename(excel_file.name, bt_patterns)
                    if file_info:
                        file_info["path"] = str(excel_file)
                        file_info["month_folder"] = month_folder.name
                        # 优先用文件名中的日期，否则用月份文件夹推算的月末
                        file_date = file_info.get("date", "")
                        if file_date and len(file_date) == 8:
                            file_info["period"] = f"{file_date[:4]}-{file_date[4:6]}-{file_date[6:8]}"
                        else:
                            file_info["period"] = period_end_date
                        file_info["business_type"] = business_type
                        file_info["code"] = None
                        file_info["suffix"] = None
                        file_info["entity_report_id"] = None  # processing 阶段匹配
                        files.append(file_info)

        self.logger.info(f"Scanned {len(files)} treasury files")
        return files

    def _parse_treasury_filename(self, filename: str, patterns: List[Dict]) -> Dict:
        """用司库配置的正则解析文件名，提取 named groups (如 date)"""
        for pattern_config in patterns:
            match = re.match(pattern_config["regex"], filename)
            if match:
                result = dict(match.groupdict())  # e.g. {"date": "20260424"}
                for key, template in pattern_config.get("mapping", {}).items():
                    result[key] = template.format(**match.groupdict())
                if "file_type" in pattern_config:
                    result["file_type"] = pattern_config["file_type"]
                return result
        return None

    # ==================== hooks.yml 执行 ====================

    @hook_impl
    def after_node_run(
        self,
        node,
        catalog: DataCatalog,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        is_async: bool = False,
    ) -> None:
        """节点完成后执行 hooks.yml 中配置的命令。"""
        self._run_hooks_for_node("after_nodes", node.name)

    def _run_hooks_for_node(self, hook_type: str, node_name: str):
        """从 conf/base/hooks.yml 加载并执行特定节点的 hook 命令。"""
        hooks_config_path = Path(settings.CONF_SOURCE) / "base" / "hooks.yml"
        if not hooks_config_path.exists():
            return

        try:
            with open(hooks_config_path, "r") as f:
                config = yaml.safe_load(f)
        except Exception:
            return

        node_hooks = config.get("hooks", {}).get(hook_type, {}).get(node_name, [])
        if not node_hooks:
            return

        import subprocess

        for cmd_spec in node_hooks:
            if isinstance(cmd_spec, str):
                cmd = cmd_spec
                cwd = "."
            elif isinstance(cmd_spec, dict):
                cmd = cmd_spec.get("cmd", "")
                cwd = cmd_spec.get("cwd", ".")
            else:
                continue

            if not cmd:
                continue

            self.logger.info(f"Running hook [{hook_type}/{node_name}]: {cmd}")
            try:
                subprocess.run(
                    cmd,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
            except Exception as e:
                self.logger.warning(f"Hook command failed: {e}")

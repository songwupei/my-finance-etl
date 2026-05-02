"""Project settings for Kedro."""
from pathlib import Path

from .hooks.hooks import DynamicExcelLoaderHooks

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONF_SOURCE = PROJECT_ROOT / "conf"
PACKAGE_NAME = "my_finance_etl"

# Project metadata
PROJECT_NAME = "my_finance_etl"
PROJECT_VERSION = "0.1.0"

# Kedro settings
PIPELINE_REGISTRY = f"{PACKAGE_NAME}.pipeline_registry.register_pipelines"
HOOKS = [
    DynamicExcelLoaderHooks(),
]
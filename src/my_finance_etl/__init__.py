"""My Finance ETL package."""

from .hooks.hooks import DynamicExcelLoaderHooks

__version__ = "0.1.0"


def get_hooks():
    """Get hooks for this project."""
    return [DynamicExcelLoaderHooks()]
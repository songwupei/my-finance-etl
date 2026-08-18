"""File-level MD5 cache — thin wrapper over polars-etl-kit's FileCache.

Adds project-specific path helpers (base_info, report_data, treasury)
while delegating all core logic to polars_etl_kit.excel.cache.FileCache.
"""

from polars_etl_kit.excel.cache import FileCache as _FileCache

# 司库缓存 schema 版本；解析/加载方式变化时 +1，自动作废旧缓存
TREASURY_CACHE_VERSION = 2


class FileCache(_FileCache):
    """MD5-based file cache, extended with project-specific path helpers.

    Inherits all core functionality (get/put/stats/compute_md5) from
    polars_etl_kit, and adds backwards-compatible path methods:

        cache.base_info_path(key)    → cache.get_path(key, 'base_info')
        cache.report_data_path(key)  → cache.get_path(key, 'report_data')
        cache.treasury_path(key)     → cache.get_path(key, 'treasury')
    """

    def base_info_path(self, cache_key: str):
        return self.get_path(cache_key, "base_info")

    def report_data_path(self, cache_key: str):
        return self.get_path(cache_key, "report_data")

    def treasury_path(self, cache_key: str):
        return self._cache_dir / f"{cache_key}_treasury_v{TREASURY_CACHE_VERSION}.parquet"

"""File-level MD5 cache for skipping unchanged Excel files.

Stores an index.json mapping source file paths to their MD5 and cache key.
Cached parquet files live alongside the index, keyed by MD5 prefix.
"""

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileCache:
    """MD5-based file cache for Excel ingestion.

    On get(): computes the current MD5 of the source file and checks
    whether cached parquet outputs still match.  Returns the cache_key
    (MD5 prefix used to name the parquet files) on hit, None on miss.

    Thread-safe: all index reads/writes are guarded by a lock.
    """

    def __init__(self, cache_dir: str):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._cache_dir / "index.json"
        self._lock = threading.Lock()
        self._index: dict = self._load_index()

    # ---- public API ----

    def get(self, source_path: str) -> Optional[str]:
        """Return cache_key if the source file is unchanged, else None."""
        src = Path(source_path)
        if not src.exists():
            return None

        current_md5 = self.compute_md5(source_path)
        with self._lock:
            entry = self._index.get(str(src))
            if entry and entry.get("md5") == current_md5:
                cache_key = entry["cache_key"]
                # verify cached files actually exist on disk
                if self._cache_files_exist(cache_key):
                    return cache_key
        return None

    def put(self, source_path: str) -> str:
        """Record cache entry for source_path. Returns the new cache_key."""
        current_md5 = self.compute_md5(source_path)
        cache_key = current_md5[:12]
        with self._lock:
            self._index[str(Path(source_path))] = {
                "md5": current_md5,
                "cache_key": cache_key,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_index()
        return cache_key

    def base_info_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}_base_info.parquet"

    def report_data_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}_report_data.parquet"

    def treasury_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}_treasury.parquet"

    @staticmethod
    def compute_md5(filepath: str) -> str:
        """Compute MD5 hex digest of a file (8 KiB chunked read)."""
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ---- batch helpers for logging ----

    def stats(self) -> dict:
        """Return {total_entries, cache_dir} for summary logging."""
        with self._lock:
            return {
                "total_entries": len(self._index),
                "cache_dir": str(self._cache_dir),
            }

    # ---- internals ----

    def _cache_files_exist(self, cache_key: str) -> bool:
        """True if at least one expected parquet file exists for this key."""
        # finance produces two files, treasury produces one — check both patterns
        return (
            self.base_info_path(cache_key).exists()
            or self.report_data_path(cache_key).exists()
            or self.treasury_path(cache_key).exists()
        )

    def _load_index(self) -> dict:
        if self._index_path.exists():
            try:
                with open(self._index_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupt cache index, starting fresh")
                return {}
        return {}

    def _save_index(self) -> None:
        try:
            with open(self._index_path, "w") as f:
                json.dump(self._index, f, indent=2, ensure_ascii=False, default=str)
        except OSError as e:
            logger.warning("Failed to save cache index: %s", e)

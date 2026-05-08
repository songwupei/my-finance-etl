"""Schema Registry — 数据标准运行时接口.

从 YAML 标准文件加载表/字段定义，提供 DDL 生成、中英文翻译、数据校验。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ============================================================
# 数据类
# ============================================================

@dataclass
class FieldDef:
    """字段定义."""
    name: str
    cn_name: str
    dtype: str          # VARCHAR / DECIMAL / INTEGER / DOUBLE / DATE / TIMESTAMP / BOOLEAN
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    nullable: bool = True
    default: str | None = None
    description: str = ""
    example: str = ""
    checks: list[dict] = field(default_factory=list)

    def duckdb_type(self) -> str:
        """生成 DuckDB 列类型字符串."""
        dt = self.dtype.upper()
        if dt in ("VARCHAR", "STRING"):
            n = self.length or 255
            return f"VARCHAR({n})"
        if dt == "DECIMAL":
            p = self.precision or 18
            s = self.scale or 2
            return f"DECIMAL({p},{s})"
        if dt in ("INTEGER", "INT", "BIGINT"):
            return "BIGINT"
        if dt == "DOUBLE":
            return "DOUBLE"
        if dt == "BOOLEAN":
            return "BOOLEAN"
        if dt == "DATE":
            return "DATE"
        if dt == "TIMESTAMP":
            return "TIMESTAMP"
        return dt

    def polars_type(self) -> Any:
        """返回对应的 Polars 数据类型."""
        import polars as pl
        dt = self.dtype.upper()
        if dt in ("VARCHAR", "STRING"):
            return pl.Utf8
        if dt in ("INTEGER", "INT", "BIGINT"):
            return pl.Int64
        if dt == "DECIMAL":
            return pl.Float64  # polars Decimal support varies
        if dt == "DOUBLE":
            return pl.Float64
        if dt == "BOOLEAN":
            return pl.Boolean
        if dt == "DATE":
            return pl.Date
        if dt == "TIMESTAMP":
            return pl.Datetime
        return pl.Utf8


@dataclass
class ForeignKey:
    """外键关系."""
    field: str
    ref_table: str
    ref_field: str


@dataclass
class TableSchema:
    """表级 schema 定义."""
    table_name: str
    table_cn: str
    description: str = ""
    row_count: int | None = None
    temporal_type: str = ""
    fields: list[FieldDef] = field(default_factory=list)
    primary_key: str | None = None
    indexes: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)

    def get_field(self, name: str) -> FieldDef | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def get_field_by_cn(self, cn_name: str) -> FieldDef | None:
        for f in self.fields:
            if f.cn_name == cn_name:
                return f
        return None

    @property
    def column_names(self) -> list[str]:
        return [f.name for f in self.fields]

    @property
    def required_columns(self) -> list[str]:
        return [f.name for f in self.fields if not f.nullable]


@dataclass
class ViewDef:
    """视图定义（参考用）."""
    view_name: str
    view_cn: str
    description: str = ""
    source_tables: list[str] = field(default_factory=list)
    key_columns: list[str] = field(default_factory=list)


# ============================================================
# Schema Registry
# ============================================================

class SchemaRegistry:
    """Schema Registry — 从 YAML 加载，提供查询/DDL/校验."""

    def __init__(self, *yaml_paths: str):
        self._tables: dict[str, TableSchema] = {}
        self._views: dict[str, ViewDef] = {}
        self._relationships: list[dict] = []
        self._meta: dict = {}

        for path in yaml_paths:
            self._load_yaml(Path(path))

    # ---- 加载 ----

    def _load_yaml(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if "meta" in data:
            self._meta.update(data["meta"])

        for raw in data.get("dimensions", []):
            table = self._parse_table(raw)
            self._tables[table.table_name] = table

        for raw in data.get("facts", []):
            table = self._parse_table(raw)
            self._tables[table.table_name] = table

        for raw in data.get("views", []):
            view = ViewDef(
                view_name=raw.get("view_name", ""),
                view_cn=raw.get("view_cn", ""),
                description=raw.get("description", ""),
                source_tables=raw.get("source_tables", []),
                key_columns=raw.get("key_columns", []),
            )
            self._views[view.view_name] = view

        self._relationships.extend(data.get("relationships", []))

    def _parse_table(self, raw: dict) -> TableSchema:
        fields = []
        for f in raw.get("fields", []):
            fields.append(FieldDef(
                name=f["name"],
                cn_name=f.get("cn_name", ""),
                dtype=f.get("dtype", "VARCHAR"),
                length=f.get("length"),
                precision=f.get("precision"),
                scale=f.get("scale"),
                nullable=f.get("nullable", True),
                default=f.get("default"),
                description=f.get("description", ""),
                example=f.get("example", ""),
                checks=f.get("checks", []),
            ))

        fks = []
        for fk in raw.get("foreign_keys", []):
            fks.append(ForeignKey(
                field=fk["field"],
                ref_table=fk["ref_table"],
                ref_field=fk["ref_field"],
            ))

        return TableSchema(
            table_name=raw["table_name"],
            table_cn=raw.get("table_cn", ""),
            description=raw.get("description", ""),
            row_count=raw.get("row_count"),
            temporal_type=raw.get("temporal_type", ""),
            fields=fields,
            primary_key=raw.get("primary_key"),
            indexes=raw.get("indexes", []),
            foreign_keys=fks,
        )

    # ---- 查询 ----

    @property
    def table_names(self) -> list[str]:
        return list(self._tables.keys())

    @property
    def dimension_tables(self) -> list[str]:
        """以 dim_ 开头的表名."""
        return [n for n in self._tables if n.startswith("dim_")]

    @property
    def fact_tables(self) -> list[str]:
        """以 fact_ 开头的表名."""
        return [n for n in self._tables if n.startswith("fact_")]

    def get_table_schema(self, table_name: str) -> TableSchema:
        if table_name not in self._tables:
            raise KeyError(f"Table '{table_name}' not found. Available: {list(self._tables.keys())}")
        return self._tables[table_name]

    def get_field_def(self, table_name: str, field_name: str) -> FieldDef:
        table = self.get_table_schema(table_name)
        f = table.get_field(field_name)
        if f is None:
            raise KeyError(f"Field '{field_name}' not found in table '{table_name}'")
        return f

    # ---- 翻译 ----

    def cn_to_en(self, table_name: str, cn_name: str) -> str:
        """中文列名 → 英文列名."""
        table = self.get_table_schema(table_name)
        f = table.get_field_by_cn(cn_name)
        if f:
            return f.name
        return cn_name

    def en_to_cn(self, table_name: str, en_name: str) -> str:
        """英文列名 → 中文列名."""
        f = self.get_field_def(table_name, en_name)
        return f.cn_name or en_name

    # ---- DDL 生成 ----

    def generate_duckdb_ddl(self, table_name: str) -> str:
        """生成单表 DuckDB CREATE TABLE DDL."""
        table = self.get_table_schema(table_name)

        lines = [f"-- {table.table_cn}: {table.description}"]
        lines.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")

        col_defs = []
        total_items = len(table.fields) + (1 if table.primary_key else 0)
        item_idx = 0
        for f in table.fields:
            null = "" if f.nullable else " NOT NULL"
            comma = "," if item_idx < total_items - 1 else ""
            col_defs.append(f"    {f.name} {f.duckdb_type()}{null}{comma}  -- {f.cn_name}")
            item_idx += 1

        if table.primary_key:
            comma = "," if item_idx < total_items - 1 else ""
            col_defs.append(f"    PRIMARY KEY ({table.primary_key}){comma}")

        lines.append("\n".join(col_defs))
        lines.append(");")
        return "\n".join(lines)

    def generate_all_ddl(self) -> str:
        """生成所有表的 DuckDB DDL."""
        blocks = []
        for name in self._tables:
            blocks.append(self.generate_duckdb_ddl(name))
            blocks.append("")
        return "\n".join(blocks)

    def generate_index_ddl(self, table_name: str) -> list[str]:
        """生成单表索引 DDL."""
        table = self.get_table_schema(table_name)
        statements = []
        for col in table.indexes:
            statements.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{col} "
                f"ON {table_name}({col});"
            )
        return statements

    # ---- 校验 ----

    def validate_schema(self, table_name: str, column_names: list[str]) -> dict:
        """校验 DataFrame 列是否与 schema 一致.

        Returns:
            {"missing_required": [...], "extra": [...], "type_mismatches": [...], "valid": bool}
        """
        table = self.get_table_schema(table_name)
        actual = set(column_names)
        expected = set(table.column_names)
        required = set(table.required_columns)

        missing_required = [c for c in required if c not in actual]
        extra = [c for c in actual if c not in expected]

        return {
            "table": table_name,
            "missing_required": missing_required,
            "extra": extra,
            "valid": len(missing_required) == 0,
        }

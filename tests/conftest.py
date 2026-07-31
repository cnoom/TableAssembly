"""测试公用 helper:构造 TableSchema / FieldDef / DataRow。"""
from __future__ import annotations

from app.schema import FieldDef, DataRow, TableSchema


def make_field(
    name: str,
    type_code: int,
    sep: str = "",
    side: str = "both",
) -> FieldDef:
    return FieldDef(name=name, type_code=type_code, sep=sep, desc="", side=side)


def make_schema(
    name: str = "Test",
    fields: list[FieldDef] | None = None,
    rows: list[tuple] | None = None,
) -> TableSchema:
    s = TableSchema(name=name, file_name=f"{name}.xlsx")
    s.fields = fields or []
    for row_index, vals in (rows or []):
        s.rows.append(DataRow(key=vals[0] if vals else None, values=list(vals), row_index=row_index))
    return s

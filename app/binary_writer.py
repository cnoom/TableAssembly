"""紧凑二进制打包器。与 codegen/cs.py 生成的 TableReader 严格对应。

文件布局(全部小端):
    magic       4B   "ETBL"
    version     2B   = 1
    rowCount    4B   数据行数
    fieldCount  2B   本包字段数(已按归属过滤)
    [数据区]    按行、按字段顺序写入

字段写入规则:
    int        4B 小端
    float      4B 小端(IEEE754)
    bool       1B  (0/1)
    string     2B 长度(小端) + UTF-8 字节
    数组       4B 元素个数 + 逐元素(按上述标量规则)
"""
from __future__ import annotations

import struct
from typing import Any

from . import schema as S

MAGIC = b"ETBL"
VERSION = 1


class BinaryWriter:
    def __init__(self) -> None:
        self.buf = bytearray()

    # —— 基础写法 ——
    def write_bytes(self, b: bytes) -> None:
        self.buf.extend(b)

    def write_int16(self, v: int) -> None:
        self.buf.extend(struct.pack("<h", v))

    def write_uint16(self, v: int) -> None:
        self.buf.extend(struct.pack("<H", v))

    def write_int32(self, v: int) -> None:
        self.buf.extend(struct.pack("<i", v))

    def write_single(self, v: float) -> None:
        self.buf.extend(struct.pack("<f", v))

    def write_bool(self, v: bool) -> None:
        self.buf.append(1 if v else 0)

    def write_string(self, s: str) -> None:
        data = s.encode("utf-8")
        if len(data) > 0xFFFF:
            raise ValueError(f"字符串过长({len(data)} 字节),超过 2B 长度上限: {s[:32]!r}...")
        self.write_uint16(len(data))
        self.buf.extend(data)

    # —— 标量/数组 ——
    def write_scalar(self, v: Any, type_code: int) -> None:
        if type_code == S.T_INT:
            self.write_int32(int(v))
        elif type_code == S.T_FLOAT:
            self.write_single(float(v))
        elif type_code == S.T_BOOL:
            self.write_bool(bool(v))
        elif type_code == S.T_STRING:
            self.write_string("" if v is None else str(v))
        else:
            raise ValueError(f"write_scalar 不接受数组类型 code={type_code}")

    def write_array(self, items: list[Any], elem_code: int) -> None:
        items = items or []
        self.write_int32(len(items))
        for it in items:
            self.write_scalar(it, elem_code)


def write_field_value(w: BinaryWriter, value: Any, field: S.FieldDef) -> None:
    """按字段类型写一个值。"""
    if field.is_array:
        if value is None:
            value = []
        w.write_array(list(value), field.element_type)
    else:
        # None 的标量按默认值兜底,避免崩溃
        if value is None:
            value = _default_scalar(field.type_code)
        w.write_scalar(value, field.type_code)


def _default_scalar(type_code: int) -> Any:
    return {S.T_INT: 0, S.T_FLOAT: 0.0, S.T_BOOL: False, S.T_STRING: ""}.get(type_code, 0)


def build_binary(schema: S.TableSchema, fields: list[S.FieldDef], rows: list[S.DataRow]) -> bytes:
    """把一张表按指定字段集合(已按归属过滤)打包为二进制。

    rows 为要写入的数据行(通常等于 schema.rows,但传入便于未来分页/过滤)。
    """
    w = BinaryWriter()
    w.write_bytes(MAGIC)
    w.write_uint16(VERSION)
    w.write_int32(len(rows))
    w.write_uint16(len(fields))

    # 建立字段 -> 在 schema.fields 中的索引,以便从 row.values 取值
    name_to_idx = {f.name: i for i, f in enumerate(schema.fields)}

    for drow in rows:
        for fdef in fields:
            idx = name_to_idx.get(fdef.name)
            value = drow.values[idx] if idx is not None and idx < len(drow.values) else None
            write_field_value(w, value, fdef)

    return bytes(w.buf)

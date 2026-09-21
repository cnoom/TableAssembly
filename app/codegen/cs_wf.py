"""WFFramework 感知的 C# 生成器（cs_wf）。

与通用 cs 生成器的差异（稳定面契约：框架仓 specs/027-excel-table-pipeline/contracts/cswf-codegen-contract.md）:
    {Table}/{Table}Data.cs    POCO + 同步 Read(TableBinaryReader)（类型来自框架包）
    {Table}/{Table}Table.cs   薄壳：[ConfigTable(address)] + 继承 TableBase<TData, TKey> + 三个 override
    TableReader.cs            不生成（框架 Runtime 提供；shared_files 返回空）

二进制读写口径与 binary_writer.py 严格对应（同 cs）；生成代码保持 C# 9。
"""
from __future__ import annotations

from typing import List

from .. import schema as S
from ..schema import FieldDef, TableSchema
from .base import OutputFile

# type_code -> C# 类型/读取法（TableBinaryReader 方法名与 cs 版 TableReader 一致）
_CS_SCALAR = {
    S.T_INT: "int",
    S.T_FLOAT: "float",
    S.T_BOOL: "bool",
    S.T_STRING: "string",
}
_CS_ARRAY = {
    S.T_INT_ARRAY: "int[]",
    S.T_FLOAT_ARRAY: "float[]",
    S.T_BOOL_ARRAY: "bool[]",
    S.T_STRING_ARRAY: "string[]",
}
_CS_READER = {
    S.T_INT: "ReadInt32",
    S.T_FLOAT: "ReadSingle",
    S.T_BOOL: "ReadBoolean",
    S.T_STRING: "ReadString",
    S.T_INT_ARRAY: "ReadInt32Array",
    S.T_FLOAT_ARRAY: "ReadSingleArray",
    S.T_BOOL_ARRAY: "ReadBooleanArray",
    S.T_STRING_ARRAY: "ReadStringArray",
}

# 框架运行时命名空间（跨仓稳定面，勿改——改动须与框架仓同批）
FRAMEWORK_NS = "CNoom.WFFramework.Modules.Config"


def _cs_type(fdef: FieldDef) -> str:
    return _CS_ARRAY[fdef.type_code] if fdef.is_array else _CS_SCALAR[fdef.type_code]


def _reader_call(fdef: FieldDef) -> str:
    return f"r.{_CS_READER[fdef.type_code]}()"


class CsWfGenerator:
    """绑定命名空间后的 cs_wf 生成器实例（供 WFFramework 宿主工程）。"""

    name = "cs_wf"

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace or "GameData"

    def generate(
        self,
        schema: TableSchema,
        side: str,
        fields: List[FieldDef],
        subdirs_by_table: bool = False,
    ) -> List[OutputFile]:
        table_cls = schema.name
        data_cls = f"{table_cls}Data"
        prefix = f"{table_cls}/" if subdirs_by_table else ""
        return [
            OutputFile(
                relative_path=f"{prefix}{data_cls}.cs",
                content=self._gen_data(schema, fields, side, data_cls),
            ),
            OutputFile(
                relative_path=f"{prefix}{table_cls}Table.cs",
                content=self._gen_table(schema, fields, side, table_cls, data_cls),
            ),
        ]

    def shared_files(self) -> List[OutputFile]:
        return []  # TableReader 由框架包提供，不再生成

    # ---------------- 模板 ----------------

    def _gen_data(self, schema: TableSchema, fields: List[FieldDef], side: str, data_cls: str) -> str:
        ns = self.namespace
        field_lines: list[str] = []
        for i, fdef in enumerate(fields):
            cstype = _cs_type(fdef)
            comment = f"        /// <summary>{fdef.desc}</summary>\n" if fdef.desc else ""
            pk = "  // 主键" if i == 0 else ""
            field_lines.append(f"{comment}        public {cstype} {fdef.name};{pk}")
        fields_block = "\n".join(field_lines)

        read_lines = [f"            {fdef.name} = {_reader_call(fdef)};" for fdef in fields]
        read_block = "\n".join(read_lines) if read_lines else "            // 无字段"

        return f"""// 自动生成,请勿手动修改。来源: {schema.file_name} [{side}]
using {FRAMEWORK_NS};

namespace {ns}
{{
    /// <summary>{schema.name} 表数据 ({side})。</summary>
    public class {data_cls}
    {{
{fields_block}

        public void Read(TableBinaryReader r)
        {{
{read_block}
        }}
    }}
}}
"""

    def _gen_table(
        self, schema: TableSchema, fields: List[FieldDef], side: str,
        table_cls: str, data_cls: str,
    ) -> str:
        ns = self.namespace
        key_field = fields[0]
        key_type = _CS_SCALAR.get(key_field.type_code, "int")
        suffix = "_c" if side == "client" else "_s"

        return f"""// 自动生成,请勿手动修改。来源: {schema.file_name}
using {FRAMEWORK_NS};

namespace {ns}
{{
    [ConfigTable("{schema.name}{suffix}")]
    public sealed class {table_cls}Table : TableBase<{data_cls}, {key_type}>
    {{
        protected override short FieldCount => {len(fields)};
        protected override {data_cls} ReadRow(TableBinaryReader r) {{ var d = new {data_cls}(); d.Read(r); return d; }}
        protected override {key_type} KeyOf({data_cls} d) => d.{key_field.name};
    }}
}}
"""

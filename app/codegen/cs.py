"""C# 代码生成器。

为每张表、每个端(client/server)生成:
    {Table}/{Table}Data.cs    数据类(class + ReadAsync)
    {Table}/{Table}Table.cs   管理类(LoadAsync(byte[]) + Get/TryGet/GetAll)
以及每端共用一次的:
    TableReader.cs            纯二进制解析器(吃 byte[])

与 binary_writer.py 的写入严格对应。
"""
from __future__ import annotations

from typing import List

from .. import schema as S
from ..schema import FieldDef, TableSchema
from .base import OutputFile

# type_code -> C# 类型字符串
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


def _cs_type(fdef: FieldDef) -> str:
    return _CS_ARRAY[fdef.type_code] if fdef.is_array else _CS_SCALAR[fdef.type_code]


def _cs_key_type(fdef: FieldDef) -> str:
    return _CS_SCALAR.get(fdef.type_code, "int")


def _reader_call(fdef: FieldDef) -> str:
    return f"r.{_CS_READER[fdef.type_code]}()"


class CsGenerator:
    """绑定命名空间后的 C# 生成器实例。"""

    name = "cs"

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
        # subdirs_by_table=True 时按表名建子目录;否则平铺
        prefix = f"{table_cls}/" if subdirs_by_table else ""
        return [
            OutputFile(
                relative_path=f"{prefix}{data_cls}.cs",
                content=self._gen_data(schema, fields, side, data_cls),
            ),
            OutputFile(
                relative_path=f"{prefix}{table_cls}Table.cs",
                content=self._gen_table(schema, fields, table_cls, data_cls),
            ),
        ]

    def shared_files(self) -> List[OutputFile]:
        return [OutputFile(
            relative_path="TableReader.cs",
            content=_render_reader(self.namespace),
            is_shared=True,
        )]

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
using System.Threading.Tasks;

namespace {ns}
{{
    /// <summary>{schema.name} 表数据 ({side})。</summary>
    public class {data_cls}
    {{
{fields_block}

        public Task ReadAsync(TableReader r)
        {{
{read_block}
            return Task.CompletedTask;
        }}
    }}
}}
"""

    def _gen_table(self, schema: TableSchema, fields: List[FieldDef], table_cls: str, data_cls: str) -> str:
        ns = self.namespace
        key_field = fields[0]
        key_type = _cs_key_type(key_field)

        return f"""// 自动生成,请勿手动修改。来源: {schema.file_name}
using System.Collections.Generic;
using System.Threading.Tasks;

namespace {ns}
{{
    /// <summary>{table_cls} 表管理类。文件加载由调用方处理(Resources/Addressables/包管理...),
    /// 本类只接收已读入内存的二进制数据。</summary>
    public class {table_cls}Table
    {{
        private Dictionary<{key_type}, {data_cls}> _map;
        private List<{data_cls}> _list;

        /// <summary>从二进制数据加载。</summary>
        public async Task LoadAsync(byte[] bytes)
        {{
            var r = new TableReader(bytes);
            r.CheckMagic("ETBL");        // magic
            r.ReadInt16();                // version
            int rowCount = r.ReadInt32(); // rowCount
            r.ReadInt16();                // fieldCount(顺序已固化在本文件)

            _map  = new Dictionary<{key_type}, {data_cls}>(rowCount);
            _list = new List<{data_cls}>(rowCount);
            for (int i = 0; i < rowCount; i++)
            {{
                var d = new {data_cls}();
                await d.ReadAsync(r);
                _map[d.{key_field.name}] = d;
                _list.Add(d);
            }}
        }}

        public {data_cls} Get({key_type} id) => _map.TryGetValue(id, out var v) ? v : null;
        public bool TryGet({key_type} id, out {data_cls} v) => _map.TryGetValue(id, out v);
        public int Count => _list.Count;
        public List<{data_cls}> GetAll() => _list;
    }}
}}
"""


# 共用 TableReader:不依赖任何具体表,内容固定,仅命名空间变化
_READER_TEMPLATE = '''// 自动生成,请勿手动修改。通用二进制表读取器。
using System.Text;

namespace {NS}
{{
    /// <summary>通用二进制表读取器:仅负责解析二进制数据,文件加载由调用方自行处理。
    /// 与 ExcelToDevData 导出的 .bytes 严格对应。</summary>
    public class TableReader
    {{
        private readonly byte[] _data;
        private int _pos;

        public TableReader(byte[] data) {{ _data = data; _pos = 0; }}

        public bool CheckMagic(string magic)
        {{
            for (int i = 0; i < magic.Length; i++)
                if (_data[_pos + i] != (byte)magic[i]) return false;
            _pos += magic.Length;
            return true;
        }}

        public short ReadInt16()
        {{
            int v = _data[_pos] | (_data[_pos + 1] << 8);
            _pos += 2;
            return (short)v;
        }}

        public int ReadInt32()
        {{
            int v = _data[_pos] | (_data[_pos + 1] << 8) | (_data[_pos + 2] << 16) | (_data[_pos + 3] << 24);
            _pos += 4;
            return v;
        }}

        public float ReadSingle() => BitConverter.Int32BitsToSingle(ReadInt32());

        public bool ReadBoolean()
        {{
            bool v = _data[_pos] != 0;
            _pos += 1;
            return v;
        }}

        public string ReadString()
        {{
            short len = ReadInt16();
            string s = Encoding.UTF8.GetString(_data, _pos, len);
            _pos += len;
            return s;
        }}

        public int[] ReadInt32Array()
        {{
            int n = ReadInt32();
            int[] a = new int[n];
            for (int i = 0; i < n; i++) a[i] = ReadInt32();
            return a;
        }}

        public float[] ReadSingleArray()
        {{
            int n = ReadInt32();
            float[] a = new float[n];
            for (int i = 0; i < n; i++) a[i] = ReadSingle();
            return a;
        }}

        public bool[] ReadBooleanArray()
        {{
            int n = ReadInt32();
            bool[] a = new bool[n];
            for (int i = 0; i < n; i++) a[i] = ReadBoolean();
            return a;
        }}

        public string[] ReadStringArray()
        {{
            int n = ReadInt32();
            string[] a = new string[n];
            for (int i = 0; i < n; i++) a[i] = ReadString();
            return a;
        }}
    }}
}}
'''


def _render_reader(namespace: str) -> str:
    return _READER_TEMPLATE.replace("{NS}", namespace or "GameData")

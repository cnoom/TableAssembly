"""Java 代码生成器。

为每张表、每个端生成:
    {Table}/{Table}Data.java   数据类(class + read 方法)
    {Table}/{Table}Table.java  管理类(load(byte[]) + get/tryGet/getAll)
以及每端共用一次的:
    TableReader.java           纯二进制读取器(吃 byte[])

与 binary_writer.py 的写入严格对应:小端、无字段描述区。
读取器用 ByteBuffer.order(LITTLE_ENDIAN) 统一小端。
"""
from __future__ import annotations

from typing import List

from .. import schema as S
from ..schema import FieldDef, TableSchema
from .base import OutputFile

# type_code -> Java 类型
_J_SCALAR = {
    S.T_INT: "int",
    S.T_FLOAT: "float",
    S.T_BOOL: "boolean",
    S.T_STRING: "String",
}
_J_ARRAY = {
    S.T_INT_ARRAY: "int[]",
    S.T_FLOAT_ARRAY: "float[]",
    S.T_BOOL_ARRAY: "boolean[]",
    S.T_STRING_ARRAY: "String[]",
}
# 读取器方法名(按 type_code)
_J_READER = {
    S.T_INT: "readInt32",
    S.T_FLOAT: "readFloat32",
    S.T_BOOL: "readBoolean",
    S.T_STRING: "readString",
    S.T_INT_ARRAY: "readInt32Array",
    S.T_FLOAT_ARRAY: "readFloat32Array",
    S.T_BOOL_ARRAY: "readBooleanArray",
    S.T_STRING_ARRAY: "readStringArray",
}


def _j_type(fdef: FieldDef) -> str:
    return _J_ARRAY[fdef.type_code] if fdef.is_array else _J_SCALAR[fdef.type_code]


def _j_key_type(fdef: FieldDef) -> str:
    return _J_SCALAR.get(fdef.type_code, "int")


def _j_box_key_type(fdef: FieldDef) -> str:
    """HashMap 的装箱主键类型。"""
    return {
        S.T_INT: "Integer",
        S.T_FLOAT: "Float",
        S.T_BOOL: "Boolean",
        S.T_STRING: "String",
    }.get(fdef.type_code, "Integer")


def _reader_call(fdef: FieldDef) -> str:
    return f"r.{_J_READER[fdef.type_code]}()"


def _camel(name: str) -> str:
    """Java 字段名保持原样(小驼峰);getter/setter 名首字母大写。"""
    if not name:
        return "field"
    return name[0].upper() + name[1:]


class JavaGenerator:
    """绑定包名后的 Java 生成器实例。self.namespace 即 Java package 名。"""

    name = "java"

    def __init__(self, namespace: str) -> None:
        # Java 包名规范:全小写、段间用点。derive_namespace 只处理单段,
        # 这里把非法字符统一降级,并强制小写
        self.namespace = _sanitize_pkg(namespace or "gamedata")

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
                relative_path=f"{prefix}{data_cls}.java",
                content=self._gen_data(schema, fields, side, data_cls),
            ),
            OutputFile(
                relative_path=f"{prefix}{table_cls}Table.java",
                content=self._gen_table(schema, fields, table_cls, data_cls),
            ),
        ]

    def shared_files(self) -> List[OutputFile]:
        return [OutputFile(
            relative_path="TableReader.java",
            content=_render_reader(self.namespace),
            is_shared=True,
        )]

    # ---------------- 模板 ----------------

    def _gen_data(self, schema: TableSchema, fields: List[FieldDef], side: str, data_cls: str) -> str:
        pkg = self.namespace
        field_lines: list[str] = []
        for i, fdef in enumerate(fields):
            jtype = _j_type(fdef)
            comment = f"    /** {fdef.desc} */\n" if fdef.desc else ""
            pk = "  // 主键" if i == 0 else ""
            field_lines.append(f"{comment}    public {jtype} {fdef.name};{pk}")
        fields_block = "\n".join(field_lines)

        read_lines = [f"        this.{fdef.name} = {_reader_call(fdef)};" for fdef in fields]
        read_block = "\n".join(read_lines) if read_lines else "        // 无字段"

        return _DATA_TEMPLATE.format(
            pkg=pkg, data_cls=data_cls, table_name=schema.name,
            file_name=schema.file_name, side=side,
            fields_block=fields_block, read_block=read_block,
        )

    def _gen_table(self, schema: TableSchema, fields: List[FieldDef], table_cls: str, data_cls: str) -> str:
        pkg = self.namespace
        key_field = fields[0]
        key_type = _j_key_type(key_field)
        box_key = _j_box_key_type(key_field)
        key_name = key_field.name

        return _TABLE_TEMPLATE.format(
            pkg=pkg, table_cls=table_cls, data_cls=data_cls,
            file_name=schema.file_name,
            key_type=key_type, box_key=box_key, key_name=key_name,
        )


def _sanitize_pkg(name: str) -> str:
    """把命名空间 sanitize 成合法 Java 包名(全小写)。"""
    s = name.lower()
    out_chars: list[str] = []
    for ch in s:
        if ch.isalnum() or ch == "." or ch == "_":
            out_chars.append(ch)
        elif ch == "-":
            out_chars.append("_")
    out = "".join(out_chars)
    # 去掉首尾的点、连续点
    while ".." in out:
        out = out.replace("..", ".")
    out = out.strip(".")
    if not out:
        return "gamedata"
    # 每段不能以数字开头,且不能是关键字/保留包名前缀
    parts = []
    for p in out.split("."):
        if not p:
            continue
        if p[0].isdigit():
            p = "_" + p
        if p in _J_INVALID_PKG:
            p = p + "_tbl"
        parts.append(p)
    return ".".join(parts) if parts else "gamedata"


# 不能用作 Java 包名段的标识符:关键字 + 受限包名前缀(直接用会导致编译/打包问题)
_J_INVALID_PKG = {
    # 关键字
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while",
    # 受限包名前缀
    "java", "javax", "sun",
}


# —— 数据类模板 ——
_DATA_TEMPLATE = """// 自动生成,请勿手动修改。来源: {file_name} [{side}]
package {pkg};

/** {data_cls} {table_name}表数据({side})。 */
public class {data_cls} {{
{fields_block}

    /** 从二进制读取器读取一条数据。 */
    public void read(TableReader r) {{
{read_block}
    }}
}}
"""

# —— 管理类模板 ——
_TABLE_TEMPLATE = """// 自动生成,请勿手动修改。来源: {file_name}
package {pkg};

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** {table_cls}Table {table_cls}表管理类。
 *  文件加载由调用方处理,本类只接收已读入内存的二进制数据。 */
public class {table_cls}Table {{
    private Map<{box_key}, {data_cls}> map;
    private List<{data_cls}> list;

    /** 从二进制数据加载整张表。 */
    public void load(byte[] bytes) {{
        TableReader r = new TableReader(bytes);
        r.checkMagic("ETBL");        // magic
        r.readInt16();               // version
        int rowCount = r.readInt32(); // rowCount
        r.readInt16();               // fieldCount(顺序已固化在本文件)

        map = new HashMap<{box_key}, {data_cls}>(rowCount);
        list = new ArrayList<{data_cls}>(rowCount);
        for (int i = 0; i < rowCount; i++) {{
            {data_cls} d = new {data_cls}();
            d.read(r);
            map.put(d.{key_name}, d);
            list.add(d);
        }}
    }}

    /** 按主键取数据,不存在返回 null。 */
    public {data_cls} get({key_type} id) {{ return map.get(id); }}

    /** 返回数据条数。 */
    public int count() {{ return list.size(); }}

    /** 返回全部数据列表。 */
    public List<{data_cls}> getAll() {{ return list; }}
}}
"""

# —— 共用读取器模板 ——
_READER_TEMPLATE = """// 自动生成,请勿手动修改。通用二进制表读取器(小端)。
package {pkg};

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** 通用二进制表读取器:仅负责解析二进制数据,文件加载由调用方自行处理。
 *  与 ExcelToDevData 导出的 .bytes 严格对应。 */
public class TableReader {{
    private final ByteBuffer buf;

    public TableReader(byte[] bytes) {{
        this.buf = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
    }}

    /** 校验魔数,匹配则跳过;不匹配返回 false。 */
    public boolean checkMagic(String magic) {{
        byte[] mb = magic.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        for (int i = 0; i < mb.length; i++) {{
            if (buf.get() != mb[i]) {{
                buf.position(buf.position() - i - 1);
                return false;
            }}
        }}
        return true;
    }}

    public short readInt16() {{ return buf.getShort(); }}

    public int readInt32() {{ return buf.getInt(); }}

    public float readFloat32() {{ return buf.getFloat(); }}

    public boolean readBoolean() {{ return buf.get() != 0; }}

    public String readString() {{
        int len = buf.getShort() & 0xFFFF;
        byte[] raw = new byte[len];
        buf.get(raw);
        return new String(raw, java.nio.charset.StandardCharsets.UTF_8);
    }}

    public int[] readInt32Array() {{
        int n = readInt32();
        int[] a = new int[n];
        for (int i = 0; i < n; i++) a[i] = readInt32();
        return a;
    }}

    public float[] readFloat32Array() {{
        int n = readInt32();
        float[] a = new float[n];
        for (int i = 0; i < n; i++) a[i] = readFloat32();
        return a;
    }}

    public boolean[] readBooleanArray() {{
        int n = readInt32();
        boolean[] a = new boolean[n];
        for (int i = 0; i < n; i++) a[i] = readBoolean();
        return a;
    }}

    public String[] readStringArray() {{
        int n = readInt32();
        String[] a = new String[n];
        for (int i = 0; i < n; i++) a[i] = readString();
        return a;
    }}
}}
"""


def _render_reader(namespace: str) -> str:
    pkg = _sanitize_pkg(namespace or "gamedata")
    return _READER_TEMPLATE.format(pkg=pkg)

"""Lua 代码生成器。

为每张表、每个端生成:
    {Table}/{Table}Data.lua    数据读取模块(返回一个 reader 函数)
    {Table}/{Table}Table.lua   管理模块(load(bytes) + get/getAll)
以及每端共用一次的:
    TableReader.lua            纯二进制读取器(小端)

与 binary_writer.py 的写入严格对应:小端、无字段描述区。

兼容 Lua 5.1+(Skynet 等常用 5.1),不依赖 Lua 5.3 的 string.unpack,
全部用 string.byte + 位运算(Lua 5.1 用算术拼,Lua 5.3 用 // 与 >> 兼容写法)。
"""
from __future__ import annotations

from typing import List

from .. import schema as S
from ..schema import FieldDef, TableSchema
from .base import OutputFile

# type_code -> Lua 读取器方法名(挂在 reader 表上)
_LUA_READER = {
    S.T_INT: "readInt32",
    S.T_FLOAT: "readFloat32",
    S.T_BOOL: "readBool",
    S.T_STRING: "readString",
    S.T_INT_ARRAY: "readInt32Array",
    S.T_FLOAT_ARRAY: "readFloat32Array",
    S.T_BOOL_ARRAY: "readBoolArray",
    S.T_STRING_ARRAY: "readStringArray",
}


def _reader_call(fdef: FieldDef) -> str:
    return f"r:{_LUA_READER[fdef.type_code]}()"


def _lua_key_is_string(fdef: FieldDef) -> bool:
    """Lua table 的数字主键用 number,string 主键用 string;主键类型仅可能是标量。"""
    return fdef.type_code == S.T_STRING


class LuaGenerator:
    """绑定模块名后的 Lua 生成器实例。self.namespace 作为模块前缀(可空)。"""

    name = "lua"

    def __init__(self, namespace: str) -> None:
        # Lua 模块名规范:小写、点分。空则不带前缀
        self.namespace = _sanitize_module(namespace or "")

    def generate(
        self,
        schema: TableSchema,
        side: str,
        fields: List[FieldDef],
        subdirs_by_table: bool = False,
    ) -> List[OutputFile]:
        table_cls = schema.name
        prefix = f"{table_cls}/" if subdirs_by_table else ""
        return [
            OutputFile(
                relative_path=f"{prefix}{table_cls}Table.lua",
                content=self._gen_table(schema, fields, side, table_cls),
            ),
        ]

    def shared_files(self) -> List[OutputFile]:
        return [OutputFile(
            relative_path="TableReader.lua",
            content=_render_reader(),
            is_shared=True,
        )]

    # ---------------- 模板 ----------------

    def _gen_table(self, schema: TableSchema, fields: List[FieldDef], side: str, table_cls: str) -> str:
        mod_prefix = f"{self.namespace}." if self.namespace else ""
        key_field = fields[0]
        key_name = key_field.name
        key_is_str = _lua_key_is_string(key_field)
        # 生成字段读取语句:data.xxx = r:readXxx()
        read_lines = [f"        data.{fdef.name} = {_reader_call(fdef)}" for fdef in fields]
        read_block = "\n".join(read_lines) if read_lines else "        -- 无字段"

        return _TABLE_TEMPLATE.format(
            mod_prefix=mod_prefix, table_cls=table_cls,
            file_name=schema.file_name, side=side,
            key_name=key_name,
            key_type_hint="string" if key_is_str else "number",
            read_block=read_block,
            field_count=len(fields),
        )


# —— 管理类(含数据读取)模板 ——
# Lua 不强求单独的 Data 文件:数据直接读成一张 table。
# 这里生成一个 XxxTable 模块,require TableReader,提供 load/get/getAll。
_TABLE_TEMPLATE = """-- 自动生成,请勿手动修改。来源: {file_name} [{side}]
-- {table_cls} 表管理模块。文件加载由调用方处理,本模块只接收已读入内存的字节串。
local TableReader = require("{mod_prefix}TableReader")

local {table_cls}Table = {{}}
{table_cls}Table.__index = {table_cls}Table

--- 从二进制字节串加载整张表。
function {table_cls}Table.load(bytes)
    local self = setmetatable({{}}, {table_cls}Table)
    local r = TableReader.new(bytes)
    r:checkMagic("ETBL")       -- magic
    r:readInt16()               -- version
    local rowCount = r:readInt32()  -- rowCount
    r:readInt16()               -- fieldCount(顺序已固化,共 {field_count} 个)

    self._map = {{}}
    self._list = {{}}
    for i = 1, rowCount do
        local data = {{}}
{read_block}
        self._map[data.{key_name}] = data
        self._list[#self._list + 1] = data
    end
    return self
end

--- 按主键取数据(主键 {key_type_hint}),不存在返回 nil。
function {table_cls}Table:get(id)
    return self._map[id]
end

--- 返回数据条数。
function {table_cls}Table:count()
    return #self._list
end

--- 返回全部数据列表。
function {table_cls}Table:getAll()
    return self._list
end

return {table_cls}Table
"""

# —— 共用读取器模板 ——
# 兼容 Lua 5.1:不用 bitwise 操作符,用算术模拟;string.byte 取字节。
# 浮点用 string.unpack("<f") —— 5.3+ 支持;5.1/5.2 需用户提供等价实现或升级。
# 为最大兼容性,这里用 struct 思路手写:5.3+ 走 string.unpack,否则降级。
_READER_TEMPLATE = """-- 自动生成,请勿手动修改。通用二进制表读取器(小端)。
-- 与 TableAssembly 导出的 .bytes 严格对应。
-- 兼容 Lua 5.1+:整数读取不依赖 string.unpack;浮点优先用 string.unpack("<f")(Lua 5.3+),
-- 旧版本调用方可自行替换 readFloat32 的实现。

local TableReader = {}
TableReader.__index = TableReader

local function _byte(s, i)
    return s:byte(i, i)
end

-- 局部化 string.unpack(若存在)
local _unpack = string.unpack or nil

function TableReader.new(bytes)
    return setmetatable({_s = bytes, _pos = 1}, TableReader)
end

-- 校验魔数,匹配则跳过;不匹配返回 false(不前进)。
function TableReader:checkMagic(magic)
    for i = 1, #magic do
        if _byte(self._s, self._pos + i - 1) ~= magic:byte(i) then
            return false
        end
    end
    self._pos = self._pos + #magic
    return true
end

-- 2 字节小端有符号整数
function TableReader:readInt16()
    local b0, b1 = _byte(self._s, self._pos), _byte(self._s, self._pos + 1)
    self._pos = self._pos + 2
    local v = b0 + b1 * 256
    if v >= 32768 then v = v - 65536 end
    return v
end

-- 4 字节小端有符号整数
function TableReader:readInt32()
    local b0 = _byte(self._s, self._pos)
    local b1 = _byte(self._s, self._pos + 1)
    local b2 = _byte(self._s, self._pos + 2)
    local b3 = _byte(self._s, self._pos + 3)
    self._pos = self._pos + 4
    local v = b0 + b1 * 256 + b2 * 65536 + b3 * 16777216
    if v >= 2147483648 then v = v - 4294967296 end
    return v
end

-- 4 字节小端 IEEE754 浮点
function TableReader:readFloat32()
    if _unpack then
        local f = _unpack("<f", self._s, self._pos)
        self._pos = self._pos + 4
        return f
    end
    -- 5.1/5.2 降级:用 string.dump 思路不通用,这里给出基于字节的手动解码
    local b0, b1, b2, b3 = _byte(self._s, self._pos), _byte(self._s, self._pos + 1),
                           _byte(self._s, self._pos + 2), _byte(self._s, self._pos + 3)
    self._pos = self._pos + 4
    local bits = b0 + b1 * 256 + b2 * 65536 + b3 * 16777216
    local sign = bits >= 2147483648 and -1 or 1
    bits = bits % 2147483648
    local exp = math.floor(bits / 8388608)
    local mant = bits % 8388608
    if exp == 0 and mant == 0 then return sign * 0.0 end
    if exp == 255 then return mant == 0 and (sign * math.huge) or (0/0) end
    return sign * math.ldexp(mant + 8388608, exp - 150)
end

-- 1 字节布尔
function TableReader:readBool()
    local v = _byte(self._s, self._pos) ~= 0
    self._pos = self._pos + 1
    return v
end

-- 字符串:2 字节小端长度 + UTF-8 字节
function TableReader:readString()
    local len = self:readInt16()
    if len < 0 then len = len + 65536 end
    local s = self._s:sub(self._pos, self._pos + len - 1)
    self._pos = self._pos + len
    return s
end

function TableReader:readInt32Array()
    local n = self:readInt32()
    local a = {}
    for i = 1, n do a[i] = self:readInt32() end
    return a
end

function TableReader:readFloat32Array()
    local n = self:readInt32()
    local a = {}
    for i = 1, n do a[i] = self:readFloat32() end
    return a
end

function TableReader:readBoolArray()
    local n = self:readInt32()
    local a = {}
    for i = 1, n do a[i] = self:readBool() end
    return a
end

function TableReader:readStringArray()
    local n = self:readInt32()
    local a = {}
    for i = 1, n do a[i] = self:readString() end
    return a
end

return TableReader
"""


def _render_reader() -> str:
    return _READER_TEMPLATE


def _sanitize_module(name: str) -> str:
    """sanitize 成 Lua 模块名(小写、点分、可空)。"""
    s = name.lower()
    out_chars: list[str] = []
    for ch in s:
        if ch.isalnum() or ch == "." or ch == "_":
            out_chars.append(ch)
        elif ch == "-":
            out_chars.append("_")
    out = "".join(out_chars)
    while ".." in out:
        out = out.replace("..", ".")
    out = out.strip(".")
    return out

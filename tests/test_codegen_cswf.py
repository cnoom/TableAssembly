"""cs_wf 生成器契约测试：薄壳形态/特性/override/无 TableReader 产物/C# 9 兼容。

稳定面契约：框架仓 specs/027-excel-table-pipeline/contracts/cswf-codegen-contract.md。
框架侧镜像锚点：Tests/EditMode/Config/TestTables.cs（抄写件，模板变更须两侧同步）。
"""
from __future__ import annotations

from app import schema as S
from app.codegen import GENERATORS, create_generator
from app.codegen.cs_wf import CsWfGenerator

from tests.conftest import make_field, make_schema


def _schema():
    return make_schema(
        name="Item",
        fields=[
            make_field("id", S.T_INT),
            make_field("name", S.T_STRING),
            make_field("hp", S.T_INT),
            make_field("dropList", S.T_INT_ARRAY),
        ],
        rows=[(6, [1001, "木剑", 50, [1001, 1002]])],
    )


def _files(side: str = "client", **kw):
    gen = CsWfGenerator("Demo.Tables")
    schema = _schema()
    out = {f.relative_path: f.content for f in gen.generate(schema, side, schema.fields, **kw)}
    return out


def test_registered_in_generators():
    gen = create_generator("cs_wf", "X")
    assert gen is not None
    assert "cs_wf" in GENERATORS


def test_data_class_is_poco_with_sync_read():
    out = _files()
    data = out["ItemData.cs"]
    assert "public class ItemData" in data
    assert "public void Read(TableBinaryReader r)" in data
    assert "r.ReadInt32();" in data
    assert "r.ReadString();" in data
    assert "r.ReadInt32Array();" in data
    assert "Task" not in data, "同步 Read，不产假异步"
    assert "namespace Demo.Tables" in data
    assert "using CNoom.WFFramework.Modules.Config;" in data
    assert "自动生成,请勿手动修改" in data


def test_table_class_is_thin_shell_with_attribute_and_overrides():
    out = _files()
    table = out["ItemTable.cs"]
    assert '[ConfigTable("Item_c")]' in table
    assert "public sealed class ItemTable : TableBase<ItemData, int>" in table
    assert "protected override short FieldCount => 4;" in table
    assert "protected override ItemData ReadRow(TableBinaryReader r) { var d = new ItemData(); d.Read(r); return d; }" in table
    assert "protected override int KeyOf(ItemData d) => d.id;" in table
    assert "LoadAsync" not in table
    assert "TableReader.cs" not in table and "class TableReader" not in table


def test_shared_files_empty_no_table_reader():
    assert CsWfGenerator("X").shared_files() == []


def test_server_side_address_suffix():
    out = _files(side="server")
    assert '[ConfigTable("Item_s")]' in out["ItemTable.cs"]


def test_string_primary_key_type():
    schema = make_schema(
        name="Name",
        fields=[make_field("id", S.T_STRING), make_field("label", S.T_STRING)],
        rows=[(6, ["key.a", "标签A"])],
    )
    gen = CsWfGenerator("Demo.Tables")
    table = gen.generate(schema, "client", schema.fields)[1].content
    assert "TableBase<NameData, string>" in table
    assert "KeyOf(NameData d) => d.id;" in table


def test_subdirs_by_table_paths():
    out = _files(subdirs_by_table=True)
    assert "Item/ItemData.cs" in out
    assert "Item/ItemTable.cs" in out


def test_csharp9_compatible_no_csharp10_syntax():
    out = _files()
    for content in out.values():
        for banned in ("record struct", "record class", " required ", "file class"):
            assert banned not in content, f"C# 10+ 语法泄漏: {banned!r}"

"""代码生成器冒烟测试:生成的源码必须能编译,二进制必须能读回。

本测试组针对的是一次真实事故:C# 的 ``TableReader.cs`` 模板误用了 ``{{``/``}}``
转义(那是 f-string / str.format 的写法),却用 ``str.replace`` 渲染,导致生成的
``.cs`` 文件里出现 ``namespace Foo`` ``{{`` 无法编译。该 bug 漏网的原因是当时只有
reader/checker/rules 的测试,没有任何「生成代码能编译」的测试。

本组测试堵住这个缺口:

1. ``test_no_double_braces_in_generated_code`` —— 对所有语言的全部产物做静态扫描,
   禁止出现 ``{{`` / ``}}``(这是渲染机制错配的指纹),无论编译器是否安装都执行,
   是防回归的硬底线。
2. ``test_cs_compiles_and_roundtrips`` —— 在安装了 .NET SDK 的环境下,真正调用
   ``dotnet build`` 编译生成的 C# 代码,并写一个 ``Program.cs`` 把 ``.bytes`` 读回,
   断言运行时数据正确;无 SDK 则跳过。
3. ``test_go_compiles`` / ``test_java_compiles`` / ``test_lua_parses`` —— 对应语言
   编译器可用时,做编译/语法检查;不可用则跳过。

被跳过不等于失败:CI 矩阵里至少要让 C# 的一路跑通(本仓库主目标语言)。
"""
from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from app import binary_writer as bw, schema as S
from app.codegen import create_generator
from tests.conftest import make_schema, make_field

# —— 一张覆盖所有类型的小表,供各语言生成器使用 ——
# 字段顺序与 binary_writer 写入顺序一致;主键 = B 列(field 0)。
_SCALAR_FIELDS = [
    make_field("id", S.T_INT, side="both"),            # 主键
    make_field("hp", S.T_FLOAT, side="both"),
    make_field("flag", S.T_BOOL, side="both"),
    make_field("name", S.T_STRING, side="both"),
    make_field("tags", S.T_STRING_ARRAY, sep="|", side="both"),
    make_field("costs", S.T_INT_ARRAY, sep=",", side="both"),
]
_ROWS = [
    (2, [1, 1.5, True, "木剑", ["a", "b"], [10, 20]]),
    (3, [2, 2.5, False, "铁盾", ["x"], [30]]),
]
NS = "SmokeData"


def _schema() -> S.TableSchema:
    return make_schema("Smoke", _SCALAR_FIELDS, _ROWS)


def _gen_all(lang: str, out_dir: Path) -> list[Path]:
    """用 lang 生成器产出全部文件(共用 + 表),写入 out_dir,返回文件路径列表。"""
    gen = create_generator(lang, NS)
    assert gen is not None, f"未知语言 {lang}"
    schema = _schema()
    written: list[Path] = []
    for sf in gen.shared_files():
        p = out_dir / sf.relative_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(sf.content, encoding="utf-8")
        written.append(p)
    for cf in gen.generate(schema, "client", schema.fields, subdirs_by_table=False):
        p = out_dir / cf.relative_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(cf.content, encoding="utf-8")
        written.append(p)
    return written


def _build_bytes(out_dir: Path) -> Path:
    """生成对应的 .bytes(全字段,不分端),返回其路径。"""
    schema = _schema()
    data = bw.build_binary(schema, schema.fields, schema.rows)
    p = out_dir / "Smoke_c.bytes"
    p.write_bytes(data)
    return p


# ============================================================
# 1. 静态底线:所有产物不得出现 {{ / }}(渲染机制错配指纹)
# ============================================================

@pytest.mark.parametrize("lang", ["cs", "go", "java", "lua"])
def test_no_double_braces_in_generated_code(lang, tmp_path):
    """禁止任何生成产物出现 ``{{`` 或 ``}}``。

    这些双大括号只可能来自「模板按 f-string/format 语法转义、却用 replace 渲染」
    的错配,会直接导致 C#/Java 代码无法编译。本断言与编译器是否安装无关,是防
    回归的最低保障。
    """
    files = _gen_all(lang, tmp_path)
    assert files, f"{lang} 未产出任何文件"
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert "{{" not in text, f"{lang}:{f.name} 含 {{ (渲染错配?)\n{text[:200]}"
        assert "}}" not in text, f"{lang}:{f.name} 含 }} (渲染错配?)\n{text[:200]}"


# ============================================================
# 2. C#:dotnet build + 运行时往返(主目标语言,CI 应跑通)
# ============================================================

def _has_dotnet() -> bool:
    return shutil.which("dotnet") is not None


@pytest.mark.skipif(not _has_dotnet(), reason="未安装 dotnet SDK,跳过 C# 编译验证")
def test_cs_compiles_and_roundtrips(tmp_path):
    """生成 C# 代码 → dotnet build 必须成功 → 读回 .bytes 数据正确。

    这是「生成代码真能用」的端到端证据,直接对冲本次事故类问题。
    """
    proj = tmp_path / "proj"
    proj.mkdir(parents=True)

    # 先建 console 项目,再把生成的 .cs 直接放进项目根(与 Program.cs 同目录)。
    # dotnet SDK 默认递归编译项目根下所有 .cs,这样无需改 csproj。
    subprocess.run(
        ["dotnet", "new", "console", "--force"],
        cwd=proj, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # 生成代码 + bytes,直接落在项目根
    _gen_all("cs", proj)
    bytes_file = _build_bytes(proj)

    # 写一个 Program.cs,加载 Smoke 表并校验数据。
    # 注意:用普通字符串 + replace 注入命名空间,不能用 f-string —— 里面的
    # C# 字符串插值 $"...{t.Count}..." 会被 Python 误当成自己的插值。
    program = textwrap.dedent('''\
        using System.IO;
        using {NS};
        var t = new SmokeTable();
        await t.LoadAsync(File.ReadAllBytes("Smoke_c.bytes"));
        if (t.Count != 2) throw new System.Exception("行数应为 2,实际 " + t.Count);
        var d = t.Get(1);
        if (d == null) throw new System.Exception("Get(1) 返回 null");
        if (d.hp != 1.5f) throw new System.Exception("hp 应为 1.5,实际 " + d.hp);
        if (!d.flag) throw new System.Exception("flag 应为 true");
        if (d.name != "木剑") throw new System.Exception("name 应为 木剑,实际 " + d.name);
        if (d.tags.Length != 2 || d.tags[1] != "b") throw new System.Exception("tags 错");
        if (d.costs.Length != 2 || d.costs[1] != 20) throw new System.Exception("costs 错");
        if (t.Get(999) != null) throw new System.Exception("Get(999) 应为 null");
        System.Console.WriteLine("OK");
    ''').replace("{NS}", NS)
    (proj / "Program.cs").write_text(program, encoding="utf-8")

    # 编译(只看是否成功,不捕获输出到测试日志以免污染)
    build = subprocess.run(
        ["dotnet", "build", "-nologo", "--no-restore"],
        cwd=proj, capture_output=True, text=True,
    )
    # no-restore 可能因为 new console 后未还原而失败,失败则补一次 restore 再 build
    if build.returncode != 0:
        subprocess.run(["dotnet", "restore"], cwd=proj,
                       check=False, capture_output=True, text=True)
        build = subprocess.run(
            ["dotnet", "build", "-nologo"],
            cwd=proj, capture_output=True, text=True,
        )
    assert build.returncode == 0, (
        f"dotnet build 失败 (rc={build.returncode}):\n"
        f"--- stdout ---\n{build.stdout}\n--- stderr ---\n{build.stderr}"
    )

    # 运行,期望输出 OK
    run = subprocess.run(
        ["dotnet", "run", "--no-build", "-nologo"],
        cwd=proj, capture_output=True, text=True,
    )
    assert run.returncode == 0, (
        f"dotnet run 失败 (rc={run.returncode}):\n"
        f"--- stdout ---\n{run.stdout}\n--- stderr ---\n{run.stderr}"
    )
    assert "OK" in run.stdout, f"运行时断言未通过,输出:\n{run.stdout}\n{run.stderr}"


# ============================================================
# 3. 其他语言:编译器可用则编译,否则跳过
# ============================================================

def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@pytest.mark.skipif(not _has("go"), reason="未安装 go,跳过 Go 编译验证")
def test_go_compiles(tmp_path):
    """生成 Go 代码 → go build 必须成功。"""
    _gen_all("go", tmp_path)
    # go build 编译目录下所有 .go
    r = subprocess.run(
        ["go", "build", "./..."],
        cwd=tmp_path, capture_output=True, text=True,
    )
    # go 不需要独立 main 也能 vet/build 包;只要不报错即可
    # (若无 main 包,build 仍会编译;若报 "no Go files" 则说明生成失败)
    assert r.returncode == 0 or "no main packages" in r.stderr, (
        f"go build 失败:\n{r.stdout}\n{r.stderr}"
    )


@pytest.mark.skipif(not _has("javac"), reason="未安装 javac,跳过 Java 编译验证")
def test_java_compiles(tmp_path):
    """生成 Java 代码 → javac 必须成功。"""
    _gen_all("java", tmp_path)
    java_files = list(tmp_path.rglob("*.java"))
    assert java_files, "未生成任何 .java"
    r = subprocess.run(
        ["javac", "-encoding", "UTF-8", *[str(f) for f in java_files]],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"javac 失败:\n{r.stdout}\n{r.stderr}"


@pytest.mark.skipif(not _has("lua"), reason="未安装 lua,跳过 Lua 语法检查")
def test_lua_parses(tmp_path):
    """生成 Lua 代码 → luac -p 语法检查必须通过。"""
    _gen_all("lua", tmp_path)
    lua_files = list(tmp_path.rglob("*.lua"))
    assert lua_files, "未生成任何 .lua"
    for f in lua_files:
        r = subprocess.run(
            ["luac", "-p", str(f)],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert r.returncode == 0, f"luac 语法错误 {f}:\n{r.stderr}"

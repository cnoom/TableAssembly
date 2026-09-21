"""无头 CLI：供 Unity 编辑器（WFFramework ConfigTableBuildRunner）等外部进程调用。

协议契约：框架仓 specs/027-excel-table-pipeline/contracts/cli-protocol.md
    python -m app.cli projects [--json]
    python -m app.cli build --project <名>
        [--input <dir>] [--client-bin <dir>] [--client-cs <dir>]
        [--client-lang <lang>] [--client-ns <ns>]
        [--server-bin <dir>] [--server-cs <dir>] [--server-lang <lang>] [--server-ns <ns>]
        [--subdirs] [--side client|server|all] [--json]

约定：
- 覆盖参数只作用于本次进程，不回写 config.json（工具配置真源不被外部污染）
- --json：stdout 输出 ExportResult.to_dict()（成功与失败同 schema）；人类可读摘要走 stderr
- 退出码：0=成功导出；1=校验有错/导出异常；2=用法错误
- 本模块不 import fastapi/uvicorn（无 Web 依赖，起进程快）
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config as config_mod
from .exporter import ExportConfig, SideConfig, export_all

EXIT_OK = 0
EXIT_BUILD_FAILED = 1
EXIT_USAGE = 2


def _fail_usage(message: str) -> int:
    print(f"用法错误: {message}", file=sys.stderr)
    return EXIT_USAGE


def cmd_projects(args: argparse.Namespace) -> int:
    projects = config_mod.load_projects()
    names = projects.project_names()
    if args.json:
        print(json.dumps({"projects": names, "active": projects.active}, ensure_ascii=False))
    else:
        print("项目列表:")
        for name in names:
            mark = " *" if name == projects.active else ""
            print(f"  - {name}{mark}")
        print("(* = 活动)")
    return EXIT_OK


def cmd_build(args: argparse.Namespace) -> int:
    projects = config_mod.load_projects()
    base = projects.projects.get(args.project)
    if base is None:
        return _fail_usage(
            f"项目 \"{args.project}\" 不存在（现有: {', '.join(projects.project_names()) or '无'}）")

    if args.side not in ("client", "server", "all"):
        return _fail_usage(f"--side 非法: {args.side!r}（须 client/server/all）")

    config = ExportConfig(
        input_dir=args.input or base.input_dir,
        client=SideConfig(
            bin_dir=args.client_bin or base.client_bin,
            cs_dir=args.client_cs or base.client_cs,
            namespace_override=args.client_ns if args.client_ns is not None else base.client_namespace,
            lang=args.client_lang or base.client_lang,
        ),
        server=SideConfig(
            bin_dir=args.server_bin or base.server_bin,
            cs_dir=args.server_cs or base.server_cs,
            namespace_override=args.server_ns if args.server_ns is not None else base.server_namespace,
            lang=args.server_lang or base.server_lang,
        ),
        subdirs_by_table=args.subdirs or base.subdirs_by_table,
    )

    if not config.input_dir:
        return _fail_usage(f"项目 \"{args.project}\" 未配置输入目录，且未传 --input")

    result = export_all(config, side=args.side)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False))

    # 人类可读摘要 → stderr（stdout 只放 JSON，避免污染解析）
    print(
        f"构建完成: ok={result.ok} 错误={result.error_count} 警告={result.warning_count} "
        f"文件={len(result.files)}（side={args.side}）",
        file=sys.stderr,
    )
    for path in result.files:
        print(f"  + {path.kind}: {path.path}", file=sys.stderr)
    for err in result.errors:
        print(f"  ! {err}", file=sys.stderr)

    return EXIT_OK if result.ok and not result.errors else EXIT_BUILD_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="TableAssembly 无头 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_projects = sub.add_parser("projects", help="列出 config.json 全部项目名")
    p_projects.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    p_projects.set_defaults(func=cmd_projects)

    p_build = sub.add_parser("build", help="校验 + 导出（有错阻断，无半成品）")
    p_build.add_argument("--project", required=True, help="config.json 项目名（输入/server 侧配置基底）")
    p_build.add_argument("--input", default=None, help="覆盖 Excel 输入目录")
    p_build.add_argument("--client-bin", default=None, help="覆盖 client .bytes 输出目录")
    p_build.add_argument("--client-cs", default=None, help="覆盖 client 代码输出目录")
    p_build.add_argument("--client-lang", default=None, help="覆盖 client 语言（WFFramework 传 cs_wf）")
    p_build.add_argument("--client-ns", default=None, help="覆盖 client 命名空间")
    p_build.add_argument("--server-bin", default=None)
    p_build.add_argument("--server-cs", default=None)
    p_build.add_argument("--server-lang", default=None)
    p_build.add_argument("--server-ns", default=None)
    p_build.add_argument("--subdirs", action="store_true", help="代码按表名建子目录")
    p_build.add_argument("--side", default="all", choices=["client", "server", "all"], help="只导出指定端")
    p_build.add_argument("--json", action="store_true", help="stdout 输出结构化 JSON")
    p_build.set_defaults(func=cmd_build)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

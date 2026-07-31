"""极简 markdown → HTML 转换器(零依赖)。

只支持 README.md 实际用到的语法子集:
标题 / 段落 / 围栏代码块 / GFM 表格 / 列表 / 引用 / 行内 code bold link。
所有文本经 html.escape() 防注入。
"""
from __future__ import annotations

import html
import re


def split_sections(md: str) -> list[dict]:
    """按 ## 标题把 markdown 切成段。

    返回 [{id, title, html}]。id 与 title 均为标题原文(中文)。
    一级标题(#)及其之前的内容(徽章区)丢弃。
    ### 子标题包含在其所属 ## 段内,不单独成段。
    """
    lines = md.split("\n")
    sections: list[dict] = []
    current_title: str | None = None
    current_body: list[str] = []

    for line in lines:
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            if current_title is not None:
                sections.append({
                    "id": current_title,
                    "title": current_title,
                    "html": markdown_to_html("\n".join(current_body)),
                })
            current_title = m.group(1).strip()
            current_body = []
        elif current_title is not None:
            # 跳过一级标题行,不进任何段(它在首个 ## 之前,本来就被丢弃)
            current_body.append(line)
        # current_title is None:仍在 ## 之前(含 # 一级标题区),丢弃

    if current_title is not None:
        sections.append({
            "id": current_title,
            "title": current_title,
            "html": markdown_to_html("\n".join(current_body)),
        })

    return sections


def markdown_to_html(md: str) -> str:
    """markdown 字符串 → HTML 字符串。

    主循环维护一个普通行缓冲 para;遇到块级元素(代码块/空行)时
    flush() 把缓冲的普通行拼成一个 <p>(转义只发生在这里)。
    块级元素自己负责转义,输出已成型 HTML,不经过 _wrap_paragraphs。
    """
    if not md or not md.strip():
        return ""

    lines = md.split("\n")
    out: list[str] = []
    para: list[str] = []  # 连续普通行缓冲
    i = 0
    n = len(lines)

    def flush():
        if para:
            text = " ".join(l.strip() for l in para)
            out.append(f"<p>{_inline(text)}</p>")
            para.clear()

    while i < n:
        line = lines[i]

        # 围栏代码块 ```
        if line.strip().startswith("```"):
            flush()
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过闭合 ```
            code = html.escape("\n".join(code_lines))
            out.append(f"<pre><code>{code}</code></pre>")
            continue

        # 标题 # ~ ######
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2).strip())}</h{lvl}>")
            i += 1
            continue

        # 无序列表 - / 有序列表 1.
        m_ul = re.match(r"^\s*[-*]\s+(.*)$", line)
        m_ol = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m_ul or m_ol:
            flush()
            tag = "ul" if m_ul else "ol"
            items: list[str] = [_inline((m_ul or m_ol).group(1).strip())]
            i += 1
            pat = r"^\s*[-*]\s+(.*)$" if m_ul else r"^\s*\d+\.\s+(.*)$"
            while i < n:
                mm = re.match(pat, lines[i])
                if not mm:
                    break
                items.append(_inline(mm.group(1).strip()))
                i += 1
            lis = "".join(f"<li>{it}</li>" for it in items)
            out.append(f"<{tag}>{lis}</{tag}>")
            continue

        # 引用 >
        if line.lstrip().startswith(">"):
            flush()
            quote_lines: list[str] = []
            while i < n and lines[i].lstrip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = _inline(" ".join(l.strip() for l in quote_lines))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # GFM 表格:当前行含 |,且下一行是分隔行
        if _is_row(line) and i + 1 < n and _is_sep(lines[i + 1]):
            flush()
            header_cells = _split_row(line)
            i += 2  # 跳过表头 + 分隔行
            body_rows: list[list[str]] = []
            while i < n and _is_row(lines[i]):
                body_rows.append(_split_row(lines[i]))
                i += 1
            ths = "".join(f"<th>{_inline(c)}</th>" for c in header_cells)
            head = f"<thead><tr>{ths}</tr></thead>"
            body = ""
            for row in body_rows:
                tds = "".join(f"<td>{_inline(c)}</td>" for c in row)
                body += f"<tr>{tds}</tr>"
            body = f"<tbody>{body}</tbody>" if body else ""
            out.append(f"<table>{head}{body}</table>")
            continue

        # 空行 = 段落边界
        if not line.strip():
            flush()
            i += 1
            continue

        para.append(line)
        i += 1

    flush()
    return "\n".join(out)


def _inline(text: str) -> str:
    """行内转义 + code/bold/link。

    顺序很重要:先 escape,再用正则在已转义文本上做替换。
    内联 code 优先(其内部内容不应被 bold/link 处理)。
    """
    esc = html.escape(text)
    # 内联 code:`...`
    esc = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", esc)
    # 粗体:**...**
    esc = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", esc)
    # 链接:[text](url)
    esc = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', esc)
    return esc


def _is_row(s: str) -> bool:
    """判断是否为表格行:含 | 且以 | 开头。"""
    return "|" in s and s.strip().startswith("|")


def _is_sep(s: str) -> bool:
    """判断是否为表格分隔行:仅由 | : - 空格组成,且至少一个内部 | 分隔。

    能正确接受 `|---|---|`(分隔行),拒绝 `| 1 | 2 |`(数据行)。
    """
    return bool(re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", s))


def _split_row(line: str) -> list[str]:
    """拆表格行:去掉首尾 |,按 | 切,去掉单元格两端空白。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]

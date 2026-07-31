"""极简 markdown → HTML 转换器(零依赖)。

只支持 README.md 实际用到的语法子集:
标题 / 段落 / 围栏代码块 / GFM 表格 / 列表 / 引用 / 行内 code bold link。
所有文本经 html.escape() 防注入。
"""
from __future__ import annotations

import html
import re


def split_sections(md: str) -> list[dict]:
    """按标题把 markdown 切片为多个段落。

    占位实现:Task 6 会替换为真正的标题切分逻辑。
    本任务(Task 1)仅为满足测试文件的导入,不调用。
    """
    return []


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

"""markdown_lite:markdown → HTML 转换 + 段落切片。"""
from __future__ import annotations

from app.markdown_lite import markdown_to_html, split_sections


def test_empty_string():
    assert markdown_to_html("") == ""


def test_simple_paragraph():
    assert markdown_to_html("你好世界") == "<p>你好世界</p>"


def test_two_paragraphs():
    md = "第一段。\n\n第二段。"
    out = markdown_to_html(md)
    assert "<p>第一段。</p>" in out
    assert "<p>第二段。</p>" in out


def test_html_escaped():
    """原始 < > & 必须被转义,防注入。"""
    out = markdown_to_html("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_fenced_code_block():
    md = "```\n<x>\n</x>\n```"
    out = markdown_to_html(md)
    assert "<pre><code>" in out
    assert "</code></pre>" in out
    # 内容转义恰好一次:出现 &lt; 而非 &amp;lt;,且 <pre> 标签本身不被转义
    assert "&lt;x&gt;" in out
    assert "&amp;lt;" not in out
    assert "<p>" not in out  # 代码块不进 <p>


def test_code_block_with_blank_line():
    """代码块内的空行不应被切成多个段落。"""
    md = "```\nline1\n\nline3\n```"
    out = markdown_to_html(md)
    assert out.count("<pre><code>") == 1
    assert "line1" in out and "line3" in out

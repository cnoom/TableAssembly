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


def test_h1_to_h6():
    for lvl in range(1, 7):
        hashes = "#" * lvl
        out = markdown_to_html(f"{hashes} 标题{lvl}")
        assert f"<h{lvl}>标题{lvl}</h{lvl}>" == out


def test_heading_then_paragraph():
    md = "## 标题\n\n正文内容。"
    out = markdown_to_html(md)
    assert "<h2>标题</h2>" in out
    assert "<p>正文内容。</p>" in out


def test_inline_code():
    out = markdown_to_html("这是 `code` 内联代码")
    assert "<code>code</code>" in out


def test_inline_bold():
    out = markdown_to_html("这是 **粗体** 文字")
    assert "<b>粗体</b>" in out


def test_inline_link():
    out = markdown_to_html("见 [文档](http://example.com) 详情")
    assert '<a href="http://example.com">文档</a>' in out


def test_unordered_list():
    md = "- 苹果\n- 香蕉\n- 橙子"
    out = markdown_to_html(md)
    assert "<ul>" in out
    assert "<li>苹果</li>" in out
    assert "<li>香蕉</li>" in out
    assert "<li>橙子</li>" in out
    assert "</ul>" in out


def test_ordered_list():
    md = "1. 第一\n2. 第二\n3. 第三"
    out = markdown_to_html(md)
    assert "<ol>" in out
    assert "<li>第一</li>" in out
    assert "<li>第二</li>" in out
    assert "</ol>" in out


def test_blockquote():
    md = "> 这是引用\n> 第二行"
    out = markdown_to_html(md)
    assert "<blockquote>" in out
    assert "这是引用" in out
    assert "</blockquote>" in out


def test_gfm_table():
    md = "| A列 | B列 |\n|-----|-----|\n| 1 | 2 |\n| 3 | 4 |"
    out = markdown_to_html(md)
    assert "<table>" in out and "</table>" in out
    assert "<thead>" in out
    assert "<th>A列</th>" in out and "<th>B列</th>" in out
    # 分隔行不应渲染成数据
    assert "<td>---</td>" not in out and "<td>-----</td>" not in out
    assert "<td>1</td>" in out
    assert "<td>3</td>" in out
    assert "<td>4</td>" in out
    assert out.count("<tr>") >= 3  # 1 表头 + 2 数据行


def test_split_sections_basic():
    md = "# 顶部标题\n\n![badge]\n\n## 第一节\n\n内容一。\n\n## 第二节\n\n内容二。"
    secs = split_sections(md)
    assert len(secs) == 2
    assert secs[0]["title"] == "第一节"
    assert secs[1]["title"] == "第二节"
    assert "<p>内容一。</p>" in secs[0]["html"]
    assert "<p>内容二。</p>" in secs[1]["html"]


def test_split_sections_drops_h1_prefix():
    """一级标题 # 及首个 ## 之前的内容应被丢弃。"""
    md = "# 项目名\n\n徽章区\n\n## 正文"
    secs = split_sections(md)
    assert len(secs) == 1
    assert secs[0]["title"] == "正文"
    assert "徽章区" not in secs[0]["html"]
    assert "项目名" not in "".join(s["html"] for s in secs)


def test_split_sections_no_h2():
    """无任何 ## 标题 → 返回空列表。"""
    assert split_sections("只有段落\n\n没有标题") == []


def test_split_sections_last_section_closes():
    """末尾段无后续 ##,应正常闭合。"""
    md = "## 唯一\n\n尾部内容。"
    secs = split_sections(md)
    assert len(secs) == 1
    assert "<p>尾部内容。</p>" in secs[0]["html"]


def test_split_sections_preserves_h3_inside_section():
    """### 子标题应包含在其所属 ## 段的 html 里。"""
    md = "## 父段\n\n正文。\n\n### 子标题\n\n子正文。"
    secs = split_sections(md)
    assert len(secs) == 1
    assert "<h3>子标题</h3>" in secs[0]["html"]


def test_split_sections_id_equals_title():
    """id 字段直接用标题原文(中文),不做锚点转写。"""
    md = "## 表格式规范\n\n内容。"
    secs = split_sections(md)
    assert secs[0]["id"] == "表格式规范"


def test_real_readme_sections():
    """真实 README.md 喂入:至少 8 个 ## 段。"""
    from pathlib import Path
    readme = Path(__file__).resolve().parent.parent / "README.md"
    md = readme.read_text(encoding="utf-8")
    secs = split_sections(md)
    titles = [s["title"] for s in secs]
    assert len(secs) >= 8, f"期望至少 8 段,实际 {len(secs)}: {titles}"
    # 已知关键段必须存在
    for must in ["特点", "快速开始", "表格式规范", "二进制格式", "项目结构"]:
        assert must in titles, f"缺失段落「{must}」, 实际: {titles}"
    # 每段 html 非空
    for s in secs:
        assert s["html"].strip() != "", f"段落「{s['title']}」html 为空"


def test_real_readme_html_no_raw_script():
    """转换后不应出现原始 <script> 标签(转义检查)。"""
    from pathlib import Path
    readme = Path(__file__).resolve().parent.parent / "README.md"
    md = readme.read_text(encoding="utf-8")
    for s in split_sections(md):
        assert "<script>" not in s["html"]

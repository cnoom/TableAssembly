# 帮助界面 + 全页明暗主题 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在网页新增按角色分 Tab 的帮助 Modal(内容解析自 README),并实现全页明暗主题切换。

**Architecture:** 新增零依赖的 `app/markdown_lite.py`(markdown→HTML + 按 `##` 切片);`main.py` 加 `GET /api/help` 端点;`index.html` 做 CSS 变量化、加主题切换、加帮助 Modal。后端可单测,前端手动验收。

**Tech Stack:** Python 3.9+ 标准库(无新依赖)、FastAPI、原生 HTML/CSS/JS(无前端框架)。

**对应规格:** `docs/superpowers/specs/2026-07-31-help-modal-design.md`

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `app/markdown_lite.py` | 新建 | 纯函数:`markdown_to_html()` + `split_sections()`,零依赖 |
| `app/main.py` | 修改 | 新增 `GET /api/help` 端点 |
| `app/web/index.html` | 修改 | CSS 变量化 + 明暗主题 + header 按钮 + 帮助 Modal |
| `tests/test_markdown_lite.py` | 新建 | 转换器与切片单测 |

---

## Task 1: markdown_lite 骨架与段落转换

**Files:**
- Create: `app/markdown_lite.py`
- Test: `tests/test_markdown_lite.py`

- [ ] **Step 1: 写失败的测试(空串 + 简单段落)**

创建 `tests/test_markdown_lite.py`:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.markdown_lite'`

- [ ] **Step 3: 写最小实现**

创建 `app/markdown_lite.py`:

```python
"""极简 markdown → HTML 转换器(零依赖)。

只支持 README.md 实际用到的语法子集:
标题 / 段落 / 围栏代码块 / GFM 表格 / 列表 / 引用 / 行内 code bold link。
所有文本经 html.escape() 防注入。
"""
from __future__ import annotations

import html
import re


def markdown_to_html(md: str) -> str:
    """markdown 字符串 → HTML 字符串。"""
    if not md or not md.strip():
        return ""

    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # 围栏代码块 ```
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过闭合 ```
            code = html.escape("\n".join(code_lines))
            out.append(f'<pre><code>{code}</code></pre>')
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        out.append(line)
        i += 1

    # 把非结构性行按空行分组为段落(占位:本步只做段落 + 转义)
    raw = "\n".join(out)
    return _wrap_paragraphs(raw)


def _wrap_paragraphs(text: str) -> str:
    """把不含块级语法的纯文本按空行分段为 <p>。"""
    blocks = re.split(r"\n\s*\n", text.strip())
    parts: list[str] = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        escaped = html.escape(b).replace("\n", "\n")
        parts.append(f"<p>{escaped}</p>")
    return "\n".join(parts)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: PASS — 4 个测试全过。

- [ ] **Step 5: 提交**

```bash
git add app/markdown_lite.py tests/test_markdown_lite.py
git commit -m "feat(markdown_lite): 骨架 + 段落转换 + HTML 转义"
```

---

## Task 2: 标题转换

**Files:**
- Modify: `app/markdown_lite.py`
- Test: `tests/test_markdown_lite.py`

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_markdown_lite.py` 末尾追加:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: FAIL — 标题被包进了 `<p>` 而非 `<h2>`。

- [ ] **Step 3: 改实现,在主循环里识别标题**

把 `markdown_to_html` 的主循环替换为(在「空行」判断之前、围栏代码块之后插入标题判断;其余不变):

```python
        # 标题 # ~ ######
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lvl = len(m.group(1))
            title = _inline(m.group(2).strip())
            out.append(f"<h{lvl}>{title}</h{lvl}>")
            i += 1
            continue
```

并把 `_wrap_paragraphs` 改为只处理未被块级元素标记的行。最简做法:主循环里标题/代码块直接输出,普通行先累积到一个缓冲,遇到空行/块级边界时把缓冲 flush 成 `<p>`。

完整重写 `markdown_to_html` 与 `_wrap_paragraphs`(用缓冲法):

```python
def markdown_to_html(md: str) -> str:
    """markdown 字符串 → HTML 字符串。"""
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
            out.append(f'<pre><code>{code}</code></pre>')
            continue

        # 标题
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
    """行内转义 + code/bold/link。"""
    esc = html.escape(text)
    # 内联 code 优先(避免内部被 bold/link 处理)
    esc = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", esc)
    esc = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", esc)
    esc = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', esc)
    return esc


def _wrap_paragraphs(text: str) -> str:
    """(已弃用,保留占位以免外部引用报错)"""
    return text
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: PASS — 全部 6 个测试过。

- [ ] **Step 5: 提交**

```bash
git add app/markdown_lite.py tests/test_markdown_lite.py
git commit -m "feat(markdown_lite): 标题转换 + 行内 code/bold/link"
```

---

## Task 3: 列表与引用转换

**Files:**
- Modify: `app/markdown_lite.py`
- Test: `tests/test_markdown_lite.py`

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_markdown_lite.py` 末尾追加:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: FAIL — 列表项被当成普通段落。

- [ ] **Step 3: 在主循环中处理列表与引用**

在 `markdown_to_html` 主循环里,「标题」判断之后、「空行」判断之前,插入列表与引用的块级聚合逻辑:

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: PASS — 全部 9 个测试过。

- [ ] **Step 5: 提交**

```bash
git add app/markdown_lite.py tests/test_markdown_lite.py
git commit -m "feat(markdown_lite): 无序/有序列表 + 引用"
```

---

## Task 4: GFM 表格转换

**Files:**
- Modify: `app/markdown_lite.py`
- Test: `tests/test_markdown_lite.py`

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_markdown_lite.py` 末尾追加:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: FAIL — 表格行被当普通段落。

- [ ] **Step 3: 在主循环中识别表格**

在主循环「引用」判断之前插入表格块。表格识别条件:当前行含 `|`,且下一行是分隔行(只含 `|`、`-`、`:`、空格)。

```python
        # GFM 表格:当前行含 |,且下一行是分隔行
        def _is_row(s: str) -> bool:
            return "|" in s and s.strip().startswith("|")

        def _is_sep(s: str) -> bool:
            return bool(re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", s))

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
```

并在文件末尾追加辅助函数 `_split_row`:

```python
def _split_row(line: str) -> list[str]:
    """拆表格行:去掉首尾 |,按 | 切,去掉单元格两端空白。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: PASS — 全部 10 个测试过。

- [ ] **Step 5: 提交**

```bash
git add app/markdown_lite.py tests/test_markdown_lite.py
git commit -m "feat(markdown_lite): GFM 表格"
```

---

## Task 5: split_sections 段落切片

**Files:**
- Modify: `app/markdown_lite.py`
- Test: `tests/test_markdown_lite.py`

- [ ] **Step 1: 追加失败的测试**

在 `tests/test_markdown_lite.py` 末尾追加:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: FAIL — `split_sections` 未定义。

- [ ] **Step 3: 实现 split_sections**

在 `app/markdown_lite.py` 末尾追加:

```python
def split_sections(md: str) -> list[dict]:
    """按 ## 标题把 markdown 切成段。

    返回 [{id, title, html}]。id 与 title 均为标题原文(中文)。
    一级标题(#)及其之前的内容(徽章区)丢弃。
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
            # 跳过一级标题行,不进任何段
            current_body.append(line)
        # current_title is None:仍在 ## 之前(含 # 一级标题区),丢弃

    if current_title is not None:
        sections.append({
            "id": current_title,
            "title": current_title,
            "html": markdown_to_html("\n".join(current_body)),
        })

    return sections
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: PASS — 全部 16 个测试过。

- [ ] **Step 5: 提交**

```bash
git add app/markdown_lite.py tests/test_markdown_lite.py
git commit -m "feat(markdown_lite): split_sections 按 ## 切片"
```

---

## Task 6: 用真实 README 喂入做集成测试

**Files:**
- Modify: `tests/test_markdown_lite.py`

- [ ] **Step 1: 追加集成测试**

在 `tests/test_markdown_lite.py` 末尾追加:

```python
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
```

- [ ] **Step 2: 跑测试确认通过**

Run: `python -m pytest tests/test_markdown_lite.py -v`
Expected: PASS — 全部 18 个测试过(若 README 表格/代码块渲染有异常,这里会暴露,回头修 Task 4/2)。

- [ ] **Step 3: 提交**

```bash
git add tests/test_markdown_lite.py
git commit -m "test(markdown_lite): 真实 README 集成测试"
```

---

## Task 7: main.py 新增 /api/help 端点

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_api_help.py`:

```python
"""GET /api/help 端点。"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_help_returns_sections():
    r = client.get("/api/help")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["source"] == "README.md"
    secs = body["sections"]
    assert isinstance(secs, list)
    assert len(secs) >= 8
    titles = [s["title"] for s in secs]
    assert "快速开始" in titles
    for s in secs:
        assert s["id"]
        assert s["title"]
        assert s["html"]  # 非空


def test_help_section_shape():
    r = client.get("/api/help")
    s = r.json()["sections"][0]
    assert set(s.keys()) == {"id", "title", "html"}
```

注:`requirements.txt` 里 fastapi 自带 TestClient 所需的 httpx(若跑时报缺 httpx,在 Task 8 统一处理依赖)。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_api_help.py -v`
Expected: FAIL — 404 或端点不存在(`/api/help` 未注册)。

- [ ] **Step 3: 在 main.py 加端点**

在 `app/main.py` 顶部 import 区,现有 `from . import exporter` 那一组下面加:

```python
from . import markdown_lite
```

在文件末尾(最后一个端点之后)追加:

```python
# ---------------- 帮助文档 ----------------

@app.get("/api/help")
def api_help() -> dict[str, Any]:
    readme_path = Path(__file__).resolve().parent.parent / "README.md"
    try:
        text = readme_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"ok": False, "error": "README.md 未找到", "sections": []}
    try:
        sections = markdown_lite.split_sections(text)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"文档解析失败: {e}", "sections": []}
    return {"ok": True, "source": "README.md", "sections": sections}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_api_help.py -v`
Expected: PASS。若报 `httpx` 未安装,执行 `pip install httpx`(仅测试用,下个 Task 评估是否进 requirements)。

- [ ] **Step 5: 提交**

```bash
git add app/main.py tests/test_api_help.py
git commit -m "feat(api): GET /api/help 返回 README 切片"
```

---

## Task 8: 确认 httpx 测试依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 检查 httpx 是否已随 fastapi 安装**

Run: `python -c "import httpx; print(httpx.__version__)"`
- 若输出版本号 → httpx 已在环境中(FastAPI 0.110+ 的 TestClient 依赖它)。仍建议加入 requirements 固化,进入 Step 2。
- 若报 ModuleNotFoundError → 必须加入。

- [ ] **Step 2: 把 httpx 加入 requirements.txt**

在 `requirements.txt` 的 `pytest` 行之后追加一行(保持注释式分组):

```
httpx>=0.27.0
```

完整文件应为:

```
openpyxl>=3.1.0
fastapi>=0.110.0
uvicorn>=0.27.0
pytest>=8.0.0
httpx>=0.27.0
```

- [ ] **Step 3: 重装并跑全部测试**

Run: `pip install -r requirements.txt && python -m pytest -q`
Expected: 全部 PASS(含原有 rules/checker 测试 + 新增 markdown_lite/api_help 测试)。

- [ ] **Step 4: 提交**

```bash
git add requirements.txt
git commit -m "chore(deps): 加入 httpx(TestClient 依赖)"
```

---

## Task 9: index.html CSS 变量化(为主题做准备)

**Files:**
- Modify: `app/web/index.html`

这一步**只改 CSS,不改结构、不加功能**,把现有硬编码颜色抽成变量。先做浅色(与现状视觉一致),下个 Task 再加深色。

- [ ] **Step 1: 在 `<style>` 开头加变量定义 + 防 FOUC 脚本**

在 `app/web/index.html` 的 `<style>` 标签内最前面(现有的 `* { box-sizing... }` 之前)插入:

```css
  :root {
    --bg: #f5f6f8;
    --surface: #fff;
    --surface-2: #fafbfc;
    --text: #222;
    --text-muted: #666;
    --text-faint: #999;
    --border: #e3e6ea;
    --border-light: #eee;
    --input-border: #ccc;
    --primary: #4a7dff;
    --primary-hover: #3a66d8;
    --primary-bg: #eef3ff;
    --header-bg: #2b3a55;
    --log-bg: #1e1e1e;
    --log-text: #d4d4d4;
    --log-meta: #888;
    --row-hover: #f0f5ff;
    --badge-both-bg: #e6f4ea; --badge-both-tx: #1e7e34;
    --badge-client-bg: #e7f0ff; --badge-client-tx: #1565c0;
    --badge-server-bg: #fff3e0; --badge-server-tx: #b25400;
    --code-bg: #f0f2f5;
    --field-pill-bg: #f0f2f5;
    --ok: #2e8b57; --err: #d33; --warn: #d97706;
  }
```

并在 `<head>` 内 `<style>` 之后、`</head>` 之前插入防 FOUC 内联脚本:

```html
<script>
  document.documentElement.setAttribute('data-theme',
    localStorage.getItem('theme') || 'light');
</script>
```

- [ ] **Step 2: 把现有 CSS 里的硬编码颜色逐一替换为变量**

按下表逐条替换(对照 `app/web/index.html` 现有第 8-47 行的规则):

| 选择器/位置 | 原值 | 替换为 |
|---|---|---|
| `body` `background` | `#f5f6f8` | `var(--bg)` |
| `body` `color` | `#222` | `var(--text)` |
| `header` `background` | `#2b3a55` | `var(--header-bg)` |
| `.card` `background` | `#fff` | `var(--surface)` |
| `.card` `border` | `1px solid #e3e6ea` | `1px solid var(--border)` |
| `.card h2` `color` | `#2b3a55` | `var(--header-bg)` |
| `.card h2` `border-left` | `3px solid #4a7dff` | `3px solid var(--primary)` |
| `.row label` `color` | `#666` | `var(--text-muted)` |
| `.row input[type=text]` `border` | `1px solid #ccc` | `1px solid var(--input-border)` |
| `.hint` `color` | `#999` | `var(--text-faint)` |
| `button` `background` | `#4a7dff` | `var(--primary)` |
| `button:hover` `background` | `#3a66d8` | `var(--primary-hover)` |
| `button.ghost` `color`/`border` | `#4a7dff` | `var(--primary)` |
| `button.ghost:hover` `background` | `#eef3ff` | `var(--primary-bg)` |
| `button.gray` `background` | `#888` | `var(--text-muted)` |
| `button.gray:hover` `background` | `#777` | `var(--text-muted)` |
| `th` `background` | `#fafbfc` | `var(--surface-2)` |
| `th, td` `border-bottom` | `1px solid #eee` | `1px solid var(--border-light)` |
| `.ok` | `#2e8b57` | `var(--ok)` |
| `.err` | `#d33` | `var(--err)` |
| `.warn` | `#d97706` | `var(--warn)` |
| `.log` `background` | `#1e1e1e` | `var(--log-bg)` |
| `.log` `color` | `#d4d4d4` | `var(--log-text)` |
| `.log .meta` `color` | `#888` | `var(--log-meta)` |
| `.table-list tr:hover` `background` | `#f0f5ff` | `var(--row-hover)` |
| `.b-both` `background`/`color` | `#e6f4ea`/`#1e7e34` | `var(--badge-both-bg)`/`var(--badge-both-tx)` |
| `.b-client` `background`/`color` | `#e7f0ff`/`#1565c0` | `var(--badge-client-bg)`/`var(--badge-client-tx)` |
| `.b-server` `background`/`color` | `#fff3e0`/`#b25400` | `var(--badge-server-bg)`/`var(--badge-server-tx)` |
| `.small` `color` | `#888` | `var(--log-meta)` |
| `.field-pill` `background` | `#f0f2f5` | `var(--field-pill-bg)` |

> 注意:`.log .lv-ERROR/.lv-WARNING/.lv-INFO` 的颜色保持原样(深色块上的亮色,两态通用)。`.row input` 的 `background:#fff` 如有也换 `var(--surface)`。

- [ ] **Step 3: 启动验证浅色无视觉回归**

Run: `python run.py`,浏览器开 `http://127.0.0.1:9900`
Expected: 页面外观与改造前**完全一致**(浅色)。

- [ ] **Step 4: 提交**

```bash
git add app/web/index.html
git commit -m "refactor(web): CSS 颜色抽成变量 + 防 FOUC 脚本"
```

---

## Task 10: 明暗主题切换

**Files:**
- Modify: `app/web/index.html`

- [ ] **Step 1: 在 CSS 末尾(现有规则之后)加深色变量与 header flex 布局**

在 `<style>` 内 `@keyframes spin` 之后追加:

```css
  [data-theme="dark"] {
    --bg: #1a1d23;
    --surface: #252932;
    --surface-2: #2d323d;
    --text: #e4e6eb;
    --text-muted: #9aa0aa;
    --text-faint: #7a808a;
    --border: #3a3f4a;
    --border-light: #333842;
    --input-border: #444a55;
    --primary: #5b8eff;
    --primary-hover: #7aa2ff;
    --primary-bg: #2a3550;
    --header-bg: #1e2533;
    --log-bg: #111317;
    --log-text: #d4d4d4;
    --log-meta: #6a707a;
    --row-hover: #2a3040;
    --badge-both-bg: #1e3a2a; --badge-both-tx: #5ac878;
    --badge-client-bg: #1a2a4a; --badge-client-tx: #6ba6ff;
    --badge-server-bg: #3a2a14; --badge-server-tx: #e8a45c;
    --code-bg: #333842;
    --field-pill-bg: #333842;
  }
  /* header 改 flex,右侧放主题+帮助按钮 */
  header { display: flex; justify-content: space-between; align-items: center; }
  .header-title { font-size: 18px; font-weight: 600; }
  .header-actions { display: flex; gap: 8px; }
  .icon-btn, .help-btn {
    background: rgba(255,255,255,.12); color: #fff; border: 1px solid rgba(255,255,255,.2);
    padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 13px;
  }
  .icon-btn:hover, .help-btn:hover { background: rgba(255,255,255,.22); }
  /* 帮助 Modal(下个 Task 接线) */
  .modal-mask {
    position: fixed; inset: 0; background: rgba(0,0,0,.5);
    display: flex; align-items: center; justify-content: center; z-index: 1000;
  }
  .modal-mask[hidden] { display: none; }
  .modal-box {
    background: var(--surface); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; width: 92%; max-width: 900px; max-height: 85vh;
    display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,.3);
  }
  .modal-head {
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 18px; border-bottom: 1px solid var(--border);
  }
  .modal-title { font-size: 16px; font-weight: 600; color: var(--primary); }
  .modal-close {
    background: transparent; color: var(--text-muted); border: 0;
    font-size: 18px; cursor: pointer; padding: 2px 8px;
  }
  .modal-close:hover { color: var(--err); }
  .modal-tabs { display: flex; gap: 4px; padding: 8px 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .modal-tab {
    padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 13px;
    color: var(--text-muted); border: 1px solid transparent;
  }
  .modal-tab:hover { color: var(--text); }
  .modal-tab.active { background: var(--primary); color: #fff; }
  .modal-body { overflow-y: auto; padding: 20px 28px; flex: 1; line-height: 1.7; }
  .modal-body h2 { color: var(--primary); border-left: 3px solid var(--primary); padding-left: 8px; margin: 22px 0 10px; font-size: 16px; }
  .modal-body h3 { color: var(--text); margin: 16px 0 6px; font-size: 14px; }
  .modal-body p { margin: 8px 0; }
  .modal-body table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }
  .modal-body th, .modal-body td { padding: 7px 9px; border: 1px solid var(--border); text-align: left; }
  .modal-body th { background: var(--surface-2); }
  .modal-body pre {
    background: var(--log-bg); color: var(--log-text); padding: 12px;
    border-radius: 6px; overflow-x: auto; margin: 10px 0; font-size: 12px;
  }
  .modal-body code { background: var(--code-bg); padding: 1px 5px; border-radius: 3px; font-family: Consolas, monospace; font-size: 12px; }
  .modal-body pre code { background: transparent; padding: 0; }
  .modal-body ul, .modal-body ol { margin: 8px 0; padding-left: 24px; }
  .modal-body li { margin: 3px 0; }
  .modal-body a { color: var(--primary); }
  .modal-body blockquote { border-left: 3px solid var(--border); margin: 10px 0; padding: 4px 12px; color: var(--text-muted); }
```

- [ ] **Step 2: 改 header 结构,加主题按钮 + 占位帮助按钮**

把现有 `<header>Excel → 开发数据 导出工具</header>` 替换为:

```html
<header>
  <span class="header-title">Excel → 开发数据 导出工具</span>
  <span class="header-actions">
    <button class="icon-btn" onclick="toggleTheme()" title="切换主题"><span id="theme_icon">🌙</span></button>
    <button class="help-btn" onclick="openHelp()">❓ 帮助</button>
  </span>
</header>
```

- [ ] **Step 3: 在 `</div><!-- /.wrap -->` 之后、`<script>` 之前插 Modal 骨架**

```html
<!-- 帮助 Modal -->
<div class="modal-mask" id="help_modal" hidden>
  <div class="modal-box">
    <div class="modal-head">
      <span class="modal-title">📖 帮助文档</span>
      <button class="modal-close" onclick="closeHelp()">✕</button>
    </div>
    <div class="modal-tabs" id="help_tabs"></div>
    <div class="modal-body" id="help_body"></div>
  </div>
</div>
```

- [ ] **Step 4: 加主题切换 JS**

在 `<script>` 内最前面(`const $ = ...` 之前)插入:

```javascript
function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
  const el = document.getElementById('theme_icon');
  if (el) el.textContent = (t === 'dark') ? '☀️' : '🌙';
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(cur === 'dark' ? 'light' : 'dark');
}
applyTheme(localStorage.getItem('theme') || 'light');
```

- [ ] **Step 5: 启动验证主题切换**

Run: `python run.py`,浏览器验证:
- 默认浅色(若之前切过深色会记忆,正常)
- 点 🌙 → 全页变深色,所有区域(header/卡片/表格/输入框/徽章/日志)无残留浅色
- 点 ☀️ → 切回浅色
- 刷新 → 保持上次主题,无闪烁
- 此刻点「❓ 帮助」无反应(openHelp 尚未实现,下个 Task 做)

- [ ] **Step 6: 提交**

```bash
git add app/web/index.html
git commit -m "feat(web): 全页明暗主题切换 + Modal 骨架 + header 按钮"
```

---

## Task 11: 帮助 Modal 接线(读 /api/help + 角色分 Tab)

**Files:**
- Modify: `app/web/index.html`

- [ ] **Step 1: 在 `<script>` 内(主题函数之后)加帮助逻辑**

在 Task 10 加的 `applyTheme(...)` 调用之后插入:

```javascript
// ---------- 帮助 Modal ----------
const ROLE_MAP = {
  'quick':   ['特点', '快速开始'],
  'planner': ['表格式规范', '自定义校验规则', '校验规则'],
  'coder':   ['产出', '二进制格式', '扩展其他语言'],
  'project': ['项目结构', 'License'],
};
const ROLE_LABELS = {
  'quick': '🎯 快速上手',
  'planner': '✏️ 策划',
  'coder': '💻 程序',
  'project': '📁 项目结构',
};
let helpCache = null;

async function openHelp() {
  const modal = document.getElementById('help_modal');
  modal.hidden = false;
  if (helpCache) { renderHelp(helpCache); return; }
  document.getElementById('help_tabs').innerHTML = '<span class="small">加载中...</span>';
  document.getElementById('help_body').innerHTML = '';
  try {
    const r = await get('/api/help');
    if (!r.ok) {
      document.getElementById('help_tabs').innerHTML = '';
      document.getElementById('help_body').innerHTML = '<p>⚠️ 文档加载失败: ' + (r.error || '未知错误') + '</p>';
      return;
    }
    helpCache = r.sections;
    renderHelp(r.sections);
  } catch (e) {
    document.getElementById('help_tabs').innerHTML = '';
    document.getElementById('help_body').innerHTML = '<p>⚠️ 请求失败: ' + e + '</p>';
  }
}

function closeHelp() {
  document.getElementById('help_modal').hidden = true;
}

function renderHelp(sections) {
  // 按角色分组:一个段精确匹配 ROLE_MAP 某项 → 归入该角色(首个命中)
  const byRole = {};
  for (const role of Object.keys(ROLE_MAP)) byRole[role] = [];
  for (const sec of sections) {
    for (const [role, titles] of Object.entries(ROLE_MAP)) {
      if (titles.includes(sec.title)) {
        byRole[role].push(sec);
        break;
      }
    }
  }
  // 渲染 Tab 栏
  const tabsEl = document.getElementById('help_tabs');
  tabsEl.innerHTML = '';
  const order = ['quick', 'planner', 'coder', 'project'];
  order.forEach((role, idx) => {
    const tab = document.createElement('span');
    tab.className = 'modal-tab' + (idx === 0 ? ' active' : '');
    tab.textContent = ROLE_LABELS[role];
    tab.onclick = () => {
      tabsEl.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      showRole(role, byRole[role]);
    };
    tabsEl.appendChild(tab);
  });
  // 默认显示第一个 Tab
  showRole('quick', byRole['quick']);
}

function showRole(role, secs) {
  const body = document.getElementById('help_body');
  if (!secs || secs.length === 0) {
    body.innerHTML = '<p>该部分文档暂未找到,请查阅 README.md。</p>';
    return;
  }
  body.innerHTML = secs.map(s => s.html).join('\n<hr style="border:0;border-top:1px solid var(--border);margin:18px 0;">');
}

// 点遮罩或 ESC 关闭
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !document.getElementById('help_modal').hidden) closeHelp();
});
document.getElementById('help_modal').addEventListener('click', e => {
  if (e.target.id === 'help_modal') closeHelp();
});
```

- [ ] **Step 2: 启动,完整手动验收**

Run: `python run.py`,浏览器逐项核对(对照 spec 的验收清单):

- [ ] 默认浅色,外观与原版一致
- [ ] 点 🌙 → 全页深色(所有区域无残留浅色);点 ☀️ → 切回
- [ ] 刷新 → 保持主题,无闪烁
- [ ] 点「❓ 帮助」→ Modal 弹出
- [ ] 4 个 Tab 都有内容:快速上手(特点+快速开始)、策划(表格式规范+规则)、程序(产出+二进制+扩展)、项目结构(项目结构+License)
- [ ] markdown 渲染正常:表格成表、代码块成深色块、内联 code 有底、标题有色
- [ ] 切换 Tab 内容正确更新
- [ ] ESC / 点遮罩空白 / 点 ✕ → 关闭 Modal
- [ ] 再次打开 Modal → 不重新请求(用缓存,响应迅速)
- [ ] 深色主题下 Modal 也深色,文字可读

- [ ] **Step 3: 提交**

```bash
git add app/web/index.html
git commit -m "feat(web): 帮助 Modal 接线(/api/help + 角色分 Tab)"
```

---

## Task 12: 全量回归与最终提交

**Files:** 无新建,仅验证

- [ ] **Step 1: 跑全部 Python 测试**

Run: `python -m pytest -q`
Expected: 全部 PASS。

- [ ] **Step 2: 启动确认无报错**

Run: `python run.py`,确认控制台无异常,网页可正常访问。

- [ ] **Step 3: 检查 git 状态干净**

Run: `git status`
Expected: nothing to commit, working tree clean(所有 Task 已分别提交)。

- [ ] **Step 4: 更新 README(可选,标记新增功能)**

在 `README.md` 的「特点」列表末尾加一条:

```markdown
- ❓ **内置帮助** — 网页内按角色分 Tab 的帮助文档,内容自动同步自本 README;支持明暗主题
```

并在「项目结构」的 `web/index.html` 行注释补「+ 帮助 Modal + 明暗主题」。

```bash
git add README.md
git commit -m "docs: README 标注帮助界面与明暗主题"
```

---

## 完成判据

- `python -m pytest -q` 全绿(原有测试 + 新增 markdown_lite/api_help 共约 18+ 个)
- 网页浅色与改造前视觉一致
- 深色主题全覆盖、无残留浅色
- 帮助 Modal 4 个 Tab 内容正确、markdown 渲染正常
- README 改动后帮助内容随之更新(重新打开 Modal 即刷新)

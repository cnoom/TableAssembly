# 帮助界面 + 全页明暗主题 设计

> 日期:2026-07-31
> 目标:在网页上新增帮助界面,让策划/程序/运维等各类人员快速上手;并配套全页明暗主题切换。

## 背景与动机

当前网页(`app/web/index.html`)是纯操作界面:配置路径 → 扫描 → 构建。新用户(尤其是不熟悉表格式规范的策划、不熟悉集成方式的程序)打开页面后没有任何引导,只能去翻仓库根的 `README.md`。README 内容完整但面向「读仓库的人」,不是面向「打开网页想快速干活的人」。

本设计在网页内嵌一个按角色分 Tab 的帮助 Modal,内容直接解析自 README,保持单一信息源;同时顺带把页面做成明暗双主题,改善长时间使用的舒适度。

## 范围

**做**:
- 新增后端模块 `app/markdown_lite.py`(零依赖 markdown→HTML 转换 + 段落切片)
- `main.py` 新增 `GET /api/help` 端点
- `index.html` 新增帮助 Modal(按角色分 Tab)
- `index.html` 全页 CSS 变量化 + 明暗主题切换 + `localStorage` 记忆

**不做**:
- 不新增 Python 依赖(requirements.txt 不变)
- 不做全文搜索、不做目录树导航(YAGNI)
- 不动后端导出/校验/生成器任何逻辑

## 关键决策(均已与用户确认)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 内容组织 | 按角色分 Tab | 各类人只看自己那段 |
| 内容来源 | 解析 README 自动填入 | 单一信息源,内容永远最新 |
| 形态 | 主页弹 Modal | 不离开主页,不打断操作 |
| Markdown 渲染 | 后端转 HTML | 职责清晰,可单测 |
| 切片策略 | 方案 A:后端按 `##` 标题切片 | 数据加工在后端,前端只展示;可测 |
| Markdown 依赖 | 不新增,手写转换器 | 项目轻量气质;README 语法子集有限可控 |
| 主题范围 | 全页明暗切换 | 体验一致,不割裂 |
| 默认主题 | 默认浅色,`localStorage` 记忆 | 符合当前观感 |
| 切换入口 | header 右侧图标按钮 | 显眼好找 |

## 架构

### 模块划分

```
app/
  markdown_lite.py   [新增] 纯函数:markdown→HTML 转换 + 按 ## 切片
  main.py            [改]   新增 GET /api/help 端点
  web/index.html     [改]   CSS 变量化 + 明暗主题 + 帮助 Modal + header 按钮
tests/
  test_markdown_lite.py  [新增] 转换器与切片单测
```

### 数据流

```
用户点「❓ 帮助」
   │
   ▼
前端 fetch GET /api/help (首次,之后缓存)
   │
   ▼
main.py: 读 README.md → markdown_lite.split_sections() → 返回 [{id,title,html}]
   │
   ▼
前端: 按 ROLE_MAP 把 sections 分到各角色 Tab → 渲染进 Modal → 显示
```

## 组件设计

### 1. `app/markdown_lite.py`(新增,约 100-130 行)

两个公开函数,纯函数、无副作用:

```python
def markdown_to_html(md: str) -> str:
    """markdown 字符串 → HTML 字符串。支持 README 实际用到的子集。"""

def split_sections(md: str) -> list[dict]:
    """按 ## 标题切段。返回 [{id, title, html}]。
    一级标题(#)及其之前的内容(徽章区)丢弃。"""
```

**支持的 markdown 子集**:

| 语法 | 输出 |
|---|---|
| `#`~`######` | `<h1>`~`<h6>` |
| 普通段落(空行分隔) | `<p>` |
| ` ``` ` 围栏代码块 | `<pre><code>`(内容 HTML 转义,保留原样) |
| GFM 表格(首行表头、第二行 `---` 分隔、`\|` 分列) | `<table><thead><tbody>` |
| `- ` 无序列表 | `<ul><li>` |
| `1. ` 有序列表 | `<ol><li>` |
| `> ` 引用 | `<blockquote>` |
| 行内 `` `code` `` | `<code>` |
| `**bold**` | `<b>` |
| `[text](url)` | `<a href="url">` |

**安全**:所有文本内容经 `html.escape()`,防注入。代码块内容原样保留(转义后)。

**切片算法**:
1. 按行扫描,遇 `## ` 开头 → 新段开始,标题 = 去掉 `## ` 的文本
2. 到下一个 `## ` 或 EOF → 当前段结束
3. `# `(一级标题)及首个 `## ` 之前的内容 → 丢弃(即 README 顶部的 `# TableAssembly` + 徽章)
4. 每段文本调 `markdown_to_html()` 转 HTML
5. 返回 `[{id: 标题原文, title: 标题原文, html}]`(id 用中文原文,前端按 ROLE_MAP 中文匹配,无需锚点转写)

**已知限制(可接受)**:
- 不支持嵌套列表(README 里没有)
- 不支持图片(README 里没有)
- 不支持复杂内联(如 `**粗体+链接**` 组合),走简单串行替换

### 2. `main.py` 新增端点(约 15 行)

```python
@app.get("/api/help")
def api_help() -> dict[str, Any]:
    readme_path = Path(__file__).resolve().parent.parent / "README.md"
    try:
        text = readme_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"ok": False, "error": "README.md 未找到", "sections": []}
    try:
        sections = markdown_lite.split_sections(text)
    except Exception as e:
        return {"ok": False, "error": f"文档解析失败: {e}", "sections": []}
    return {"ok": True, "source": "README.md", "sections": sections}
```

README 路径:`main.py` 在 `app/`,README 在仓库根,即 `app/../README.md`。

### 3. 前端帮助 Modal

**DOM 结构**(加在 `</div><!-- /.wrap -->` 之后、`<script>` 之前):

```html
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

**角色 → 段落映射**(前端 JS 常量):

```javascript
// 只列 ## 二级标题。### 三级标题(如「支持的类型」「各语言形态」)
// 随其所属 ## 段一起进 Tab,无需单独映射。
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
```

**匹配规则(明确无歧义)**:
- 切片产出的是 `##` 段(含其下所有 `###` 子标题、表格、代码块)。ROLE_MAP 的值是 `##` 标题文本列表。
- 一个段归入哪个 Tab:遍历 ROLE_MAP,段 title **精确等于**某列表项 → 归入该角色。一个段只归第一个命中的角色。
- README 实际 10 个 `##` 段:特点、快速开始、表格式规范、产出、自定义校验规则(可选)、校验规则、二进制格式、项目结构、扩展其他语言、License。上面 ROLE_MAP 覆盖全部 10 个。
- 未来 README 新增 `##` 段且没更新 ROLE_MAP → 该段不显示(可接受;如需兜底,未匹配段可收集到一个隐藏的「其他」区,但本期不做)。

**交互**:

| 动作 | 行为 |
|---|---|
| 点「❓ 帮助」 | 首次 fetch `/api/help` 并缓存;填 Tab;默认选中「快速上手」;显示 Modal |
| 点 Tab | 切换 `help_body` 内容(拼接该角色所有段的 HTML) |
| 点 ✕ / 点遮罩 / ESC | 关闭 Modal(`hidden`) |
| 再次打开 | 用缓存,不重新 fetch |

**容错**:
- fetch 失败或 `ok:false` → Modal 内显示 `⚠️ 文档加载失败:xxx`
- 某角色 Tab 无任何匹配段 → Tab 内容显示 `该部分文档暂未找到,请查阅 README.md`

### 4. 全页明暗主题

**机制**:`<html data-theme="light|dark">` + CSS 变量。把现有 `index.html` 内所有硬编码颜色抽成变量。

**配色表**:

| 变量 | 浅色 | 深色 |
|---|---|---|
| `--bg` | `#f5f6f8` | `#1a1d23` |
| `--surface` | `#fff` | `#252932` |
| `--surface-2` | `#fafbfc` | `#2d323d` |
| `--text` | `#222` | `#e4e6eb` |
| `--text-muted` | `#666` | `#9aa0aa` |
| `--text-faint` | `#999` / `#888` | `#7a808a` |
| `--border` | `#e3e6ea` | `#3a3f4a` |
| `--border-light` | `#eee` | `#333842` |
| `--input-border` | `#ccc` | `#444a55` |
| `--primary` | `#4a7dff` | `#5b8eff` |
| `--primary-hover` | `#3a66d8` | `#7aa2ff` |
| `--primary-bg` | `#eef3ff` | `#2a3550` |
| `--header-bg` | `#2b3a55` | `#1e2533` |
| `--log-bg` | `#1e1e1e` | `#111317` |
| `--log-text` | `#d4d4d4` | `#d4d4d4` |
| `--row-hover` | `#f0f5ff` | `#2a3040` |
| `--badge-both-bg`/`text` | `#e6f4ea`/`#1e7e34` | `#1e3a2a`/`#5ac878` |
| `--badge-client-bg`/`text` | `#e7f0ff`/`#1565c0` | `#1a2a4a`/`#6ba6ff` |
| `--badge-server-bg`/`text` | `#fff3e0`/`#b25400` | `#3a2a14`/`#e8a45c` |
| `--code-bg`(行内) | `#f0f2f5` | `#333842` |
| `--field-pill-bg` | `#f0f2f5` | `#333842` |

> 状态色 `.ok`/`.err`/`.warn`(绿/红/橙)两态通用不变(高饱和色在深浅底上都清楚)。
> 日志区本身两态都是深色,只是深色主题下底色更深一点,日志内部的 `.lv-ERROR` 等级色不变。

**header 右侧布局**(主题 + 帮助):

```html
<header>
  <span class="header-title">Excel → 开发数据 导出工具</span>
  <span class="header-actions">
    <button class="icon-btn" onclick="toggleTheme()" title="切换主题">
      <span id="theme_icon">🌙</span>
    </button>
    <button class="help-btn" onclick="openHelp()">❓ 帮助</button>
  </span>
</header>
```

图标语义:**图标代表「点击后切换到的目标」**——当前浅色显示 🌙(切到深色),当前深色显示 ☀️(切回浅色)。

**切换 JS**(约 15 行):

```javascript
function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
  $('theme_icon').textContent = (t === 'dark') ? '☀️' : '🌙';
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(cur === 'dark' ? 'light' : 'dark');
}
// 启动时同步图标(主题已在 head 内联脚本预设)
applyTheme(localStorage.getItem('theme') || 'light');
```

**无 FOUC**:在 `<head>` 最早处加内联脚本,渲染前就设好 `data-theme`:

```html
<script>
  document.documentElement.setAttribute('data-theme',
    localStorage.getItem('theme') || 'light');
</script>
```

**改造范围**:现有 CSS 约 20 处硬编码颜色 → 替换为 `var(--xxx)`;现有 `header` 加 `display:flex; justify-content:space-between; align-items:center`;逻辑代码不动。

## 测试策略

### 单元测试(`tests/test_markdown_lite.py`)

`markdown_lite` 是纯函数,重点测:

- `markdown_to_html`:
  - 各级标题 → 对应 `<h*>`
  - 段落 → `<p>`
  - 围栏代码块 → `<pre><code>`,内部 `<` `>` 被转义
  - GFM 表格 → `<table>`,表头/分隔行/数据行正确,分隔行不渲染成数据
  - 无序/有序列表 → `<ul>`/`<ol>`
  - 行内 code/bold/link
  - HTML 注入:`<script>` 被转义
  - 空串 → `""`
- `split_sections`:
  - 给一段含多个 `##` 的文本 → 返回正确数量、正确标题
  - `# `(一级标题)及首段 `##` 前内容 → 被丢弃
  - 末尾段无后续 `##` → 正常闭合
  - 无任何 `##` → 返回 `[]`
  - 实际 README.md 喂入 → 至少返回 8 个段(README 实际有 10 个 `##`)

### 手动验收

启动 `python run.py`,浏览器打开后逐项验证:
- [ ] 浅色(默认)外观与改造前一致
- [ ] 点 🌙 → 全页切深色,所有区域(含日志/徽章/输入框/表格/Modal)无残留浅色
- [ ] 刷新 → 保持上次主题(无闪烁)
- [ ] 点「❓ 帮助」→ Modal 弹出,4 个 Tab 都有内容
- [ ] 各 Tab 内容正确(策划 Tab 含表格式规范+规则;程序 Tab 含集成+二进制)
- [ ] 帮助内 markdown 渲染正常:表格成表、代码块成深色块、内联 code 有底
- [ ] ESC / 点遮罩 / 点 ✕ → 关闭 Modal
- [ ] 再次打开 Modal → 不重新请求(用缓存)
- [ ] 帮助 Modal 跟随主题(深色下 Modal 也深色)

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| README 改 `##` 标题 → ROLE_MAP 匹配失效,Tab 空白 | 容错:Tab 空时显示「请查阅 README」;ROLE_MAP 集中在一处易改 |
| 手写 markdown 转换器遇 README 未覆盖的语法 | 已限定子集;实际 README 喂入的单测兜底;遇问题可加 `**` 之类的小修补 |
| CSS 变量化遗漏某处 → 深色下残留浅色 | 手动验收清单逐区域检查 |
| `data-theme` 设在 `<html>` 而 CSS 选择器特异性冲突 | 变量定义放 `:root` 与 `[data-theme="dark"]`,变量替换不改变选择器特异性 |

## 非目标 / 未来扩展

- 全文搜索、目录树导航(可后续加)
- 主题色定制(目前固定两套)
- README 改动后帮助页自动热更新(当前需重新打开 Modal 才 fetch,可接受)

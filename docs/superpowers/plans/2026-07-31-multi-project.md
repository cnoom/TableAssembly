# 多项目配置管理 实施记录

> **状态:已完成** ✅(代码已合并至 `main`,提交 `0fdadc7`)
> **对应规格:** `docs/superpowers/specs/2026-07-31-multi-project-design.md`
> 本文档为实施记录,所有 Task 已落地并测试通过。

**Goal:** 在网页中管理多套命名配置(项目),下拉框一键切换,避免不同工程反复覆盖保存。

**Architecture:** `config.json` 升级为 `{projects, active}`;`config.py` 增多项目读写与迁移;`main.py` 增 `/api/projects` 系列端点;`index.html` 加项目下拉框 + 脏检查切换。后端可单测,前端手动验收 + 端到端冒烟。

**Tech Stack:** Python 3.9+ 标准库、FastAPI、原生 HTML/CSS/JS(无前端框架)。无新依赖。

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `app/config.py` | 修改 | `ProjectsConfig` + `load_projects`/`save_projects` + 迁移 + 增删改 + 兼容旧 API |
| `app/main.py` | 修改 | 新增 `/api/projects` 系列端点 |
| `app/web/index.html` | 修改 | 项目下拉框 + 新建/重命名/删除 + 脏检查切换 |
| `config.example.json` | 修改 | 升级为多项目格式示例 |
| `tests/test_config_projects.py` | 新建 | 存储与迁移单测(15) |
| `tests/test_api_projects.py` | 新建 | 端点单测(12) |

---

## Task 1: `app/config.py` 多项目存储与迁移 ✅

- [x] 新增 `ProjectsConfig` dataclass(projects + active)
- [x] `load_projects()`:识别新格式 / 旧平铺格式(迁移写回)/ 文件缺失兜底
- [x] `save_projects()`:保证「至少一个项目 + active 有效」不变量
- [x] `active_project()`、`create_project`、`rename_project`、`delete_project`、`set_active`
- [x] 兼容:`load_config()`/`save_config()` 操作活动项目

**实现要点**:
- 旧格式识别靠「dict 无 `projects` 键」;迁移后 `save_projects` 写回,下次即新格式。
- `rename_project` 保持插入顺序(重建 dict)。
- 多余字段(`extra_unknown_field`)被 `_config_from_dict` 过滤。

---

## Task 2: `app/main.py` 新增端点 ✅

- [x] `GET /api/projects` — 列出项目 + 活动名
- [x] `POST /api/projects` — 新建并切为活动
- [x] `PUT /api/projects/active` — 切换活动项目
- [x] `POST /api/projects/rename` — 重命名(活动项改名同步)
- [x] `DELETE /api/projects` — 删除(query `?name=`,至少留一个)

**实现要点**:
- DELETE 用 query 参数(starlette TestClient 不支持 DELETE 带 `json=`)。
- 错误统一 `{ok:false, error}`,HTTP 200。
- `/api/config` POST 仍是「写活动项目」。

---

## Task 3: `app/web/index.html` UI 与交互 ✅

- [x] `.proj-bar` CSS + 项目下拉框 + 新建/重命名/删除按钮
- [x] `serializeForm` / `isDirty` / `savedSnapshot` 脏检查
- [x] `onProjectChange`:脏则弹三选一确认框(保存当前 / 丢弃 / 取消)
- [x] `newProject` / `renameProject` / `deleteProject`
- [x] `loadConfig` 改为先拉项目列表再填表单;`saveConfig` 保存后更新 snapshot

**实现要点**:
- 三选一确认框用 `.modal-mask` 风格(非 `window.confirm`,因需三个选项)。
- 切换后 `fillForm` + 更新 `savedSnapshot`,表单回到干净态。
- `delRequest` 改为拼 query string。

---

## Task 4: `config.example.json` 示例 ✅

- [x] 升级为 `{projects:{默认, MMO服务端}, active:默认}` 两项目示例

---

## Task 5: 测试 ✅

- [x] `tests/test_config_projects.py`(15):迁移 / 往返 / 增删改 / 兼容旧 API
- [x] `tests/test_api_projects.py`(12):端点 CRUD + `/api/config` 联动

**实现要点**:
- `monkeypatch app.config.CONFIG_FILE` 隔离真实文件。
- 端点测试 `importlib.reload(mainmod)` 吃下新 patch。

---

## Task 6: README 文档同步 ✅

- [x] 「特点」加 🗂️ 多项目条目
- [x] 「快速开始」加下拉切换说明 + 未保存确认提示
- [x] 「项目结构」表 `config.py` 行补「多项目配置持久化(含旧格式自动迁移)」

---

## Task 7: 全量回归与提交 ✅

- [x] `python -m pytest` 全绿
- [x] 端到端冒烟:两项目隔离 / 切换 / 持久化正确
- [x] 旧格式迁移验证
- [x] 提交 `0fdadc7` 推送至 `origin/main`

---

## 完成判据(均满足)

- `python -m pytest` 全绿:**140 passed, 3 skipped**(3 跳过为环境相关 codegen 编译,与本次无关)
- 旧平铺 `config.json` 首次加载自动迁移为「默认」项目,字段不丢,写回新格式
- 网页下拉框可新建/重命名/删除/切换项目
- 切换前未保存修改弹三选一确认,防误丢
- `/api/config` 旧接口语义不变,外部脚本兼容
- 端到端:两个项目配置完全隔离、磁盘持久化结构正确

# 多项目配置管理 设计

> 日期:2026-07-31
> 目标:支持在网页中管理多套命名配置(项目),一键切换,避免不同工程反复覆盖保存。

## 背景与动机

实际开发中常有多个工程分散在不同目录(如:示例项目、MMO 服务端、某独立玩法模块),每个工程有自己的 Excel 输入目录与 Client/Server 输出目录。

当前 `app/config.py` 只支持**单一配置**:一个 `config.json` 文件 ↔ 一个 `AppConfig`。`load_config()` / `save_config()` 直接读写它;所有读取路径(`/api/scan`、`/api/check`、`/api/build`)都拿这同一份配置;前端也只有一个「路径配置」卡片操作它。切换不同工程只能手动覆盖保存,极易丢失/混淆配置。

本设计引入「项目」概念:一份 `config.json` 同时保存多套命名配置,其中一个标记为活动,网页下拉框可一键切换。

## 范围

**做**:
- `config.json` 升级为多项目格式:`{projects:{名称:字段}, active:"名称"}`
- 检测旧平铺格式 → 自动迁移为含单个「默认」项目的新格式(零摩擦升级)
- 后端新增 `/api/projects` 系列端点(列出 / 新建 / 切换 / 重命名 / 删除)
- 前端「路径配置」卡片顶部加项目下拉框 + 新建/重命名/删除按钮
- 切换项目前,若表单有未保存修改,弹「保存当前 / 丢弃 / 取消」三选一确认
- 保留 `load_config` / `save_config` 与 `/api/config` 旧语义(操作活动项目),兼容外部脚本

**不做**:
- 不引入多文件 `configs/*.json`(已评估,单文件更简、读写原子性更好)
- 不做项目导入/导出、跨机器同步
- 不自动保存表单(易误改落盘,且与「保存」按钮语义冲突)

## 关键决策(均已与用户确认)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 存储格式 | 单文件 `config.json` 升级 | 本地工具配置量小;单文件最简、读写原子性好;无需维护多文件索引一致性 |
| UI 入口 | 「路径配置」卡片顶部一行(下拉 + 增删按钮) | 与配置编辑同区,语义集中;切换后立即把该项目路径填入下方表单 |
| 旧配置迁移 | 自动迁移为「默认」项目并设为活动 | 老用户首次启动零摩擦,字段不丢;迁移结果写回磁盘,下次即新格式 |
| 切换交互 | 切换前若表单脏,弹三选一确认 | 防误丢未保存配置;与文档「读取/保存」语义一致 |
| 命名约束 | 仅查重,允许任意非空字符串(含中文、空格) | 本地工具无需文件名安全约束(单文件 JSON 键);最宽松 |

## 架构

### 文件改动

| 文件 | 动作 | 职责 |
|---|---|---|
| `app/config.py` | 改 | 新增 `ProjectsConfig` + 读写迁移 + 增删改 + 兼容旧 API |
| `app/main.py` | 改 | 新增 `/api/projects` 系列端点 |
| `app/web/index.html` | 改 | 项目下拉框 + 增删按钮 + 脏检查切换 |
| `config.example.json` | 改 | 升级为多项目格式示例 |
| `tests/test_config_projects.py` | 新建 | 存储与迁移单测 |
| `tests/test_api_projects.py` | 新建 | 端点单测 |

### 数据结构(`app/config.py`)

```python
@dataclass
class AppConfig:        # 不变,仍是单个项目的字段
    input_dir / client_bin / client_cs / server_bin / server_cs
    client_namespace / server_namespace
    client_lang / server_lang / subdirs_by_table

@dataclass
class ProjectsConfig:   # 新增,多项目集合
    projects: dict[str, AppConfig]   # 名称 -> 配置
    active: str = ""                  # 活动项目名;空表示无活动
```

### 文件格式

新格式(单一信息源,一份文件管所有项目):

```json
{
  "projects": {
    "默认":     { "input_dir": "...", "client_bin": "...", ... },
    "MMO服务端": { "input_dir": "...", "server_lang": "lua", ... }
  },
  "active": "默认"
}
```

### 读写与迁移算法

`load_projects()` 识别两种格式:

1. **新格式**(含 `projects` 键且为 dict):
   - 逐项构造 `AppConfig`(只取已知字段,忽略多余字段)
   - `projects` 为空对象 → 兜底一个「默认」项目
   - `active` 指向不存在的名字 → 回退第一个
2. **旧格式**(平铺字段 dict,无 `projects` 键):
   - 把字段包成 `projects["默认"]`,`active="默认"`
   - **迁移结果写回磁盘**(`save_projects`),下次即新格式
3. **文件不存在 / 解析失败**:返回含一个空「默认」项目的结构(与旧 `load_config()` 兜底行为对齐)

`save_projects()` 保证不变量:至少有一个项目;`active` 必须指向已存在名字(失效则修正为第一个)。

### 项目级增删改(均为「修改 ProjectsConfig + 写盘」一体)

| 操作 | 校验 | 行为 |
|---|---|---|
| `create_project(name)` | 非空 + 不重名 | 新建空 `AppConfig` 并设为活动 |
| `rename_project(old, new)` | 新名非空 + 不重名(可与 old 同) | 保持插入顺序重建 dict;若改的是活动项,`active` 同步改名 |
| `delete_project(name)` | 存在 + **不能删最后一个** | 删除;若删的是活动项,`active` 另选第一个 |
| `set_active(name)` | 存在 | 仅切 `active` |

### 兼容旧 API

| 旧 API | 在新结构下的行为 |
|---|---|
| `load_config()` | 返回 `active_project(load_projects())`(落空返回 `AppConfig()`) |
| `save_config(cfg)` | 把 cfg 写回当前活动项目;无活动则建「默认」 |

这样 `main.py` 里原有的 `load_config()` 调用、以及任何外部脚本都不受影响。

## 端点设计(`app/main.py`)

保留 `/api/config`(GET/POST)语义不变(操作活动项目),新增:

| 方法 + 路径 | body / 参数 | 返回 |
|---|---|---|
| `GET /api/projects` | — | `{ok, projects:[{name}], active}` |
| `POST /api/projects` | `{name}` | 新建并切为活动;`{ok, active, config}` |
| `PUT /api/projects/active` | `{name}` | 切换活动;`{ok, active, config}` |
| `POST /api/projects/rename` | `{old, new}` | 重命名;`{ok, active}` |
| `DELETE /api/projects` | query `?name=` | 删除;`{ok, active, config}` |

**设计要点**:
- 切换的「脏检查」放前端(无状态、简单),后端 `PUT /api/projects/active` 只负责落盘切换。
- DELETE 用 query 参数传 name(HTTP DELETE 带 body 不规范,且 starlette TestClient 不支持 `json=`)。
- 重名 / 非法名 / 删最后一个 → `{ok:false, error:"..."}`,HTTP 200(与项目既有错误返回风格一致)。
- `/api/config` POST 仍是「写活动项目并持久化」,前端「保存配置」按钮不变。

## 前端设计(`app/web/index.html`)

### UI

「路径配置」卡片 `<h2>` 下方插入一行(`.proj-bar`):

```
项目: [ 下拉框 ▼ ]  [＋新建]  [✎重命名]  [🗑删除]
```

### 脏检查机制

```javascript
const FORM_KEYS = ['input_dir', 'client_bin', ...];
function serializeForm() { return JSON.stringify(readForm()); }
let savedSnapshot = serializeForm();   // 最近一次已落盘的活动项目表单快照
function isDirty() { return serializeForm() !== savedSnapshot; }
```

### 下拉切换流程(`onProjectChange`)

```
用户改下拉
   │
   ├── 表单未脏 → PUT /api/projects/active → 填新项目表单 + 更新 snapshot
   │
   └── 表单脏 → 弹三选一确认框
            ├── 保存当前: POST /api/config 写回旧项目 → 再 PUT 切换 → 填新表单 + 更新 snapshot
            ├── 丢弃:     直接 PUT 切换 → 填新表单 + 更新 snapshot
            └── 取消:     下拉还原旧值,不切换
```

### 其他交互

| 动作 | 行为 |
|---|---|
| 页面加载 | `GET /api/projects` 填下拉 → `GET /api/config` 填活动项目表单 → 记 snapshot |
| 新建 | `prompt` 输名称 → `POST /api/projects` → 刷新下拉选中新项 → 填空表单 + snapshot |
| 重命名 | `prompt`(预填当前名)→ `POST /api/projects/rename` → 刷新下拉 |
| 删除 | `confirm`(删活动项额外提示会自动另选)→ `DELETE /api/projects` → 刷新 + 加载新活动表单 |
| 保存配置按钮(已有) | 保存后更新 snapshot,表单回到「干净」状态 |

三选一确认框复用既有 `.modal-mask` 轻量风格(非 `window.confirm`,因后者无法表达三个选项)。

## 测试策略

### 单元测试(`tests/test_config_projects.py`,15 用例)

通过 monkeypatch `app.config.CONFIG_FILE = tmp_path/"config.json"` 隔离,不触碰真实文件:

- 旧平铺格式 → 迁移为「默认」项目,字段正确,多余字段被忽略
- 旧格式迁移后**写回磁盘**,二次加载为新格式
- 文件缺失 / 损坏 → 兜底「默认」项目
- 新格式往返(保存再加载,字段不丢)
- `projects:{}` 空对象 → 兜底
- `active` 失效 → 回退第一个
- `create_project` 重名 / 空名抛错
- `rename_project` 改活动项 → `active` 同步;重名抛错
- `delete_project` 删最后一个 → 拒绝;删活动项 → 另选活动
- `set_active` 不存在抛错
- 兼容:`load_config()`/`save_config()` 在多项目结构下仍工作

### 端点测试(`tests/test_api_projects.py`,12 用例)

用 `TestClient` + monkeypatch + `importlib.reload(mainmod)` 吃下新 `CONFIG_FILE`:

- 列表默认含「默认」
- 新建 / 重名拒绝 / 空名拒绝
- 切换 / 切到不存在拒绝
- 重命名 / 重名拒绝
- 删除 / 删最后一个拒绝 / 删活动自动切换
- `/api/config` 与活动项目联动(写活动项、切换后隔离)

### 端到端冒烟(手动)

`TestClient` 模拟完整工作流:两个项目配置完全隔离、切换正确、磁盘持久化结构正确。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 老用户 `config.json` 被意外破坏 | 迁移只读旧字段;解析失败兜底「默认」项目,不抛异常 |
| `active` 指向已删除项目 | `save_projects` / `active_project` 统一修正为第一个,保证不变量 |
| 多浏览器标签同时改配置 | 本地单用户工具,不做并发控制(与既有单配置行为一致) |
| 误删唯一项目 | `delete_project` 拒绝删最后一个 |
| 切换丢未保存修改 | 前端脏检查 + 三选一确认框兜底 |

## 非目标 / 未来扩展

- 多文件存储 `configs/*.json`(若未来需单独备份/分享某项目配置)
- 项目导入/导出、跨机器同步
- 配置版本字段(目前迁移靠「有无 projects 键」识别,足够)

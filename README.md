# TableAssembly

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![Langs](https://img.shields.io/badge/codegen-C%23%20%7C%20Go%20%7C%20Java%20%7C%20Lua-orange.svg)

> Excel 配置表 → **紧凑二进制 + 多语言数据类**,自带本地网页构建工具,面向 Unity 等游戏工程。

策划在 Excel 里改完表,打开网页点一下「构建」,就能自动产出 `.bytes` 二进制数据和对应的 C# / Go / Java / Lua 读取代码——校验、分包、生成全自动化。

## 特点

- 🔧 **一键构建** — 本地网页可视化,改表 → 扫描 → 校验 → 导出,全流程零命令行
- 🛡️ **强校验** — 类型转换、主键唯一、必填检查逐格诊断,有错阻断导出,杜绝半成品
- 📦 **按端分包** — 用 `#cs` 标记字段归属,前后端各自独立的 `.bytes` 与代码
- 🌐 **多语言** — 内置 C# / Go / Java / Lua 生成器,前后端可分别指定不同语言
- ⚡ **紧凑二进制** — 小端、无字段描述区,运行时零反射、零解析开销
- 🔌 **加载解耦** — 生成的 Reader 只吃 `byte[]`,Resources / Addressables / 包管理由调用方决定

## 快速开始

```bash
# 1. 装依赖(只需一次)
pip install -r requirements.txt

# 2. (可选)从模板生成本地配置;直接启动也会用默认值
cp config.example.json config.json

# 3. 启动,浏览器打开 http://127.0.0.1:9900
python run.py
```

仓库附带了示例表 `sample/Item.xlsx`,可直接试跑。启动后在网页上:

1. **路径配置**:填入 Excel 输入目录(指向 `sample`)、Client/Server 各自的二进制和代码输出目录
2. **扫描表**:查看所有表与校验状态
3. **全部构建**:先校验,通过才导出

> `config.json` 含本机绝对路径,已被 `.gitignore` 忽略;`config.example.json` 是相对路径模板。
> Client / Server 的**代码语言可分别指定**(代码输出目录旁的「语言」框),默认 `cs`。

## 表格式规范

**A 列是「定义列」**,标识该行作用;**B 列起为字段区**,**B 列 = 主键**。

| A 列 | 含义 |
|------|------|
| `##` | 字段类型行 |
| `#name` | 字段名行(代码用标识符) |
| `#desc` | 字段说明行(注释) |
| `#cs` | 归属行:`both` / `client` / `server` |
| `#rule` | 字段规则行(可选,可多行);详见下方「自定义校验规则」 |
| *(空)* | 数据行 |

**示例**

| A | B(id) | C(name) | D(hp) | E(dropList) |
|---|-------|---------|-------|-------------|
| `##` | int | string | int | int[sep=\|] |
| `#name` | id | name | hp | dropList |
| `#desc` | 主键 | 名字 | 血量 | 掉落(\|分隔) |
| `#cs` | both | both | server | client |
|  | 1001 | 木剑 | 50 | 1001\|1002 |

### 支持的类型

- 基础:`int` `float` `bool` `string`
- 数组(默认逗号分隔):`int[]` `float[]` `bool[]` `string[]`
- 自定义分隔符:`int[sep=|]`、`string[sep=;]`、`string[sep=##]`(单/多字符均可)

> 分隔符只影响**解析/校验阶段**;二进制统一存为「数量 + 逐元素」,生成的读取代码不感知分隔符。

## 产出

构建按 `#cs` 归属把字段分到不同包:`both` 列进两端、`client` 列只进 client、`server` 列只进 server。每端产出独立的 `.bytes` 和代码,文件名用 `_c` / `_s` 后缀区分;某表在该端无可见字段则不生成。

```
client_bin/Item_c.bytes   client_cs/{TableReader, ItemData, ItemTable}.cs
server_bin/Item_s.bytes   server_cs/{TableReader, ItemData, ItemTable}.cs
```

代码文件默认平铺在输出目录;在网页勾选「按表名建子目录」后,变为 `Item/ItemData.cs`、`Monster/MonsterData.cs`... 各自独立子目录。

### 各语言形态

所有语言生成的 Reader **都只接收 `byte[]` / `[]byte` / 字节串**,文件加载交给调用方,与 `.bytes` 严格对应(小端)。

| 语言 | 配置值 | 产物 | 说明 |
|------|--------|------|------|
| **C#** | `cs` | `XxxData.cs` + `XxxTable.cs` + `TableReader.cs` | 字段公开;`LoadAsync(byte[])` 返回 `Task`;`Dictionary<主键,Data>` |
| **Go** | `go` | `XxxData.go` + `XxxTable.go` + `TableReader.go` | `encoding/binary`;`Load([]byte) error`;字段首字母大写导出 |
| **Java** | `java` | `XxxData.java` + `XxxTable.java` + `TableReader.java` | `ByteBuffer` 小端;`load(byte[])`;`HashMap` 管理 |
| **Lua** | `lua` | `XxxTable.lua` + `TableReader.lua` | 兼容 5.1+;浮点优先 `string.unpack`(5.3+),旧版手动解码 |

**命名空间 / 包名**:默认按「代码输出目录」最后一级推导(非法字符自动处理),也可在网页手动覆盖,client / server 各自独立。

> Go / Java 生成器会对保留包名兜底:若输出目录名是 `go` / `java`,自动改为 `go_tbl` / `java_tbl`,避免 `package go` 这类编译错误。

### 在 Unity 中使用(C# 示例)

```csharp
var table = new ItemTable();
TextAsset ta = Resources.Load<TextAsset>("Tables/Item_c");
await table.LoadAsync(ta.bytes);
ItemData item = table.Get(1001);   // id, name, hp, dropList ...
```

## 自定义校验规则(可选)

在表里加 `#rule` 定义行,可对**单个字段跨所有行**声明领域约束,校验不过即阻断导出。规则行可写多行(累加),也可留空单元格(只约束部分字段)。

**示例**

| A | B(id) | C(name) | D(hp) | E(dropList) |
|---|-------|---------|-------|-------------|
| `##` | int | string | int | int[sep=\|] |
| `#name` | id | name | hp | dropList |
| `#rule[sep=;]` | unique; sorted | non_empty; regex:^\S+$ | range:0,99999 | elem_range:1,9999 |
| `#rule` | range:1000,9999 | | | |
|  | 1001 | 木剑 | 50 | 1001\|1002 |

**语法**

- 多条规则默认用 `;` 分隔;可在 A 列写 `#rule[sep=##]` 改分隔符(`,` 不允许,与参数分隔符冲突)
- 单条规则:`规则名` 或 `规则名:参数1,参数2`
- 范围参数支持 `*` 表示不限:`range:0,*` = 只设下界

**内置规则**

| 规则 | 参数 | 适用类型 | 作用 |
|------|------|---------|------|
| `unique` | — | 任意标量 | 所有值唯一 |
| `sorted` / `sorted_desc` | — | int/float | 严格递增 / 递减 |
| `non_empty` | — | 任意 | 非空(空串/空数组视为空) |
| `range` | `min,max` | int/float | 值在 [min,max] 内 |
| `len` | `min,max` | 数组 | 数组长度在 [min,max] 内 |
| `elem_range` | `min,max` | int[]/float[] | 每个元素在 [min,max] 内 |
| `regex` | `PATTERN` | string | 正则全匹配 |
| `in` | `a,b,c` | 任意标量 | 值在枚举集合内 |

> 空值(空串/空数组)默认**不触发**逐值规则,由 `non_empty` 显式管空。主键为空仍按 ERROR 处理(内置)。
> `len` 仅作用于数组;字符串长度约束请用 `regex`(如 `regex:^.{1,20}$`,但注意正则含逗号会被当参数分隔,改用不含逗号的写法)。

## 校验规则

| 检查项 | 级别 |
|-------|------|
| 类型转换(每格能否转声明类型) | 错误 |
| 主键唯一、主键非空 | 错误 |
| 数组按各自分隔符切分 + 逐项校验 | 错误 |
| 定义行列数对齐 | 错误 |
| 字段名标识符合法性 / 关键字 | 警告 |
| 必填字段为空 / 空数组 | 警告 |

有错误则**阻断导出**(不产半成品),网页逐表 / 逐行 / 逐列给出原因。

## 二进制格式

小端,无字段描述区(表改了必重导,`.bytes` 与代码总配套):

```
文件头:  magic "ETBL"(4B) + version(2B=1) + rowCount(4B) + fieldCount(2B)
数据区:  按行、按字段顺序
  int 4B | float 4B | bool 1B | string 2B长度+UTF8 | 数组 4B数量+逐元素
```

## 项目结构

```
app/
  main.py           FastAPI 接口 + 网页
  config.py         路径配置持久化
  schema.py         数据模型
  excel_reader.py   Excel 解析(识别 A 列标记 + 数组 sep)
  checker.py        分级校验(错误/警告/通过)
  binary_writer.py  紧凑二进制打包
  exporter.py       按归属分包编排
  codegen/
    base.py         生成器抽象基类
    cs.py           C# 生成器
    go.py           Go 生成器
    java.py         Java 生成器
    lua.py          Lua 生成器
  web/index.html    可视化网页
sample/Item.xlsx    示例表
run.py              启动脚本
```

## 扩展其他语言

已内置 `cs` / `go` / `java` / `lua`。新增语言只需:

1. 在 `app/codegen/` 下新增文件,实现 `CodeGenerator` 协议(`generate` + `shared_files`),参考现有生成器
2. 在 `app/codegen/__init__.py` 注册工厂:`GENERATORS["python"] = lambda ns: PythonGenerator(ns)`

`exporter` 无需改动。

## License

[MIT](./LICENSE) © 2026 cnoom-home

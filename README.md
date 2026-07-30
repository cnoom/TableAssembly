# TableAssembly

把 Excel 表(.xlsx)转成 **二进制数据 + 多语言数据类**(C# / Go / Java / Lua),供 Unity 等游戏工程使用。
附带一个**本地网页可视化工具**,策划改完表 → 网页一键构建 → 自动产出 `.bytes` + 代码。

## 快速开始

```bash
# 1. 装依赖(只需一次)
pip install -r requirements.txt

# 2. (可选)从模板生成本地配置;直接启动也会用默认值
cp config.example.json config.json

# 3. 启动
python run.py
# 浏览器打开 http://127.0.0.1:9900
```

> `config.json`(本机绝对路径)默认被 `.gitignore` 忽略,不会进版本库;`config.example.json` 是相对路径模板。

仓库已附带示例表 `sample/Item.xlsx`,可直接用来试跑:在网页上把「Excel 输入目录」指向 `sample` 文件夹即可。

在网页上:
1. **路径配置** 填入:Excel 输入目录、Client/Server 各自的二进制输出目录和代码输出目录
2. 点 **扫描表** 看到所有表和状态
3. 点 **全部构建**(先校验,通过才导出)

> Client 和 Server 的**代码语言可分别指定**(各代码输出目录后跟一个「语言」输入框),默认都是 `cs`。例如可以让 client 用 `cs`、server 用别的语言(需在 `app/codegen/` 注册对应生成器)。

## 表格式规范

**A 列是「定义列」**,标识该行作用;**B 列起为字段区**,**B 列 = 主键**。

| A(定义列) | 含义 |
|-----------|------|
| `##` | 字段类型行 |
| `#name` | 字段名行(代码用标识符) |
| `#desc` | 字段说明行(注释) |
| `#cs` | 归属行:`both` / `client` / `server` |
| *(空)* | 数据行 |

示例:

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
- 数组 + 自定义分隔符:`int[sep=|]`、`string[sep=;]`、`string[sep=##]`(支持单/多字符)

> 数组的分隔符只影响**解析/校验阶段**;二进制存为「数量 + 逐元素」,生成的 C# 读取代码不感知分隔符。

## 按归属分包

依据 `#cs` 行:
- `both` 列 → 同时进 client 和 server 包
- `client` 列 → 只进 client 包
- `server` 列 → 只进 server 包

输出(各自独立目录,网页可配置):

```
client_bin/  Item_c.bytes  ...     client_cs/  TableReader.cs, ItemData.cs, ItemTable.cs ...
server_bin/  Item_s.bytes  ...     server_cs/  TableReader.cs, ItemData.cs, ItemTable.cs ...
```

代码文件默认直接平铺在代码输出目录下(`ItemData.cs`、`ItemTable.cs`...);多张表就是 `ItemData.cs`、`MonsterData.cs`... 都在同一层。

如果希望按表名分文件夹,可在网页配置里勾选「按表名建子目录」,此时变成 `Item/ItemData.cs`、`Monster/MonsterData.cs`... 各自独立子目录。

文件名带 `_c` / `_s` 后缀区分端。某表在该端无可见字段则不生成。

## 生成的 C# 形态

- `TableReader.cs` —— 通用二进制解析器,**只吃 `byte[]`**,文件加载(Resources/Addressables/包管理)由调用方自行处理
- `XxxData.cs` —— 数据类(`class`),字段公开,`ReadAsync(TableReader)` 返回 `Task`
- `XxxTable.cs` —— 管理类,`LoadAsync(byte[])` + `Get`/`TryGet`/`GetAll`,`Dictionary<主键,Data>`

使用示例(Unity 端):
```csharp
var table = new ItemTable();
TextAsset ta = Resources.Load<TextAsset>("Tables/Item_c");
await table.LoadAsync(ta.bytes);
ItemData item = table.Get(1001);
```

## 支持的代码语言

| 语言 | 命令 | 形态 | 备注 |
|------|------|------|------|
| **C#** | `cs` | `XxxData.cs` + `XxxTable.cs` + `TableReader.cs` | Unity 等客户端默认;字段公开,`LoadAsync(byte[])` |
| **Go** | `go` | `XxxData.go` + `XxxTable.go` + `TableReader.go` | `encoding/binary` + `math.Float32frombits`;`Load([]byte) error`;字段首字母大写(导出) |
| **Java** | `java` | `XxxData.java` + `XxxTable.java` + `TableReader.java` | `ByteBuffer` 小端;`load(byte[])`;`HashMap` 管理 |
| **Lua** | `lua` | `XxxTable.lua` + `TableReader.lua` | 兼容 5.1+;浮点优先 `string.unpack("<f")`(5.3+),旧版手动解码;模块返回 Table |

各语言读取器均**只接收 `byte[]`/`[]byte`/字节串**,文件加载交给调用方,与 `.bytes` 格式严格对应(小端)。

> Go/Java 生成器会对保留包名做兜底(如输出目录名是 `go`/`java` 会自动改为 `go_tbl`/`java_tbl`,避免 `package go` 这类编译错误)。

命名空间默认按「代码输出目录」最后一级推导(非法字符自动处理),也可在网页上手动覆盖;client / server 各自独立。

## 校验规则

| 检查项 | 级别 |
|-------|------|
| 类型转换(每格能否转声明类型) | 错误 |
| 主键唯一、主键非空 | 错误 |
| 数组按各自分隔符切分 + 逐项校验 | 错误 |
| 定义行列数对齐 | 错误 |
| 字段名标识符合法性 / 关键字 | 警告 |
| 必填字段为空 / 空数组 | 警告 |

有错误则**阻断导出**(不产半成品),网页逐表/逐行/逐列给出原因。

## 二进制格式

小端,无字段描述区(表改了必重导,`.bytes` 与 `.cs` 总配套):

```
magic "ETBL"(4B) + version(2B=1) + rowCount(4B) + fieldCount(2B)
数据区: 按行、按字段顺序
  int 4B | float 4B | bool 1B | string 2B长度+UTF8 | 数组 4B数量+逐元素
```

## 项目结构

```
app/
  main.py          FastAPI 接口 + 网页
  config.py        路径配置持久化(config.json)
  schema.py        数据模型
  excel_reader.py  Excel 解析(识别 A 列标记 + 数组 sep)
  checker.py       校验(错误/警告/通过)
  binary_writer.py 紧凑二进制打包
  exporter.py      按归属分包编排
  codegen/
    base.py        生成器抽象基类(可扩展多语言)
    cs.py          C# 生成器
  web/index.html   可视化网页
sample/Item.xlsx   示例表
run.py             启动脚本
```

## 扩展其他语言

已内置 `cs` / `go` / `java` / `lua` 四种。新增语言只需:
1. 在 `app/codegen/` 下新增文件,实现 `CodeGenerator` 协议(`generate` + `shared_files`),参考 `cs.py` / `go.py` / `java.py` / `lua.py`
2. 在 `app/codegen/__init__.py` 注册工厂:`GENERATORS["python"] = lambda ns: PythonGenerator(ns)`

`exporter` 无需改动。前后端可分别指定语言(见「路径配置」中的语言输入框)。

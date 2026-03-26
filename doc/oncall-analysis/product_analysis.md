# Oncall Agent - 产品分析设计文档

## 1. 项目概述

### 1.1 项目背景

基于 [deer-flow 2.0](https://github.com/bytedance/deer-flow) 实现一个 Oncall Agent，供 **RD（研发工程师）** 使用：当接到商家 oncall 投诉后，通过此工具快速定位商品上品表单的字段异常根因，例如：

- 商家反馈：创建 `购物>果蔬生鲜>水果 / 团购` 时，上品表单中找不到"商家平台商品ID"
- 商家反馈：创建 `购物>果蔬生鲜>水果 / 代金券` 时，"券码类型"下拉选项中没有"商家券"

> **使用者**：RD（研发工程师）接到商家 oncall 后，通过 CLI 辅助排查，非商家本人直接使用。

### 1.2 核心定位

- **基座**：deer-flow 2.0 Agent Harness
- **交互方式**：CLI Chat 模式（交互式多轮对话）
- **代码管理**：沙箱隔离 + 智能缓存
- **诊断能力**：模板定位 → 字段确认 → 代码分析 → 根因诊断

---

## 2. 需求分析

### 2.1 核心概念：五元组

模板定位依赖以下五个维度唯一确定一张上品表单：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `category_id` | int | 叶子类目 ID（对应类目树路径） | `购物>果蔬生鲜>水果` 对应的 ID |
| `product_type` | int | 商品类型 | 团购 / 代金券 / 外卖 / ... |
| `product_sub_type` | int | 商品子类型 | 根据 product_type 进一步细分 |
| `template_type` | int | 模板类型，默认商品（枚举值 `1`） | `1` |
| `template_sub_type` | int | 模板子类型，默认单品（枚举值 `0`） | `0` |

> MCP `bytedance-mcp-ace_ai` 的 Tool：`ace_ai_locate_template` 输入类目路径文本，返回候选五元组列表，RD 从中选择并确认。

### 2.2 字段诊断状态分类

诊断一个字段时，结论必须落在以下三种状态之一：

| 状态 | 含义 | 根因方向 |
|------|------|----------|
| **模板不存在** | 当前五元组找不到对应模板 | 类目/类型配置问题 |
| **字段不存在** | 模板 schema 中没有该字段定义 | 字段未配置或未发布 |
| **成功定位模板、字段** | 定位到模板、字段schema、组件代码，进行oncall分析 | 联动逻辑分析 schema 和 代码 |

### 2.3 用户场景

| 场景 | 描述 | 期望输出 |
|------|------|----------|
| 字段缺失 | 商家找不到预期字段 | 字段是否存在 + 为什么没显示 |
| 选项不全 | 字段下拉选项与预期不符 | 选项配置逻辑 + 影响因素 |
| 交互异常 | 字段表现不符合预期 | 组件实现分析 + 联动逻辑解释 |

### 2.4 功能需求

- **模板定位**：通过 MCP `ace_ai_locate_template` 获取五元组候选，RD 确认
- **字段确认**：精确定位字段，支持模糊匹配和人工确认
- **代码检索**：在组件仓库中定位实现代码（schema + 组件源码）
- **联动分析**：同时分析 schema `x-reactions`（静态）和 `effects` 函数（动态运行时）
- **诊断报告**：输出结构化分析报告，包含根因和建议操作

### 2.5 约束条件

- 代码检索不跳出当前模板和组件
- 所有关键信息（五元组、字段）需 RD 确认后才进入下一阶段
- 每次诊断前检查代码仓库是否为最新
- 支持追问和反馈修正

---

## 3. 技术架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLI Chat Interface                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Session    │  │   Command    │  │   Status Display     │  │
│  │   Manager    │  │   Router     │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         └─────────────────┴─────────────────────┘              │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DeerFlowClient                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Thread     │  │   Stream     │  │   Interrupt          │  │
│  │   Manager    │  │   Handler    │  │   Handler            │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐  ┌──────────────┐  ┌──────────────┐
│   MCP Tools     │  │  Sandbox     │  │   Index      │
│                 │  │  Tools       │  │   Manager    │
│ - ace_ai_xxx    │  │              │  │              │
│ - goods_xxx     │  │ - bash       │  │ - Component  │
│                 │  │ - read_file  │  │ - Schema     │
└─────────────────┘  │ - glob/grep  │  │ - Cache      │
                     └──────┬───────┘  └──────┬───────┘
                            │                   │
                            ▼                   ▼
              ┌───────────────────────────────────────┐
              │   Repository (Sandbox)                │
              │   /mnt/user-data/workspace/repos/     │
              │   └── fe_ls_tobias_goods_mono/        │
              │       ├── packages/components/        │
              │       └── .oncall-index/              │
              └───────────────────────────────────────┘
```

### 3.2 MCP 工具说明

Agent 通过 MCP 协议访问平台服务，MCP接入方式

```
{
  "mcpServers": {
    "bytedance-mcp-ace_ai": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "--registry",
        "https://bnpm.byted.org",
        "-y",
        "@byted/mcp-proxy@latest"
      ],
      "env": {
        "MCP_SERVER_PSM": "bytedance.mcp.ace_ai",
        "MCP_GATEWAY_REGION": "CN"
      }
    }
  }
}
```

### 3.3 代码仓库管理

#### 沙箱路径结构

```
/mnt/user-data/workspace/
├── repos/
│   └── fe_ls_tobias_goods_mono/       # 组件代码仓库
│       ├── .git/
│       ├── packages/components/src/goods/
│       └── .oncall-index/             # 本地缓存索引
│           ├── meta.yaml              # 缓存元数据
│           ├── component-index.json   # 组件索引
│           └── schema-cache/          # schema缓存目录
```

#### 仓库同步策略

| 触发时机 | 操作 | 说明 |
|----------|------|------|
| 首次启动 | `git clone --depth 1 --sparse` | 稀疏克隆，只拉组件目录 |
| 每次诊断前 | `git fetch` + 版本对比 | 检查是否落后 master |
| 检测到落后 | `git pull --ff-only` + 重建索引 | Fast-forward 更新，失败则提示 RD 手动处理 |

### 3.4 缓存机制

#### 两级缓存架构

| 级别 | 内容 | 粒度 | 更新策略 |
|------|------|------|----------|
| 一级 | 组件索引 | 组件级 | 代码落后时重建 |
| 二级 | Schema 缓存 | 五元组级 | TTL 24 小时过期 |

#### 缓存元数据格式

```yaml
# .oncall-index/meta.yaml
version: "1.0"
lastSync:
  commitHash: "a1b2c3d4e5f6"
  timestamp: "2026-03-26T14:30:00+08:00"
  branch: "master"
indexStats:
  totalComponents: 156
  totalSchemas: 42
cachePolicy:
  schemaTTL: "24h"
  indexAutoRebuild: true
```

#### 组件索引格式

```json
{
  "components": {
    "InputField": {
      "name": "InputField",
      "category": "form-input",
      "path": "packages/components/src/goods/InputField",
      "mainFile": "index.tsx",
      "hasSchema": true,
      "hasEffects": true,
      "effectsFile": "effects.ts",
      "lastIndexed": "2026-03-26T14:30:00Z"
    }
  },
  "categories": {
    "form-input": ["InputField", "TextArea", "NumberInput"],
    "form-select": ["SelectField", "Cascader"]
  }
}
```

---

## 4. CLI Chat 模式详细设计

### 4.1 启动体验

```bash
$ python -m oncall_agent

🦌 Oncall Agent v1.0
基于 DeerFlow 的商品问题诊断助手

正在初始化...
📦 代码仓库检查: master@a1b2c3d (最新)
📊 组件索引: 156个组件已加载

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
请输入商家问题 (输入 /help 查看命令，/quit 退出):

>
```

### 4.2 会话状态管理

```python
class OncallSession:
    """CLI会话状态"""

    def __init__(self):
        self.thread_id: str              # DeerFlow线程ID
        self.turn_count: int = 0         # 对话轮数
        self.diagnosis_stage: str = "idle"  # 当前阶段

        # 诊断上下文
        self.quintuple: dict = None      # 已确认的五元组
        self.field: dict = None          # 已确认的字段
        self.component: dict = None      # 定位的组件

        # 缓存状态
        self.repo_synced: bool = False
        self.index_loaded: bool = False
```

#### 诊断阶段状态机

```
┌───────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│ idle  │───▶│ template  │───▶│  field    │───▶│ analyzing │───▶│  report   │
│(待机) │    │ (模板定位) │    │ (字段确认) │    │ (代码分析) │    │ (报告生成)│
└───────┘    └─────┬─────┘    └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
                   │                │                │                │
                   ▼                ▼                ▼                ▼
             ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
             │ INTERRUPT│    │ INTERRUPT│    │ 加载代码  │    │  完成     │
             │(选择模板)│    │(确认字段)│    │ 分析逻辑  │    │  输出     │
             └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 4.3 诊断流程详细交互

#### 阶段 1: 模板定位

```
> 为什么水果团购没有商家平台商品ID？

🔍 正在定位商品模板...

找到 3 个可能匹配：
  1) 购物 > 果蔬生鲜 > 水果 (标准类目)
  2) 购物 > 果蔬生鲜 > 水果礼盒 (特殊类目)
  3) 购物 > 生鲜 > 水果批发 (批发类目)

请选择 (输入序号，或描述具体类目)：
> 1

✅ 已确认模板：
   类目: 购物 > 果蔬生鲜 > 水果
   类型: 团购
```

#### 阶段 2: 字段确认

```
🔍 正在检索字段配置...

找到相似字段：
  1) 商家平台商品ID (merchant_product_id)
  2) 商家商品编码 (merchant_code)
  3) 外部商品ID (external_product_id)

请确认或修正字段名：
> 1

✅ 已确认字段：商家平台商品ID (merchant_product_id)
```

#### 阶段 3/4: 代码检索与分析

```
📦 检查代码仓库... [最新]
📄 定位组件实现... [InputField]
🔍 分析联动逻辑... [完成]
```

#### 阶段 5: 生成报告

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 诊断报告

1. 问题概述
   商家反馈：创建水果团购时缺少"商家平台商品ID"字段

2. 模板信息
   ┌──────────┬─────────────────────┐
   │ 商品类目 │ 购物>果蔬生鲜>水果   │
   │ 商品类型 │ 团购                │
   └──────────┴─────────────────────┘

3. 字段分析
   字段名称：商家平台商品ID
   当前状态：✅ 存在但条件显示

4. 联动逻辑
   该字段仅在"商品来源=外部系统"时显示
   当前表单未选择商品来源，或选择为"自建"

5. 结论
   字段存在，但受联动条件控制未显示

6. 建议
   检查"商品来源"字段设置，选择"外部系统"后
   "商家平台商品ID"将自动显示
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

有疑问可以继续追问，或输入新问题开始诊断
>
```

### 4.4 追问模式（上下文保持）

```
> 什么是商品来源？

💡 补充说明

"商品来源"是商品基础信息字段，选项包括：
  - 自建：商家在平台直接创建
  - 外部系统：从ERP/其他系统同步
  - 第三方：来自第三方供货

当选择"外部系统"时，需要填写：
  - 商家平台商品ID (用于关联外部系统商品)
  - 外部系统类型

当前诊断上下文仍保留，可继续追问或 /reset 重置
```

---

## 5. 系统命令设计

| 命令 | 功能 | 输出示例 |
|------|------|----------|
| `/help` | 显示所有可用命令 | 命令列表和帮助说明 |
| `/status` | 显示当前会话状态 | 阶段、已确认信息、缓存状态 |
| `/reset` | 重置当前诊断 | 清空当前诊断上下文，回到 idle |
| `/history` | 显示对话历史 | 本轮对话的问题和回答摘要 |
| `/repo` | 手动触发代码同步 | 同步结果和版本信息 |
| `/models` | 切换LLM模型 | 可用模型列表 |
| `/quit` 或 `/q` | 退出会话 | 保存会话并退出 |

### `/status` 输出示例

```
> /status

📊 当前会话状态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
会话ID: thread_abc123
对话轮数: 3
诊断阶段: 报告已生成

已确认信息：
  ✅ 模板：购物>果蔬生鲜>水果 / 团购
  ✅ 字段：商家平台商品ID
  ✅ 组件：InputField

代码仓库：master@a1b2c3d (最新)
组件索引：已加载 (156个组件)
```

---

## 6. 技术实现要点

### 6.1 DeerFlowClient 集成

```python
class OncallChatCLI:
    """主CLI类"""

    def __init__(self):
        self.client = DeerFlowClient()
        self.session = OncallSession()

    async def start(self):
        """启动交互式会话"""
        # 初始化
        await self._init_repository()
        await self._load_index()
        self.session.thread_id = await self._create_thread()

        # 主循环
        while self.running:
            user_input = await self._prompt("> ")
            await self._handle_input(user_input)

    async def _chat_stream(self, message: str):
        """流式对话"""
        async for event in self.client.stream(
            message,
            thread_id=self.session.thread_id
        ):
            match event.type:
                case "messages-tuple":
                    content = event.data.get("content", "")
                    print(content, end="", flush=True)
                case "values":
                    if interrupt := event.data.get("interrupt"):
                        await self._handle_interrupt(interrupt)
```

### 6.2 代码读取范围控制

```yaml
read_scope:
  primary:
    - "{componentPath}/index.tsx"
    - "{componentPath}/index.ts"
  secondary:
    - "{componentPath}/schema.ts"
    - "{componentPath}/interface.ts"
    - "{componentPath}/effects.ts"      # 运行时联动逻辑
    - "{componentPath}/effects/index.ts"
  exclude:
    - "**/node_modules/**"
    - "**/__tests__/**"
    - "**/*.test.ts"

limits:
  max_lines_per_file: 200
  max_files_per_component: 4           # 新增 effects 文件
```

---

## 7. Prompt 设计（初版）

### 7.1 System Prompt

```
你是一个专门诊断商品上品表单问题的 Oncall 助手，帮助 RD 快速定位商家反馈的字段异常根因。

## 工作上下文
- 上品表单基于 Formily 框架实现
- 每张表单由「五元组」唯一确定：category_id / product_type / product_sub_type / template_type / template_sub_type
- 字段的显示/隐藏可能由两种机制控制：
  1. schema 中的 x-reactions（静态声明式联动）
  2. effects 函数中的运行时逻辑（动态联动）

## 诊断流程
1. 通过 ace_ai_locate_template 定位模板候选，等待 RD 确认五元组
2. 通过 ace_ai_search_field 查找字段，等待 RD 确认字段
3. 读取 MCP 返回的 schema，分析字段的 x-reactions
4. 若字段存在 effects 引用，读取代码仓库中的 effects.ts 分析运行时逻辑
5. 输出结构化诊断报告

## 诊断结论必须明确三选一
- 【模板不存在】：无法通过五元组找到对应模板
- 【字段不存在】：模板 schema 中没有该字段定义
- 【字段存在但隐藏】：字段在 schema 中，但被联动条件隐藏，需说明触发条件

## 输出规范
- 每次确认关键信息后，明确说"✅ 已确认：..."
- 分析过程保持简洁，不要重复已知信息
- 诊断报告必须包含：结论、根因、触发条件（若为隐藏）、建议操作
- 若 effects 中存在复杂运行时逻辑无法静态分析，需明确标注"⚠️ 需要运行时验证"
```

### 7.2 联动分析 Prompt（代码读取后注入）

当读取到组件代码后，通过以下 prompt 引导分析：

```
以下是字段 "{field_key}" 所在组件的相关代码：

[Schema x-reactions]
{reactions_json}

[Effects 运行时逻辑（如有）]
{effects_code}

请分析：
1. 该字段在什么条件下会被隐藏（hidden=true）？
2. 触发条件依赖哪些其他字段的值？
3. 商家当前场景（{scenario_description}）是否满足隐藏条件？
4. 如何操作可以让字段显示？

注意：
- x-reactions 中的表达式 `{{$deps[n] !== 'xxx'}}` 表示当依赖字段不等于 'xxx' 时隐藏
- effects 中通常用 onFieldValueChange 监听字段变化并设置其他字段状态
- 若 effects 逻辑依赖接口数据或用户权限，标注"需运行时验证"
```

### 7.3 诊断报告模板

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 诊断报告

【结论】字段存在但隐藏 / 字段不存在 / 模板不存在（三选一）

【模板信息】
  类目路径：{category_path}
  商品类型：{product_type} / {product_sub_type}

【字段信息】
  字段名称：{field_title}（{field_key}）
  所在组件：{component_name}

【根因分析】
  联动类型：静态 x-reactions / 动态 effects（注明来源）
  隐藏条件：当 {dependency_field} = {value} 时，该字段隐藏
  当前状态：{current_state_analysis}

【建议操作】
  {actionable_suggestion}

【置信度】高 / 中（需运行时验证）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 8. 错误处理策略

| 场景 | 处理策略 | 用户反馈 |
|------|----------|----------|
| 仓库克隆失败 | 提示检查网络/权限，支持手动指定路径 | "克隆失败，请检查网络或手动指定路径" |
| git pull 失败（非 fast-forward） | 停止自动操作，提示 RD 手动处理 | "检测到非线性提交，请手动执行 git pull" |
| MCP 服务不可用 | 降级到本地缓存，提示使用缓存数据 | "MCP 服务不可用，使用缓存继续" |
| 组件未找到 | 扩大搜索范围到整个仓库 | "未找到组件，正在扩大搜索..." |
| 字段未找到 | 列出该模板所有可用字段 | "未找到字段，可用字段如下：" |
| effects 代码复杂无法静态分析 | 标注置信度为"中"，提示运行时验证 | "⚠️ 部分逻辑需运行时验证" |
| LLM 调用失败 | 重试 3 次 | "分析服务暂时不可用，请稍后重试" |
| 用户中断 | 保存会话上下文到本地文件 | "会话已保存，下次启动时自动恢复" |

---

## 9. 性能预估

| 操作 | 预估耗时 | 优化策略 |
|------|----------|----------|
| 代码同步 (git fetch/pull) | 2-5s | 稀疏克隆，只拉组件目录 |
| 索引构建（首次） | 5-10s | 全量扫描 |
| 索引更新（增量） | 1-3s | 只更新变更组件 |
| 模板定位 (MCP) | 1-3s | 结果缓存 |
| Schema 查询 (MCP) | 1-3s | TTL 缓存 |
| 组件代码读取（含 effects） | <1s | 本地文件系统 |
| LLM 分析 | 5-15s | 流式输出 |
| **总计（冷启动）** | **15-40s** | - |
| **总计（热缓存）** | **<10s** | 索引和 schema 已缓存 |

> **启动进度反馈**：冷启动期间通过进度条展示各阶段耗时，避免用户误认为卡死。

---

## 10. 配置管理

### 10.1 配置文件位置

```yaml
# ~/.config/oncall-agent/config.yaml
deerflow:
  endpoint: "http://localhost:2026"
  defaultModel: "claude-sonnet-4-6"

repository:
  remoteUrl: "https://code.byted.org/life_service/fe_ls_tobias_goods_mono.git"
  localPath: "~/.cache/oncall-agent/repos/fe_ls_tobias_goods_mono"
  sparsePaths: ["packages/components/src/goods"]

cache:
  indexPath: ".oncall-index"
  schemaTTL: 86400
  maxCacheSize: "500MB"

session:
  persistPath: "~/.config/oncall-agent/sessions/"  # 会话自动持久化路径
  autoRestore: true                                  # 启动时自动恢复上次会话

mcp:
  aceAi:
    serverName: "ace_ai"
    tools:
      - ace_ai_locate_template
      - ace_ai_get_schema
      - ace_ai_search_field
```

### 10.2 环境变量覆盖

```bash
ONCALL_DF_ENDPOINT=http://localhost:2026
ONCALL_REPO_PATH=/custom/path/to/repo
ONCALL_CACHE_TTL=86400
ONCALL_SESSION_PATH=~/.config/oncall-agent/sessions/
ONCALL_DEBUG=true
```

### 10.3 会话持久化

会话上下文（五元组、字段、组件、诊断阶段）在每次用户输入后自动保存到本地文件。下次启动时检测到未完成会话，自动询问是否恢复：

```
检测到上次未完成的诊断会话（2026-03-26 14:30）：
  模板：购物>果蔬生鲜>水果 / 团购
  字段：商家平台商品ID
  阶段：代码分析中

是否恢复？(y/n):
```

---

## 11. 扩展性考虑

| 扩展点 | 设计预留 |
|--------|----------|
| 多仓库支持 | 索引结构支持 `repos/{name}/` 多级 |
| 字段级索引 | metadata 中可扩展 `exportedFields`、`referencedInEffects` |
| 历史诊断记录 | 保存到 `~/.config/oncall-agent/history/`，支持 `/history` 命令浏览 |
| 批量诊断 | 支持输入 JSON 文件，顺序执行多条 oncall |
| Web UI | DeerFlow 前端通过技能调用同一逻辑，CLI 与 Web 共享 Agent 核心 |

---

## 12. 关键设计决策总结

| 决策 | 选择 | 理由 |
|------|------|------|
| 缓存粒度 | 组件级 | 平衡查询速度和资源消耗 |
| 同步策略 | fast-forward only | 避免自动 rebase 破坏本地状态 |
| 代码读取 | 限制在当前组件（含 effects） | 防止分析范围无限扩大 |
| 联动分析 | 静态 reactions + 动态 effects 双路径 | 覆盖所有隐藏场景 |
| 诊断结论 | 三态分类（模板不存在/字段不存在/隐藏） | 结论明确，避免歧义 |
| 交互方式 | 多轮 interrupt | 确保五元组和字段信息经 RD 确认 |
| 会话持久化 | 自动保存 + 启动恢复 | 应对 oncall 中途中断场景 |

---

*文档版本: v1.1*
*最后更新: 2026-03-26*

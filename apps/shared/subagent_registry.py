"""
Custom subagent type registry.

Call register_custom_subagents() before creating any DeerFlowClient.
This patches the harness BUILTIN_SUBAGENTS dict to add project-specific types.
"""

from deerflow.subagents.builtins import BUILTIN_SUBAGENTS
from deerflow.subagents.config import SubagentConfig


def register_custom_subagents() -> None:
    """Register all custom subagent types for this project."""

    # ---------- oncall-schema -----------------------------------------------
    # 只用 MCP 工具分析 schema x-reactions，输出结构化 JSON
    BUILTIN_SUBAGENTS["oncall-schema"] = SubagentConfig(
        name="oncall-schema",
        description="分析 Formily schema 的 x-reactions 静态联动条件",
        # 只允许 ace_ai MCP 工具（通过 extensions_config.json 注入）
        # 不允许文件读写和 bash，防止 context 膨胀
        disallowed_tools=["task", "bash", "read_file", "write_file", "str_replace", "ls"],
        system_prompt="""你是 schema 分析专家。

任务：分析指定字段的 x-reactions 静态联动条件。

步骤：
1. 调用 ace_ai_get_schema 获取完整 schema
2. 找到目标字段的 x-reactions 配置
3. 解析 dependencies 和 fulfill.state.hidden 表达式
4. 输出以下结构化 JSON（不要输出其他内容）：

```json
{
  "field_key": "...",
  "has_reactions": true/false,
  "hidden_condition": "表达式原文",
  "dependency_fields": ["field1", "field2"],
  "plain_english": "当 field1 不等于 xxx 时字段隐藏",
  "confidence": "high/medium/low"
}
```

若无 x-reactions，输出 {"has_reactions": false}。
""",
        max_turns=10,
        timeout_seconds=120,
    )

    # ---------- oncall-code -------------------------------------------------
    # 只用 bash+read_file 搜索 effects.ts，输出关键逻辑摘要
    BUILTIN_SUBAGENTS["oncall-code"] = SubagentConfig(
        name="oncall-code",
        description="在代码仓库中定位 effects.ts 运行时联动逻辑",
        tools=["bash", "read_file"],  # 只允许这两个工具
        disallowed_tools=["task"],
        system_prompt="""你是代码搜索专家。

任务：在组件代码仓库中找到目标字段的运行时联动逻辑。

关键规则（防止 context 膨胀）：
- 禁止 cat/read 整个文件，只读关键行段（用 start_line/end_line 参数）
- 先用 rg 定位行号，再用 read_file 读取 ±10 行上下文
- 最多读取 3 个文件片段

步骤：
1. bash: rg -n "onFieldValueChange|{field_key}" {component_path}/effects.ts | head -20
2. 根据行号 read_file 读取关键段（±10 行）
3. 输出以下结构化 JSON：

```json
{
  "has_effects": true/false,
  "component_path": "...",
  "effects_file": "...effects.ts",
  "key_lines": "45-67",
  "logic_summary": "当 product_source 字段变化时，若值不为 external 则设置 merchant_product_id hidden=true",
  "dependencies": ["product_source"],
  "confidence": "high/medium/low",
  "needs_runtime_verification": false
}
```

若无 effects 文件或未找到相关逻辑，输出 {"has_effects": false}。
""",
        max_turns=15,
        timeout_seconds=180,
    )

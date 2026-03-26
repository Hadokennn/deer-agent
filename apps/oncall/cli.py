"""Oncall Agent CLI — 商品上品表单诊断助手"""

import os
import sys
from pathlib import Path

# 设置 DEER_FLOW_HOME 到项目根（agents/ skills/ memory.json 都在这里）
PROJECT_ROOT = Path(__file__).parent.parent.parent
os.environ.setdefault("DEER_FLOW_HOME", str(PROJECT_ROOT))
os.environ.setdefault("DEER_FLOW_CONFIG_PATH", str(PROJECT_ROOT / "config.yaml"))
os.environ.setdefault("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(PROJECT_ROOT / "extensions_config.json"))

# 加载 .env（如果存在）
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# 注册自定义子 agent 类型（必须在 import deerflow.client 之前完成）
from apps.shared.subagent_registry import register_custom_subagents
register_custom_subagents()

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from deerflow.client import DeerFlowClient
from rich.console import Console
from rich.prompt import Prompt

console = Console()


def _make_client() -> DeerFlowClient:
    db_path = PROJECT_ROOT / "checkpoints.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return DeerFlowClient(
        config_path=str(PROJECT_ROOT / "config.yaml"),
        checkpointer=checkpointer,
        agent_name="oncall",
        model_name="kimi-k2.5",
        thinking_enabled=False,
        subagent_enabled=True,
        plan_mode=False,
    )


def _run_session(client: DeerFlowClient, thread_id: str) -> None:
    console.print("\n[bold green]🦌 Oncall Agent[/bold green] — 商品上品表单诊断助手")
    console.print("输入 [bold]/quit[/bold] 退出，[bold]/reset[/bold] 新建诊断\n")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]>[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]退出[/dim]")
            break

        if not user_input.strip():
            continue

        cmd = user_input.strip().lower()
        if cmd in ("/quit", "/q", "/exit"):
            break
        if cmd == "/reset":
            import uuid
            thread_id = str(uuid.uuid4())
            console.print(f"[dim]新会话已创建: {thread_id[:8]}[/dim]\n")
            continue

        # 流式输出
        console.print()
        pending_clarification = None

        for event in client.stream(user_input, thread_id=thread_id):
            if event.type == "messages-tuple":
                data = event.data
                if data.get("type") == "ai" and data.get("content"):
                    console.print(data["content"], end="")
                    sys.stdout.flush()
                elif data.get("type") == "tool":
                    tool_name = data.get("name", "")
                    if tool_name == "ask_clarification":
                        # ClarificationMiddleware 会把问题放在 content 里
                        pending_clarification = data.get("content", "")

            elif event.type == "values":
                # 检测 interrupt（ask_clarification 触发）
                interrupt_data = event.data.get("interrupt")
                if interrupt_data and not pending_clarification:
                    pending_clarification = (
                        interrupt_data.get("question")
                        or interrupt_data.get("message")
                        or str(interrupt_data)
                    )

            elif event.type == "end":
                console.print()  # 换行

        # 如果有 clarification 请求，等待用户回复后继续
        if pending_clarification:
            console.print(f"\n[yellow]{pending_clarification}[/yellow]")
            try:
                answer = Prompt.ask("[bold cyan]>[/bold cyan]")
                # 把答案作为下一轮消息发送（harness 会 resume interrupted graph）
                for event in client.stream(answer, thread_id=thread_id):
                    if event.type == "messages-tuple":
                        data = event.data
                        if data.get("type") == "ai" and data.get("content"):
                            console.print(data["content"], end="")
                            sys.stdout.flush()
                    elif event.type == "end":
                        console.print()
            except (EOFError, KeyboardInterrupt):
                pass

        console.print()


def main() -> None:
    import uuid
    thread_id = str(uuid.uuid4())

    client = _make_client()
    _run_session(client, thread_id)


if __name__ == "__main__":
    main()

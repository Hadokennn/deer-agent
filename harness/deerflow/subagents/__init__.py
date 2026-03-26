from .config import SubagentConfig

__all__ = [
    "SubagentConfig",
    "SubagentExecutor",
    "SubagentResult",
    "get_subagent_config",
    "list_subagents",
]


def __getattr__(name: str):
    """Lazy imports to break circular dependency with deerflow.agents."""
    if name in ("SubagentExecutor", "SubagentResult"):
        from .executor import SubagentExecutor, SubagentResult  # noqa: PLC0415
        globals()["SubagentExecutor"] = SubagentExecutor
        globals()["SubagentResult"] = SubagentResult
        return globals()[name]
    if name in ("get_subagent_config", "list_subagents"):
        from .registry import get_subagent_config, list_subagents  # noqa: PLC0415
        globals()["get_subagent_config"] = get_subagent_config
        globals()["list_subagents"] = list_subagents
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

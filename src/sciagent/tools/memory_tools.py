from __future__ import annotations

from smolagents import Tool

from sciagent.memory import ResearchMemory


class ArchiveArtifactTool(Tool):
    """将关键产物存入 ResearchMemory。"""

    name = "archive_artifact_tool"
    description = "把关键中间产物归档到 ResearchMemory，便于后续引用。"
    inputs = {
        "key": {"type": "string", "description": "存档键名"},
        "value": {"type": "string", "description": "存档内容（文本化）"},
    }
    output_type = "string"

    def __init__(self, memory: ResearchMemory):
        super().__init__()
        self._memory = memory

    def forward(self, key: str, value: str) -> str:  # type: ignore[override]
        self._memory.archive(key, value)
        return f"OK: 已归档 {key}"


class MemorySummaryTool(Tool):
    """输出 ResearchMemory 摘要。"""

    name = "memory_summary_tool"
    description = "输出当前 ResearchMemory 的摘要信息。"
    inputs = {
        "max_items": {
            "type": "integer",
            "description": "最多展示条目数",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, memory: ResearchMemory):
        super().__init__()
        self._memory = memory

    def forward(self, max_items: int = 10) -> str:  # type: ignore[override]
        return self._memory.summary(max_items=max_items)

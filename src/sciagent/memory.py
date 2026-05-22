from __future__ import annotations

from typing import Any, Dict, List


class ResearchMemory:
    """ResearchAgent 的轻量记忆系统（档案+工作摘要）。"""

    def __init__(self) -> None:
        self._archive: Dict[str, Any] = {}
        self._history: List[str] = []

    def archive(self, key: str, value: Any) -> None:
        """存档关键产物。"""
        self._archive[key] = value
        self._history.append(key)

    def get(self, key: str, default: Any | None = None) -> Any:
        """读取存档。"""
        return self._archive.get(key, default)

    def summary(self, max_items: int = 10) -> str:
        """生成简短摘要，供 ReAct 上下文使用。"""
        if not self._history:
            return "当前无已归档内容。"
        recent = self._history[-max_items:]
        lines = ["已归档关键产物："]
        for key in recent:
            value = self._archive.get(key)
            preview = str(value)
            if len(preview) > 200:
                preview = preview[:200] + "..."
            lines.append(f"- {key}: {preview}")
        return "\n".join(lines)

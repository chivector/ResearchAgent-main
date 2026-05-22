from __future__ import annotations

from pathlib import Path

from smolagents import Tool


class ReadTextFileTool(Tool):
    """读取文本文件工具。"""

    name = "read_text_file"
    description = "读取文本文件内容，返回字符串。"
    inputs = {
        "path": {"type": "string", "description": "文件路径"},
        "encoding": {
            "type": "string",
            "description": "编码，默认 utf-8",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(self, path: str, encoding: str = "utf-8") -> str:  # type: ignore[override]
        file_path = Path(path)
        if not file_path.exists():
            return f"Error: 文件不存在: {file_path}"
        return file_path.read_text(encoding=encoding)


class WriteTextFileTool(Tool):
    """写入文本文件工具。"""

    name = "write_text_file"
    description = "写入文本文件内容，自动创建目录。"
    inputs = {
        "path": {"type": "string", "description": "文件路径"},
        "content": {"type": "string", "description": "写入内容"},
        "encoding": {
            "type": "string",
            "description": "编码，默认 utf-8",
            "nullable": True,
        },
    }
    output_type = "string"

    def forward(self, path: str, content: str, encoding: str = "utf-8") -> str:  # type: ignore[override]
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding=encoding)
        return f"OK: 已写入 {file_path}"

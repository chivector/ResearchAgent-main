from __future__ import annotations

from pathlib import Path
import json


def read_text_file(path: str, encoding: str = "utf-8") -> str:
    """读取文本文件。"""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    return file_path.read_text(encoding=encoding)


def write_text_file(path: str, content: str, encoding: str = "utf-8") -> None:
    """写入文本文件（自动创建目录）。"""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding=encoding)


def read_jsonl_problem(path: str, index: int, encoding: str = "utf-8") -> str:
    """从 JSONL 中读取指定题号的 problem 字段（1-based）。"""
    if index <= 0:
        raise ValueError("题号必须为正整数（从 1 开始）。")
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    with file_path.open("r", encoding=encoding) as f:
        for i, line in enumerate(f, start=1):
            if i == index:
                data = json.loads(line)
                if "problem" not in data:
                    raise KeyError(f"第 {index} 行不存在 problem 字段。")
                return data["problem"]
    raise IndexError(f"题号超出范围: {index}")

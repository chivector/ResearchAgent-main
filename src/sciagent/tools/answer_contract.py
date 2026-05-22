from __future__ import annotations

import re
from typing import Dict, List

from smolagents import tool

SECTION_KEYWORDS = {
    "Problem restatement": ["problem restatement", "deliverables"],
    "Key context & assumptions / notation": ["context", "assumption", "notation"],
    "Hypotheses / model (mechanism)": ["hypothesis", "model", "mechanism"],
    "Method / protocol / computational strategy": ["method", "protocol", "computational", "simulation"],
    "Analysis plan & expected outcomes": ["analysis plan", "expected outcome", "metrics"],
    "Sanity checks, limitations, confounders": ["sanity", "limitation", "confounder"],
    "Downstream tasks / next experiments": ["downstream", "next experiment", "future work"],
}


def _missing_sections(draft: str, context_brief: Dict = None) -> List[str]:
    """
    检查草稿中缺失的章节。

    动态调整契约检查（修复与 Prompt 的逻辑冲突）
    - 如果是考试导向（存在明确的 subquestions），则不强制要求科研 7 段式
    - 只检查子问题标题是否存在，具体覆盖率交由 _missing_tasks 检查
    """
    lowered = draft.lower()

    # 【新增逻辑】：如果是考试导向（存在明确的 subquestions），则不强制要求科研 7 段式
    if context_brief and context_brief.get("subquestions"):
        # 只要草稿里有标题排版即可（## 或 #），具体覆盖率交由 _missing_tasks 检查
        if "## " not in draft and "# " not in draft:
            return ["Subquestion headings (missing ## or # markers)"]
        return []  # 考试题不检查科研 7 段式

    # 对于非考试题（科研论文式），检查 7 段式结构
    missing = []
    for section, keywords in SECTION_KEYWORDS.items():
        if not any(keyword in lowered for keyword in keywords):
            missing.append(section)
    return missing


def _missing_tasks(draft: str, task_graph: Dict) -> List[str]:
    lowered = draft.lower()
    missing = []
    for task in task_graph.get("tasks", []):
        title = str(task.get("title", "")).lower()
        task_type = str(task.get("task_type", "")).lower()
        if title and title not in lowered and task_type not in lowered:
            missing.append(task.get("id", "unknown"))
    return missing


def _check_numerical_deliverables(draft: str, context_brief: Dict) -> List[str]:
    """
    检查数值交付物是否完成（针对物理/数学题的严格数值契约）。

    触发条件：deliverables 中包含明确要求计算数值的关键词。
    检查逻辑：草稿中是否包含数字和常见物理单位的组合。
    """
    issues = []
    deliverables = context_brief.get("deliverables", [])

    # 触发词汇检测（英文 + 中文）
    value_triggers = [
        "value of",
        "calculate the",
        "compute the",
        "find the exact",
        "how much",
        "what is the numerical",
        "determine the value",
        "evaluate numerically",
        "求出",
        "计算",
        "数值",
        "具体值",
    ]

    for item in deliverables:
        item_lower = str(item).lower()
        if any(trigger in item_lower for trigger in value_triggers):
            # 检查草稿中是否包含数值结果
            # 匹配模式：数字 + 可选单位（支持科学计数法、负数、小数）
            # 例如: "= -17.8 MeV", "C = -0.05", "E = 1.23e-10 J", "k = 2π/a"
            numerical_pattern = r'[-+]?\d*\.?\d+([eE][-+]?\d+)?(\s*(MeV|eV|keV|GeV|J|erg|fm|nm|μm|mm|cm|m|kg|g|Hz|s|K|°C|rad|deg|Å|a\.u\.|hartree|C|N|Pa|atm|mol|M|L|V|A|Ω|T|Wb|H|F|W|cal|kcal))?'

            # 同时检查是否有明确的赋值语句（= 或 ≈）
            assignment_pattern = r'[=≈≃]\s*' + numerical_pattern

            if not re.search(assignment_pattern, draft):
                # 进一步检查：是否至少有数值出现（即使没有赋值符号）
                if not re.search(numerical_pattern, draft):
                    issues.append(f"Numerical result missing: Deliverable '{item}' requires a computed numerical value, "
                                  "but no clear numerical result was found in the draft. "
                                  "Expected format: 'X = [value] [unit]' or 'X ≈ [value] [unit]'.")
                else:
                    # 有数字但没有赋值语句，给出警告
                    issues.append(
                        f"Numerical result incomplete: Deliverable '{item}' requires a computed value. "
                        "Numbers were found in the draft, but no clear assignment statement (e.g., 'C = ...') was detected. "
                        "Please ensure the final numerical result is explicitly stated.")

    return issues


@tool
def answer_contract_check_tool(draft: str, task_graph: dict, context_brief: dict = None) -> dict:
    """
    Check the draft against the scientific AnswerContract.

    Args:
        draft: Draft text.
        task_graph: ResearchTaskGraph JSON.
        context_brief: ContextBrief JSON (optional, for numerical deliverable checks and exam-style detection).

    Returns:
        ContractReport JSON with pass flag and missing items.
    """
    missing_sections = _missing_sections(draft, context_brief)  # 传入 context_brief
    missing_tasks = _missing_tasks(draft, task_graph)
    issues = []

    if missing_sections:
        issues.append("Missing required sections.")
    if missing_tasks:
        issues.append("Missing task coverage.")

    # 数值交付物检查（如果提供了 context_brief）
    if context_brief:
        numerical_issues = _check_numerical_deliverables(draft, context_brief)
        issues.extend(numerical_issues)

    return {
        "passed": not missing_sections and not missing_tasks and (not context_brief or not numerical_issues),
        "missing_sections": missing_sections,
        "missing_tasks": missing_tasks,
        "issues": issues,
    }

from __future__ import annotations

import re

from smolagents import tool


PLACEHOLDER_PATTERNS = [
    r"\bTBD\b",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bto be determined\b",
]


@tool
def consistency_lint_tool(draft: str) -> list:
    """
    Check for basic consistency issues in the draft text.

    Args:
        draft: Draft text.

    Returns:
        A list of issue strings.
    """
    issues = []
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, draft, re.IGNORECASE):
            issues.append(f"Placeholder detected: {pattern}")

    if "##" not in draft:
        issues.append("No section headings detected; structure may be missing.")

    if "assumption" in draft.lower() and "define" not in draft.lower():
        issues.append("Assumptions mentioned without explicit definitions.")

    return issues

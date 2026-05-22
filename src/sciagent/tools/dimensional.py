from __future__ import annotations

from typing import Dict, List

from smolagents import tool


def _collect_symbols(expression: str) -> List[str]:
    tokens = []
    for token in expression.replace("(", " ").replace(")", " ").replace("*", " ").replace("/", " ").split():
        token = token.strip()
        if token.isidentifier():
            tokens.append(token)
    return tokens


@tool
def dimensional_check_tool(expressions: List[str], unit_map: Dict[str, str]) -> dict:
    """
    Perform a lightweight dimensional check on expressions.

    Args:
        expressions: List of expressions to check.
        unit_map: Mapping from variable name to unit string.

    Returns:
        A report with issues and suggestions.
    """
    issues = []
    for expr in expressions:
        symbols = _collect_symbols(expr)
        undefined = [s for s in symbols if s not in unit_map]
        if undefined:
            issues.append(
                {
                    "expression": expr,
                    "issue": "Undefined units for symbols",
                    "symbols": undefined,
                }
            )
    return {"issues": issues, "notes": ["Dimensional check is heuristic."]}

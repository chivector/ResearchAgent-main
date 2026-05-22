from __future__ import annotations

from smolagents import tool


GENERAL_MARKERS = [
    "arbitrary",
    "general",
    "for any",
    "for all",
    "general formula",
    "general expression",
    "|\\Psi_i",
    "|\\Psi_f",
    "\\Psi_i",
    "\\Psi_f",
]

EXAMPLE_MARKERS = [
    "ghz",
    "example",
    "special case",
    "specific state",
    "separable",
    "toy model",
]


@tool
def generality_guard_tool(draft: str) -> dict:
    """
    Check whether the draft prioritizes general derivations over examples.

    Args:
        draft: Draft text.

    Returns:
        GeneralityReport JSON.
    """
    lowered = draft.lower()
    general_count = sum(marker in lowered for marker in GENERAL_MARKERS)
    example_count = sum(marker in lowered for marker in EXAMPLE_MARKERS)
    ratio = general_count / max(1, example_count)
    issues = []
    if general_count == 0 and example_count > 0:
        issues.append("Only examples detected; general derivation likely missing.")
    if ratio < 0.5 and example_count > 0:
        issues.append("Example-heavy draft; general derivation appears underrepresented.")
    return {
        "general_markers": general_count,
        "example_markers": example_count,
        "ratio": ratio,
        "issues": issues,
    }

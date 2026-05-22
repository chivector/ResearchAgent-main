"""
Deterministic constraint validation for the ConstraintLedger.

Validates whether an agent's output satisfies the constraints extracted from
the problem text. Uses regex/keyword matching — zero LLM calls.

Modeled after answer_contract.py and _append_deterministic_exam_checks in runner.py.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List


def validate_constraints(
    output_text: str,
    constraint_ledger: Dict[str, Any],
    stage_name: str,
) -> Dict[str, Any]:
    """
    Deterministic validation of constraint satisfaction against an agent's output.

    Args:
        output_text: The text output to validate against.
        constraint_ledger: ConstraintLedger dict with ``constraints`` list.
        stage_name: Pipeline stage name (e.g., "task_execution", "post_writer").

    Returns:
        Updated constraint_ledger dict with status fields changed.
    """
    if not isinstance(constraint_ledger, dict):
        return constraint_ledger or {"constraints": [], "last_validated_at": ""}

    ledger = deepcopy(constraint_ledger)
    text = (output_text or "")
    text_lower = " ".join(text.split()).lower()

    for entry in ledger.get("constraints", []):
        if not isinstance(entry, dict):
            continue

        status = entry.get("status", "pending")
        if status in ("satisfied", "deferred"):
            continue

        strategy = entry.get("verification_strategy", "keyword_presence")

        if strategy == "keyword_presence":
            entry["status"] = _check_keyword_presence(text_lower, entry)
        elif strategy == "section_presence":
            entry["status"] = _check_section_presence(text, text_lower, entry)
        elif strategy == "count_check":
            entry["status"] = _check_count(text_lower, entry)
        elif strategy == "llm_required":
            entry["status"] = "deferred"

        if entry["status"] == "satisfied" and stage_name not in entry.get("satisfied_by", []):
            entry.setdefault("satisfied_by", []).append(stage_name)

    ledger["last_validated_at"] = stage_name
    return ledger


def get_violations(constraint_ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return list of constraints that are violated or still pending."""
    if not isinstance(constraint_ledger, dict):
        return []
    return [
        c for c in constraint_ledger.get("constraints", [])
        if isinstance(c, dict) and c.get("status") in ("pending", "violated")
    ]


# ---------------------------------------------------------------------------
# Verification strategy implementations
# ---------------------------------------------------------------------------

def _check_keyword_presence(text_lower: str, entry: Dict[str, Any]) -> str:
    """
    Check if ALL keywords appear in the text (case-insensitive substring match).

    If no keywords are specified, the constraint cannot be verified deterministically
    and is left as pending.
    """
    keywords = entry.get("keywords") or []
    if not keywords:
        return entry.get("status", "pending")

    for kw in keywords:
        kw_lower = kw.strip().lower()
        if not kw_lower:
            continue
        if kw_lower not in text_lower:
            return "violated"

    return "satisfied"


def _check_section_presence(text: str, text_lower: str, entry: Dict[str, Any]) -> str:
    """
    Check for structural markers indicating that the constraint is addressed:
    - Numbered steps (1., 2., 3., ...)
    - Section headings (## Step, ### Derivation, etc.)
    - Step/derivation keywords in context

    For "show all steps" / "step by step" type constraints.
    """
    # Check for numbered steps pattern (at least 2 steps)
    numbered_steps = re.findall(r'(?:^|\n)\s*(?:\d+[\.\)]\s|Step\s+\d)', text)
    if len(numbered_steps) >= 2:
        return "satisfied"

    # Check for section headings with step/derivation keywords
    headings = re.findall(r'(?:^|\n)\s*#{1,4}\s+.+', text)
    step_headings = [h for h in headings if any(
        kw in h.lower() for kw in ["step", "derivation", "intermediate", "stage", "phase"]
    )]
    if len(step_headings) >= 2:
        return "satisfied"

    # Check keywords from the constraint entry
    keywords = entry.get("keywords") or []
    if keywords:
        matched = sum(1 for kw in keywords if kw.strip().lower() in text_lower)
        if matched >= len(keywords):
            return "satisfied"

    # Check for explicit step enumeration markers
    if re.search(r'(?:step\s+\d|stage\s+\d|first,.*second,|firstly.*secondly)', text_lower):
        return "satisfied"

    return "violated"


def _check_count(text_lower: str, entry: Dict[str, Any]) -> str:
    """
    For 'how many X' type constraints, check if the output contains
    numerical values associated with the keywords.
    """
    keywords = entry.get("keywords") or []
    if not keywords:
        return entry.get("status", "pending")

    for kw in keywords:
        kw_lower = kw.strip().lower()
        if not kw_lower:
            continue
        if kw_lower not in text_lower:
            return "violated"

        # Check if there's a number near the keyword (within ~100 chars)
        pattern = (
            rf'(?:{re.escape(kw_lower)}.{{0,100}}\d+'
            rf'|\d+.{{0,100}}{re.escape(kw_lower)})'
        )
        if not re.search(pattern, text_lower):
            return "violated"

    return "satisfied"

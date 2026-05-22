from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROBLEM_IDS = [1, 2, 6, 8, 10, 13, 16]


STOPWORDS = {
    "about",
    "above",
    "after",
    "against",
    "also",
    "because",
    "before",
    "between",
    "could",
    "derive",
    "describe",
    "given",
    "include",
    "including",
    "problem",
    "question",
    "should",
    "state",
    "states",
    "their",
    "there",
    "these",
    "those",
    "through",
    "using",
    "where",
    "which",
    "while",
    "would",
}

MATH_REPLACEMENTS = {
    "≈": "approx",
    "≃": "approx",
    "≤": "<=",
    "≥": ">=",
    "−": "-",
    "–": "-",
    "—": "-",
    "η": "eta",
    "ψ": "psi",
    "Ψ": "psi",
    "φ": "phi",
    "Φ": "phi",
    "σ": "sigma",
    "Σ": "sigma",
    "τ": "tau",
    "λ": "lambda",
    "Λ": "lambda",
    "π": "pi",
    "θ": "theta",
    "μ": "mu",
    "∞": "infty",
}

LATEX_COMMAND_REPLACEMENTS = {
    r"\approx": "approx",
    r"\simeq": "approx",
    r"\sim": "approx",
    r"\eta": "eta",
    r"\psi": "psi",
    r"\Psi": "psi",
    r"\phi": "phi",
    r"\Phi": "phi",
    r"\sigma": "sigma",
    r"\Sigma": "sigma",
    r"\tau": "tau",
    r"\lambda": "lambda",
    r"\Lambda": "lambda",
    r"\pi": "pi",
    r"\theta": "theta",
    r"\mu": "mu",
    r"\infty": "infty",
    r"\leq": "<=",
    r"\geq": ">=",
    r"\times": "*",
    r"\cdot": "*",
    r"\left": "",
    r"\right": "",
}


def parse_problem_ids(value: str) -> List[int]:
    ids: List[int] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start <= 0 or end < start:
                raise ValueError(f"Invalid problem id range: {chunk}")
            ids.extend(range(start, end + 1))
        else:
            problem_id = int(chunk)
            if problem_id <= 0:
                raise ValueError(f"Problem ids are 1-based positive integers: {problem_id}")
            ids.append(problem_id)
    seen = set()
    deduped = []
    for problem_id in ids:
        if problem_id not in seen:
            seen.add(problem_id)
            deduped.append(problem_id)
    return deduped


def normalize_formula_text(text: str) -> str:
    value = str(text or "")
    for old, new in MATH_REPLACEMENTS.items():
        value = value.replace(old, new)
    for old, new in LATEX_COMMAND_REPLACEMENTS.items():
        value = value.replace(old, new)
    value = re.sub(r"\\(?:mathrm|text|operatorname)\{([^{}]*)\}", r"\1", value)
    value = value.replace("\\(", "").replace("\\)", "")
    value = value.replace("\\[", "").replace("\\]", "")
    value = value.replace("$", "")
    value = value.replace("\\", "")
    value = value.replace("{", "").replace("}", "")
    value = value.lower()
    value = re.sub(r"\s+", "", value)
    return value


def _normalize_plain_text(text: str) -> str:
    value = str(text or "").lower()
    for old, new in MATH_REPLACEMENTS.items():
        value = value.replace(old, new)
    value = re.sub(r"[^a-z0-9_+\-*/=<>'.()]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_formula_items(text: str, max_items: int = 16) -> List[str]:
    source = str(text or "")
    candidates: List[str] = []
    patterns = [
        r"\$\$(.*?)\$\$",
        r"\$(.*?)\$",
        r"\\\((.*?)\\\)",
        r"\\\[(.*?)\\\]",
    ]
    for pattern in patterns:
        candidates.extend(match.group(1).strip() for match in re.finditer(pattern, source, flags=re.DOTALL))

    math_markers = ("=", "\\frac", "\\sum", "\\prod", "\\int", "\\approx", "^", "_", "≈", "<=", ">=")
    for line in source.splitlines():
        stripped = line.strip()
        if "$" in stripped or "\\(" in stripped or "\\[" in stripped:
            continue
        if any(marker in stripped for marker in math_markers):
            candidates.append(stripped)

    items: List[str] = []
    seen = set()
    for candidate in candidates:
        compact = " ".join(candidate.split())
        norm = normalize_formula_text(compact)
        if len(norm) < 4:
            continue
        if not any(marker in candidate for marker in math_markers) and not re.search(r"[a-zA-Z]\([^)]*\)", candidate):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        items.append(compact)
        if len(items) >= max_items:
            break
    return items


def extract_keyword_items(text: str, max_items: int = 14) -> List[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9'_-]{4,}", str(text or "").lower())
    counter = Counter(token for token in tokens if token not in STOPWORDS and not token.isdigit())
    return [token for token, _ in counter.most_common(max_items)]


def _coverage(answer_text: str, items: Iterable[str], math_mode: bool) -> Dict[str, Any]:
    item_list = list(items)
    if math_mode:
        haystack = normalize_formula_text(answer_text)
        rows = [{"item": item, "present": normalize_formula_text(item) in haystack} for item in item_list]
    else:
        haystack = _normalize_plain_text(answer_text)
        rows = [{"item": item, "present": re.search(rf"\b{re.escape(item.lower())}\b", haystack) is not None} for item in item_list]
    hits = sum(1 for row in rows if row["present"])
    return {
        "hit_count": hits,
        "item_count": len(rows),
        "coverage": (hits / len(rows)) if rows else None,
        "items": rows,
    }


def rubric_proxy(problem_text: str, reference_text: str, answer_text: str) -> Dict[str, Any]:
    groups = {
        "problem_formula_coverage": _coverage(answer_text, extract_formula_items(problem_text, max_items=10), True),
        "reference_formula_coverage": _coverage(answer_text, extract_formula_items(reference_text, max_items=16), True),
        "rubric_keyword_coverage": _coverage(answer_text, extract_keyword_items(reference_text, max_items=14), False),
    }
    coverages = [group["coverage"] for group in groups.values() if group["coverage"] is not None]
    return {
        "coverage": sum(coverages) / len(coverages) if coverages else None,
        "groups": groups,
    }


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _read_dataset_records(path: Path) -> Dict[int, Dict[str, Any]]:
    if not path.exists():
        return {}
    records: Dict[int, Dict[str, Any]] = {}
    with path.open(encoding="utf-8", errors="replace") as fp:
        for idx, line in enumerate(fp, start=1):
            try:
                records[idx] = json.loads(line)
            except Exception:
                records[idx] = {}
    return records


def _case_paths(output_dir: Path, problem_id: int) -> Dict[str, Path]:
    case_dir = output_dir / "cases" / f"problem_{problem_id:03d}"
    return {
        "case_dir": case_dir,
        "answer": case_dir / "answer.md",
        "payload": case_dir / "payload_report.json",
        "judge": case_dir / "judge" / "judge_result.json",
    }


def _summarize_views(views: List[Dict[str, Any]]) -> Dict[str, Any]:
    rendered = sum(int(view.get("rendered_token_cost", view.get("token_cost", 0)) or 0) for view in views)
    legacy = sum(int(view.get("legacy_token_cost", 0) or 0) for view in views)
    savings = legacy - rendered if legacy else None
    by_role: Dict[str, Dict[str, Any]] = {}
    for view in views:
        role = str(view.get("role") or "unknown")
        bucket = by_role.setdefault(
            role,
            {
                "count": 0,
                "rendered_token_cost": 0,
                "legacy_token_cost": 0,
                "verified": 0,
                "fail_soft": 0,
            },
        )
        bucket["count"] += 1
        bucket["rendered_token_cost"] += int(view.get("rendered_token_cost", view.get("token_cost", 0)) or 0)
        bucket["legacy_token_cost"] += int(view.get("legacy_token_cost", 0) or 0)
        bucket["verified"] += int(bool(view.get("payload_verified")))
        bucket["fail_soft"] += int(not bool(view.get("payload_verified")))
    return {
        "payload_view_count": len(views),
        "verified_count": sum(1 for view in views if view.get("payload_verified")),
        "fail_soft_count": sum(1 for view in views if not view.get("payload_verified")),
        "total_rendered_token_cost": rendered,
        "total_legacy_token_cost": legacy or None,
        "total_token_savings_vs_legacy": savings,
        "total_token_savings_ratio_vs_legacy": (savings / legacy) if legacy else None,
        "by_role": by_role,
    }


def _role_rows(label: str, report: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not report:
        return []
    summary = report.get("summary") or _summarize_views(list(report.get("payload_views") or []))
    by_role = summary.get("by_role") or {}
    rows = []
    for role, item in sorted(by_role.items()):
        rendered = int(item.get("rendered_token_cost", item.get("rendered", 0)) or 0)
        legacy = int(item.get("legacy_token_cost", item.get("legacy", 0)) or 0)
        savings = legacy - rendered if legacy else None
        rows.append(
            {
                "case_label": label,
                "role": role,
                "count": int(item.get("count", 0) or 0),
                "rendered_tokens": rendered,
                "legacy_tokens": legacy,
                "token_savings": savings,
                "token_savings_ratio": (savings / legacy) if legacy and savings is not None else None,
                "verified": int(item.get("verified", 0) or 0),
                "fail_soft": int(item.get("fail_soft", 0) or 0),
            }
        )
    return rows


def _candidate_counts(views: List[Dict[str, Any]]) -> Dict[str, int]:
    return dict(Counter(str(view.get("candidate_name") or "unknown") for view in views))


def _status(answer_path: Path, payload_path: Path, judge_path: Path) -> str:
    missing = []
    if not answer_path.exists():
        missing.append("answer")
    if not payload_path.exists():
        missing.append("payload")
    if not judge_path.exists():
        missing.append("judge")
    return "complete" if not missing else "missing_" + "_".join(missing)


def _case_row(
    label: str,
    problem_id: int,
    answer_path: Path,
    payload_path: Path,
    judge_path: Path,
    record: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    report = _load_json(payload_path)
    judge = _load_json(judge_path)
    answer_text = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.exists() else ""
    views = list((report or {}).get("payload_views") or [])
    summary = (report or {}).get("summary") or _summarize_views(views)
    reference_text = str(record.get("answer") or record.get("rubric") or "")
    problem_text = str(record.get("problem") or "")
    coverage = rubric_proxy(problem_text, reference_text, answer_text)

    rendered = summary.get("total_rendered_token_cost")
    legacy = summary.get("total_legacy_token_cost")
    savings = summary.get("total_token_savings_vs_legacy")
    ratio = summary.get("total_token_savings_ratio_vs_legacy")
    if ratio is not None:
        ratio = float(ratio)

    group_values = coverage["groups"]
    row = {
        "case_label": label,
        "problem_id": problem_id,
        "status": _status(answer_path, payload_path, judge_path),
        "payload_view_count": int(summary.get("payload_view_count", len(views)) or 0),
        "verified_count": int(summary.get("verified_count", 0) or 0),
        "fail_soft_count": int(summary.get("fail_soft_count", 0) or 0),
        "rendered_tokens": int(rendered or 0),
        "legacy_tokens": int(legacy or 0),
        "token_savings": int(savings or 0) if savings is not None else None,
        "token_savings_ratio": ratio,
        "judge_score": float(judge.get("overall_score_0_to_10")) if judge and judge.get("overall_score_0_to_10") is not None else None,
        "judge_verdict": str(judge.get("verdict", "")) if judge else "",
        "judge_confidence": float(judge.get("confidence_0_to_1")) if judge and judge.get("confidence_0_to_1") is not None else None,
        "repair_rounds": sum(int(view.get("repair_rounds", 0) or 0) for view in views),
        "candidate_counts": _candidate_counts(views),
        "answer_est_tokens": math.ceil(len(answer_text) / 4) if answer_text else 0,
        "coverage": coverage,
        "overall_rubric_proxy_coverage": coverage["coverage"],
        "problem_formula_coverage": group_values["problem_formula_coverage"]["coverage"],
        "reference_formula_coverage": group_values["reference_formula_coverage"]["coverage"],
        "rubric_keyword_coverage": group_values["rubric_keyword_coverage"]["coverage"],
    }
    return row, _role_rows(label, report)


def _discover_problem_ids(output_dir: Path) -> List[int]:
    case_root = output_dir / "cases"
    if not case_root.exists():
        return []
    ids = []
    for path in case_root.iterdir():
        match = re.fullmatch(r"problem_(\d+)", path.name)
        if match:
            ids.append(int(match.group(1)))
    return sorted(ids)


def load_midterm_results(
    output_dir: Path,
    dataset_file: Path,
    problem_ids: Optional[List[int]] = None,
    include_anchor: bool = True,
    anchor_payload: Path = ROOT / "outputs" / "real_q1_current2_payload_report.json",
    anchor_judge: Path = ROOT / "outputs" / "llm_judge" / "real_q1_current2" / "judge_result.json",
    anchor_answer: Path = ROOT / "outputs" / "real_q1_current2_output.md",
) -> Dict[str, Any]:
    records = _read_dataset_records(dataset_file)
    ids = problem_ids if problem_ids is not None else _discover_problem_ids(output_dir)
    rows: List[Dict[str, Any]] = []
    role_rows: List[Dict[str, Any]] = []

    if include_anchor and (anchor_payload.exists() or anchor_answer.exists() or anchor_judge.exists()):
        row, roles = _case_row(
            label="anchor_real_q1_hq",
            problem_id=1,
            answer_path=anchor_answer,
            payload_path=anchor_payload,
            judge_path=anchor_judge,
            record=records.get(1, {}),
        )
        rows.append(row)
        role_rows.extend(roles)

    for problem_id in ids:
        paths = _case_paths(output_dir, problem_id)
        row, roles = _case_row(
            label=f"batch_p{problem_id:03d}",
            problem_id=problem_id,
            answer_path=paths["answer"],
            payload_path=paths["payload"],
            judge_path=paths["judge"],
            record=records.get(problem_id, {}),
        )
        rows.append(row)
        role_rows.extend(roles)

    return {"rows": rows, "role_rows": role_rows}


def _as_csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _write_metrics_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "case_label",
        "problem_id",
        "status",
        "payload_view_count",
        "verified_count",
        "fail_soft_count",
        "rendered_tokens",
        "legacy_tokens",
        "token_savings",
        "token_savings_ratio",
        "judge_score",
        "judge_verdict",
        "judge_confidence",
        "repair_rounds",
        "answer_est_tokens",
        "overall_rubric_proxy_coverage",
        "problem_formula_coverage",
        "reference_formula_coverage",
        "rubric_keyword_coverage",
        "candidate_counts",
    ]
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _as_csv_value(row.get(field)) for field in fieldnames})


def _write_role_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "case_label",
        "role",
        "count",
        "rendered_tokens",
        "legacy_tokens",
        "token_savings",
        "token_savings_ratio",
        "verified",
        "fail_soft",
    ]
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _as_csv_value(row.get(field)) for field in fieldnames})


def _label(label: str) -> str:
    if label == "anchor_real_q1_hq":
        return "Anchor\nQ1 HQ"
    return label.replace("batch_", "").replace("_", "\n").upper()


def _save_empty_chart(path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    ax.axis("off")
    ax.text(0.5, 0.5, "No data available", ha="center", va="center", fontsize=13)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_token_savings_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    data = [row for row in rows if row.get("legacy_tokens") and row.get("rendered_tokens")]
    if not data:
        _save_empty_chart(path, "Token Savings by Case")
        return
    labels = [_label(row["case_label"]) for row in data]
    legacy = [row["legacy_tokens"] / 1000 for row in data]
    rendered = [row["rendered_tokens"] / 1000 for row in data]
    x = list(range(len(data)))
    width = 0.36

    fig, ax = plt.subplots(figsize=(12.0, 5.2))
    ax.bar([idx - width / 2 for idx in x], legacy, width, label="Legacy", color="#9aa6b2")
    ax.bar([idx + width / 2 for idx in x], rendered, width, label="PayloadView", color="#2f6f9f")
    for idx, row in enumerate(data):
        ratio = row.get("token_savings_ratio")
        if ratio is not None:
            ax.text(idx, max(legacy[idx], rendered[idx]) * 1.04, f"-{ratio:.0%}", ha="center", fontsize=9)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Estimated tokens (thousands)")
    ax.set_title("Token Savings by Case")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_quality_savings_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    data = [row for row in rows if row.get("judge_score") is not None and row.get("token_savings_ratio") is not None]
    if not data:
        _save_empty_chart(path, "Judge Score vs Token Savings")
        return
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    for row in data:
        x = row["token_savings_ratio"] * 100
        y = row["judge_score"]
        size = 55 + row.get("payload_view_count", 0) * 10
        color = "#3f8f70" if row.get("status") == "complete" else "#ba7a2f"
        ax.scatter(x, y, s=size, color=color, alpha=0.82, edgecolor="white", linewidth=0.8)
        ax.text(x + 0.6, y + 0.03, row["case_label"].replace("batch_", ""), fontsize=8)
    ax.set_xlim(0, max(100, max(row["token_savings_ratio"] * 100 for row in data) + 8))
    ax.set_ylim(0, 10)
    ax.set_xlabel("Token savings vs legacy (%)")
    ax.set_ylabel("LLM-as-judge score / 10")
    ax.set_title("Quality Signal vs Compression")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_role_savings_chart(path: Path, role_rows: List[Dict[str, Any]]) -> None:
    if not role_rows:
        _save_empty_chart(path, "Role-Level Token Savings")
        return
    aggregate: Dict[str, Dict[str, int]] = defaultdict(lambda: {"rendered": 0, "legacy": 0})
    for row in role_rows:
        aggregate[row["role"]]["rendered"] += int(row.get("rendered_tokens") or 0)
        aggregate[row["role"]]["legacy"] += int(row.get("legacy_tokens") or 0)
    roles = sorted(aggregate)
    legacy = [aggregate[role]["legacy"] / 1000 for role in roles]
    rendered = [aggregate[role]["rendered"] / 1000 for role in roles]
    x = list(range(len(roles)))
    width = 0.36

    fig, ax = plt.subplots(figsize=(9.8, 5.0))
    ax.bar([idx - width / 2 for idx in x], legacy, width, label="Legacy", color="#9aa6b2")
    ax.bar([idx + width / 2 for idx in x], rendered, width, label="PayloadView", color="#3f8f70")
    for idx, role in enumerate(roles):
        leg = aggregate[role]["legacy"]
        ren = aggregate[role]["rendered"]
        if leg:
            ax.text(idx, max(legacy[idx], rendered[idx]) * 1.04, f"-{(leg - ren) / leg:.0%}", ha="center", fontsize=9)
    ax.set_xticks(x, roles, rotation=18, ha="right")
    ax.set_ylabel("Estimated tokens (thousands)")
    ax.set_title("Role-Level Token Savings")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_payload_health_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        _save_empty_chart(path, "Payload Verifier Health")
        return
    labels = [_label(row["case_label"]) for row in rows]
    verified = [row.get("verified_count", 0) for row in rows]
    fail_soft = [row.get("fail_soft_count", 0) for row in rows]
    x = list(range(len(rows)))

    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.6))
    axes[0].bar(x, verified, label="Verified", color="#3f8f70")
    axes[0].bar(x, fail_soft, bottom=verified, label="Fail-soft", color="#d35f5f")
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("PayloadView count")
    axes[0].set_title("Verifier Outcome by Case")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.25)

    status_counts = Counter(row.get("status", "unknown") for row in rows)
    axes[1].bar(list(status_counts), list(status_counts.values()), color="#6d70b8")
    axes[1].set_title("Artifact Completeness")
    axes[1].set_ylabel("Case count")
    axes[1].tick_params(axis="x", rotation=20)
    axes[1].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_candidate_repair_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        _save_empty_chart(path, "Candidate and Repair Distribution")
        return
    candidate_counts: Counter[str] = Counter()
    for row in rows:
        candidate_counts.update(row.get("candidate_counts") or {})
    labels = [_label(row["case_label"]) for row in rows]
    repairs = [row.get("repair_rounds", 0) for row in rows]

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
    if candidate_counts:
        axes[0].bar(list(candidate_counts), list(candidate_counts.values()), color="#2f6f9f")
    else:
        axes[0].text(0.5, 0.5, "No candidate data", ha="center", va="center", transform=axes[0].transAxes)
    axes[0].set_title("Selected Candidate Types")
    axes[0].set_ylabel("Count")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(labels, repairs, color="#8d4d9d")
    axes[1].set_title("Verifier Repair Rounds")
    axes[1].set_ylabel("Total rounds")
    axes[1].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_coverage_heatmap(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        _save_empty_chart(path, "Formula and Rubric Coverage")
        return
    columns = ["problem_formula_coverage", "reference_formula_coverage", "rubric_keyword_coverage"]
    labels = ["Problem formulas", "Reference formulas", "Rubric keywords"]
    matrix = []
    annotations = []
    for row in rows:
        values = []
        notes = []
        for column in columns:
            value = row.get(column)
            values.append(float(value) if value is not None else 0.0)
            notes.append("n/a" if value is None else f"{value:.0%}")
        matrix.append(values)
        annotations.append(notes)

    fig, ax = plt.subplots(figsize=(8.8, max(3.8, 0.45 * len(rows) + 1.8)))
    image = ax.imshow(matrix, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(columns)), labels, rotation=20, ha="right")
    ax.set_yticks(range(len(rows)), [_label(row["case_label"]).replace("\n", " ") for row in rows])
    ax.set_title("Formula and Rubric Coverage Proxy")
    for y, row_notes in enumerate(annotations):
        for x, text in enumerate(row_notes):
            ax.text(x, y, text, ha="center", va="center", color="#102027", fontsize=9)
    fig.colorbar(image, ax=ax, fraction=0.03, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows],
        ]
    )


def _fmt_percent(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.1%}"


def _fmt_num(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _write_report(path: Path, rows: List[Dict[str, Any]], role_rows: List[Dict[str, Any]], charts: List[Path]) -> None:
    complete = [row for row in rows if row.get("status") == "complete"]
    scored = [row for row in rows if row.get("judge_score") is not None]
    with_savings = [row for row in rows if row.get("token_savings_ratio") is not None]
    verifier_total = sum(row.get("payload_view_count", 0) for row in rows)
    verifier_passed = sum(row.get("verified_count", 0) for row in rows)
    avg_savings = sum(row["token_savings_ratio"] for row in with_savings) / len(with_savings) if with_savings else None
    avg_score = sum(row["judge_score"] for row in scored) / len(scored) if scored else None

    case_rows = [
        [
            row["case_label"],
            row["status"],
            row["payload_view_count"],
            row["verified_count"],
            row["fail_soft_count"],
            row["rendered_tokens"],
            row["legacy_tokens"],
            _fmt_percent(row.get("token_savings_ratio")),
            _fmt_num(row.get("judge_score")),
            row["repair_rounds"],
            _fmt_percent(row.get("overall_rubric_proxy_coverage")),
        ]
        for row in rows
    ]

    role_summary: Dict[str, Dict[str, int]] = defaultdict(lambda: {"rendered": 0, "legacy": 0, "count": 0})
    for row in role_rows:
        role_summary[row["role"]]["rendered"] += int(row.get("rendered_tokens") or 0)
        role_summary[row["role"]]["legacy"] += int(row.get("legacy_tokens") or 0)
        role_summary[row["role"]]["count"] += int(row.get("count") or 0)
    role_table = []
    for role, item in sorted(role_summary.items()):
        ratio = (item["legacy"] - item["rendered"]) / item["legacy"] if item["legacy"] else None
        role_table.append([role, item["count"], item["rendered"], item["legacy"], _fmt_percent(ratio)])
    complete_word = "case" if len(complete) == 1 else "cases"

    lines = [
        "# Midterm PayloadView Showcase Report",
        "",
        "## Main Finding",
        "",
        (
            f"This showcase contains {len(rows)} analyzed cases, {len(complete)} complete {complete_word}, "
            f"average token savings {_fmt_percent(avg_savings)}, and average LLM-as-judge score {_fmt_num(avg_score)}."
        ),
        (
            f"Payload verifier pass rate is {verifier_passed}/{verifier_total} views "
            f"({_fmt_percent(verifier_passed / verifier_total if verifier_total else None)})."
        ),
        "",
        "## Charts",
        "",
    ]
    for chart in charts:
        lines.append(f"- [{chart.name}]({chart.name})")
    lines.extend(
        [
            "",
            "## Case Metrics",
            "",
            _markdown_table(
                [
                    "Case",
                    "Status",
                    "Views",
                    "Verified",
                    "Fail-soft",
                    "Rendered",
                    "Legacy",
                    "Savings %",
                    "Judge",
                    "Repairs",
                    "Coverage proxy",
                ],
                case_rows,
            ),
            "",
            "## Role-Level Savings",
            "",
            _markdown_table(["Role", "Calls", "Rendered", "Legacy", "Savings %"], role_table),
            "",
            "## Interpretation",
            "",
            "- Compression value is shown by comparing compiled PayloadView tokens against legacy full-dossier-style payloads.",
            "- Quality is tracked separately with LLM-as-judge scores and deterministic formula/rubric coverage proxies.",
            "- Verifier health and repair rounds show whether minimal payloads required graph-based repair before being sent to agents.",
            "- Missing judge or payload artifacts are kept in the table instead of being hidden, so the report can be used while a batch is still running.",
            "",
            "## Limitations and Next Step",
            "",
            "- LLM-as-judge is an external quality signal, not a formal proof of correctness.",
            "- Formula/rubric coverage is a deterministic proxy and should be read as a risk detector.",
            "- The next implementation target is formula-level obligation extraction so key equations become explicit payload verifier requirements.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze midterm PayloadView batch artifacts.")
    parser.add_argument("--dataset-file", default="test.jsonl")
    parser.add_argument("--input-dir", default="outputs/midterm_showcase")
    parser.add_argument("--output-dir", default="outputs/midterm_showcase")
    parser.add_argument("--problem-ids", default=",".join(str(item) for item in DEFAULT_PROBLEM_IDS))
    parser.add_argument("--discover-cases", action="store_true", help="Analyze all cases found under input-dir/cases.")
    parser.add_argument("--no-anchor", action="store_true")
    parser.add_argument("--anchor-payload", default="outputs/real_q1_current2_payload_report.json")
    parser.add_argument("--anchor-judge", default="outputs/llm_judge/real_q1_current2/judge_result.json")
    parser.add_argument("--anchor-answer", default="outputs/real_q1_current2_output.md")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_file = Path(args.dataset_file)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    anchor_payload = Path(args.anchor_payload)
    anchor_judge = Path(args.anchor_judge)
    anchor_answer = Path(args.anchor_answer)
    if not dataset_file.is_absolute():
        dataset_file = ROOT / dataset_file
    if not input_dir.is_absolute():
        input_dir = ROOT / input_dir
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    if not anchor_payload.is_absolute():
        anchor_payload = ROOT / anchor_payload
    if not anchor_judge.is_absolute():
        anchor_judge = ROOT / anchor_judge
    if not anchor_answer.is_absolute():
        anchor_answer = ROOT / anchor_answer

    problem_ids = None if args.discover_cases else parse_problem_ids(args.problem_ids)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = load_midterm_results(
        output_dir=input_dir,
        dataset_file=dataset_file,
        problem_ids=problem_ids,
        include_anchor=not bool(args.no_anchor),
        anchor_payload=anchor_payload,
        anchor_judge=anchor_judge,
        anchor_answer=anchor_answer,
    )
    rows = result["rows"]
    role_rows = result["role_rows"]

    metrics_csv = output_dir / "metrics.csv"
    role_csv = output_dir / "role_metrics.csv"
    results_json = output_dir / "results.json"
    report_md = output_dir / "midterm_report.md"
    charts = [
        output_dir / "01_token_savings_by_case.png",
        output_dir / "02_judge_score_vs_savings.png",
        output_dir / "03_role_level_savings.png",
        output_dir / "04_payload_verifier_health.png",
        output_dir / "05_candidate_repair_distribution.png",
        output_dir / "06_formula_rubric_coverage.png",
    ]

    _write_metrics_csv(metrics_csv, rows)
    _write_role_csv(role_csv, role_rows)
    results_json.write_text(json.dumps({"rows": rows, "role_rows": role_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    _save_token_savings_chart(charts[0], rows)
    _save_quality_savings_chart(charts[1], rows)
    _save_role_savings_chart(charts[2], role_rows)
    _save_payload_health_chart(charts[3], rows)
    _save_candidate_repair_chart(charts[4], rows)
    _save_coverage_heatmap(charts[5], rows)
    _write_report(report_md, rows, role_rows, charts)

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "metrics_csv": str(metrics_csv),
                "role_csv": str(role_csv),
                "results_json": str(results_json),
                "report": str(report_md),
                "charts": [str(chart) for chart in charts],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

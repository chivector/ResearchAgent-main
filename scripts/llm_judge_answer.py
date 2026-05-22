from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

from openai import OpenAI


def _load_jsonl_record(path: Path, problem_id: int) -> Dict[str, Any]:
    if problem_id < 1:
        raise ValueError("--problem-id is 1-based.")
    with path.open(encoding="utf-8") as fp:
        for idx, line in enumerate(fp, start=1):
            if idx == problem_id:
                return json.loads(line)
    raise IndexError(f"Problem id {problem_id} not found in {path}.")


def _extract_json(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _judge_prompt(problem: str, reference_rubric: str, answer: str) -> list[Dict[str, str]]:
    system = (
        "You are a strict scientific exam judge. Grade the candidate answer only against the given problem "
        "and reference rubric. Do not reward verbosity unless it contains correct required derivations. "
        "Penalize missing formulas, wrong notation, unsupported claims, and failure to answer requested parts. "
        "Return valid JSON only."
    )
    user = f"""
Evaluate the candidate answer for the problem below.

Use the REFERENCE_RUBRIC as the grading guide. It may include point allocations and expected formulas. 
You should infer a 0-10 score from the rubric, not necessarily exactly sum all points if the rubric is noisy.

Return JSON with this schema:
{{
  "overall_score_0_to_10": number,
  "verdict": "excellent" | "good" | "partial" | "poor",
  "confidence_0_to_1": number,
  "requested_part_scores": [
    {{
      "part": "part label",
      "score_0_to_1": number,
      "assessment": "short assessment",
      "missing_or_wrong": ["specific missing/wrong items"]
    }}
  ],
  "rubric_coverage": {{
    "background_protocol": number,
    "entanglement_efficiency": number,
    "fixed_postselection_alternative": number,
    "fisher_information": number,
    "conclusion": number
  }},
  "major_strengths": ["..."],
  "major_omissions": ["..."],
  "mathematical_errors_or_risks": ["..."],
  "hallucination_or_irrelevance_risks": ["..."],
  "token_payload_quality_note": "one sentence about whether the answer appears to have enough task-relevant material",
  "recommended_next_payload_improvement": "one concrete payload/compiler improvement"
}}

PROBLEM:
{problem}

REFERENCE_RUBRIC:
{reference_rubric}

CANDIDATE_ANSWER:
{answer}
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _write_markdown(path: Path, judgment: Dict[str, Any]) -> None:
    lines = [
        "# LLM-as-Judge Report",
        "",
        f"- overall_score_0_to_10: {judgment.get('overall_score_0_to_10')}",
        f"- verdict: {judgment.get('verdict')}",
        f"- confidence_0_to_1: {judgment.get('confidence_0_to_1')}",
        "",
        "## Requested Parts",
        "",
        "| Part | Score | Assessment | Missing/Wrong |",
        "| --- | ---: | --- | --- |",
    ]
    for item in judgment.get("requested_part_scores") or []:
        lines.append(
            "| {part} | {score} | {assessment} | {missing} |".format(
                part=str(item.get("part", "")).replace("|", "\\|"),
                score=item.get("score_0_to_1", ""),
                assessment=str(item.get("assessment", "")).replace("|", "\\|"),
                missing="; ".join(str(x) for x in item.get("missing_or_wrong") or []).replace("|", "\\|"),
            )
        )
    lines.extend(["", "## Rubric Coverage", ""])
    for key, value in (judgment.get("rubric_coverage") or {}).items():
        lines.append(f"- {key}: {value}")
    for title, key in (
        ("Major Strengths", "major_strengths"),
        ("Major Omissions", "major_omissions"),
        ("Mathematical Errors Or Risks", "mathematical_errors_or_risks"),
        ("Hallucination Or Irrelevance Risks", "hallucination_or_irrelevance_risks"),
    ):
        lines.extend(["", f"## {title}", ""])
        for value in judgment.get(key) or []:
            lines.append(f"- {value}")
    lines.extend([
        "",
        "## Payload Note",
        "",
        str(judgment.get("token_payload_quality_note", "")),
        "",
        "## Recommended Payload Improvement",
        "",
        str(judgment.get("recommended_next_payload_improvement", "")),
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Judge a final answer with an OpenAI-compatible LLM.")
    parser.add_argument("--dataset-file", default="test.jsonl")
    parser.add_argument("--problem-id", type=int, default=1)
    parser.add_argument("--answer-file", required=True)
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--output-dir", default="outputs/llm_judge")
    args = parser.parse_args()

    record = _load_jsonl_record(Path(args.dataset_file), args.problem_id)
    answer = Path(args.answer_file).read_text(encoding="utf-8", errors="replace")
    problem = str(record.get("problem") or "")
    reference = str(record.get("answer") or record.get("rubric") or "")

    api_key = os.environ.get("API_KEY") or os.environ.get("DF_API_KEY")
    api_base = os.environ.get("API_BASE") or os.environ.get("DF_API_URL")
    if not api_key or not api_base:
        raise RuntimeError("Set API_KEY/API_BASE or DF_API_KEY/DF_API_URL.")

    client = OpenAI(api_key=api_key, base_url=api_base)
    response = client.chat.completions.create(
        model=args.model,
        messages=_judge_prompt(problem, reference, answer),
        temperature=0,
        max_tokens=3500,
    )
    raw = response.choices[0].message.content or ""
    judgment = _extract_json(raw)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "judge_raw.txt"
    json_path = output_dir / "judge_result.json"
    md_path = output_dir / "judge_report.md"
    raw_path.write_text(raw, encoding="utf-8")
    json_path.write_text(json.dumps(judgment, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, judgment)
    print(json.dumps({
        "output_dir": str(output_dir),
        "json": str(json_path),
        "markdown": str(md_path),
        "overall_score_0_to_10": judgment.get("overall_score_0_to_10"),
        "verdict": judgment.get("verdict"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

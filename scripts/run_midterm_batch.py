from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROBLEM_IDS = [1, 2, 6, 8, 10, 13, 16]


@dataclass(frozen=True)
class CasePaths:
    case_dir: Path
    answer_file: Path
    run_log: Path
    payload_report: Path
    judge_dir: Path
    judge_log: Path
    judge_result: Path


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


def case_paths(output_dir: Path, problem_id: int) -> CasePaths:
    case_dir = output_dir / "cases" / f"problem_{problem_id:03d}"
    judge_dir = case_dir / "judge"
    return CasePaths(
        case_dir=case_dir,
        answer_file=case_dir / "answer.md",
        run_log=case_dir / "run.log",
        payload_report=case_dir / "payload_report.json",
        judge_dir=judge_dir,
        judge_log=case_dir / "judge.log",
        judge_result=judge_dir / "judge_result.json",
    )


def is_case_complete(paths: CasePaths, run_judge: bool = True) -> bool:
    required = [paths.answer_file, paths.payload_report]
    if run_judge:
        required.append(paths.judge_result)
    return all(path.exists() and path.stat().st_size > 0 for path in required)


def _run_and_log(command: List[str], log_path: Path, cwd: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as log_fp:
        log_fp.write("$ " + " ".join(command) + "\n\n")
        log_fp.flush()
        process = subprocess.run(
            command,
            cwd=str(cwd),
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return int(process.returncode)


def _run_case(
    problem_id: int,
    dataset_file: Path,
    output_dir: Path,
    director_model: str,
    mode: str,
    judge_model: str,
    skip_existing: bool,
    run_judge: bool,
    dry_run: bool,
) -> dict:
    paths = case_paths(output_dir, problem_id)
    paths.case_dir.mkdir(parents=True, exist_ok=True)
    paths.judge_dir.mkdir(parents=True, exist_ok=True)

    if skip_existing and is_case_complete(paths, run_judge=run_judge):
        return {
            "problem_id": problem_id,
            "status": "skipped_existing",
            "answer_file": str(paths.answer_file),
            "payload_report": str(paths.payload_report),
            "judge_result": str(paths.judge_result) if run_judge else "",
        }

    run_command = [
        sys.executable,
        str(ROOT / "run.py"),
        "--dataset-file",
        str(dataset_file),
        "--problem-id",
        str(problem_id),
        "--director-model",
        director_model,
        "--mode",
        mode,
        "--output-file",
        str(paths.answer_file),
        "--log-file",
        str(paths.run_log),
        "--payload-report-file",
        str(paths.payload_report),
    ]

    judge_command: List[str] = []
    if run_judge:
        judge_command = [
            sys.executable,
            str(ROOT / "scripts" / "llm_judge_answer.py"),
            "--dataset-file",
            str(dataset_file),
            "--problem-id",
            str(problem_id),
            "--answer-file",
            str(paths.answer_file),
            "--model",
            judge_model,
            "--output-dir",
            str(paths.judge_dir),
        ]

    if dry_run:
        return {
            "problem_id": problem_id,
            "status": "dry_run",
            "run_command": run_command,
            "judge_command": judge_command,
        }

    run_code = _run_and_log(run_command, paths.case_dir / "driver_run.log", ROOT)
    if run_code != 0:
        return {
            "problem_id": problem_id,
            "status": "run_failed",
            "exit_code": run_code,
            "answer_file": str(paths.answer_file),
            "payload_report": str(paths.payload_report),
        }

    judge_code = None
    if run_judge:
        judge_code = _run_and_log(judge_command, paths.judge_log, ROOT)
        if judge_code != 0:
            return {
                "problem_id": problem_id,
                "status": "judge_failed",
                "run_exit_code": run_code,
                "judge_exit_code": judge_code,
                "answer_file": str(paths.answer_file),
                "payload_report": str(paths.payload_report),
                "judge_result": str(paths.judge_result),
            }

    return {
        "problem_id": problem_id,
        "status": "complete",
        "run_exit_code": run_code,
        "judge_exit_code": judge_code,
        "answer_file": str(paths.answer_file),
        "payload_report": str(paths.payload_report),
        "judge_result": str(paths.judge_result) if run_judge else "",
    }


def _default_problem_id_text(ids: Iterable[int]) -> str:
    return ",".join(str(item) for item in ids)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the midterm multi-question PayloadView batch.")
    parser.add_argument("--dataset-file", default="test.jsonl")
    parser.add_argument("--problem-ids", default=_default_problem_id_text(DEFAULT_PROBLEM_IDS))
    parser.add_argument("--output-dir", default="outputs/midterm_showcase")
    parser.add_argument("--mode", default="fast", choices=["fast", "hq"])
    parser.add_argument("--director-model", default=os.environ.get("MIDTERM_DIRECTOR_MODEL") or os.environ.get("DIRECTOR_MODEL") or "")
    parser.add_argument("--judge-model", default=os.environ.get("MIDTERM_JUDGE_MODEL") or "gpt-4.1")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--no-judge", action="store_true", help="Run answer generation only; analysis will mark judge as missing.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned work without calling models.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    problem_ids = parse_problem_ids(args.problem_ids)
    dataset_file = Path(args.dataset_file)
    if not dataset_file.is_absolute():
        dataset_file = ROOT / dataset_file
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    run_judge = not bool(args.no_judge)
    if not args.director_model and not args.dry_run:
        raise RuntimeError("Set --director-model or MIDTERM_DIRECTOR_MODEL/DIRECTOR_MODEL.")

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for problem_id in problem_ids:
        row = _run_case(
            problem_id=problem_id,
            dataset_file=dataset_file,
            output_dir=output_dir,
            director_model=args.director_model,
            mode=args.mode,
            judge_model=args.judge_model,
            skip_existing=bool(args.skip_existing),
            run_judge=run_judge,
            dry_run=bool(args.dry_run),
        )
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    manifest = {
        "dataset_file": str(dataset_file),
        "problem_ids": problem_ids,
        "mode": args.mode,
        "run_judge": run_judge,
        "rows": rows,
    }
    manifest_path = output_dir / "batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

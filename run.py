from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv

from sciagent.runner import run_from_dataset, run_from_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ResearchFlowAgent Runner")
    parser.add_argument("--ground-truth-model", type=str, default="", help="GroundTruthSearcher model ID")
    parser.add_argument("--question-intent-model", type=str, default="", help="QuestionIntentAligner model ID")
    parser.add_argument("--axiom-builder-model", type=str, default="", help="AxiomBuilder model ID")
    parser.add_argument("--prompt-proximity-model", type=str, default="", help="PromptProximitySelector model ID")
    parser.add_argument("--pathway-mapping-model", type=str, default="", help="PathwayMappingAgent model ID")
    parser.add_argument("--comparison-matrix-model", type=str, default="", help="ComparisonMatrixAgent model ID")
    parser.add_argument("--input-file", type=str, default="", help="题目文件路径（纯文本）")
    parser.add_argument("--dataset-file", type=str, default="", help="JSONL 数据集路径")
    parser.add_argument("--problem-id", type=int, default=0, help="题号（JSONL 行号，1-based）")
    parser.add_argument("--director-model", type=str, required=True, help="Director 使用的模型 ID")
    parser.add_argument("--context-model", type=str, default="", help="ContextMiner 模型 ID")
    parser.add_argument("--task-graph-model", type=str, default="", help="TaskGraphBuilder 模型 ID")
    parser.add_argument("--hypothesis-model", type=str, default="", help="HypothesisModeler 模型 ID")
    parser.add_argument("--wetlab-model", type=str, default="", help="WetLabDesigner 模型 ID")
    parser.add_argument("--insilico-model", type=str, default="", help="InSilicoDesigner 模型 ID")
    parser.add_argument("--data-analysis-model", type=str, default="", help="DataAnalysisDesigner 模型 ID")
    parser.add_argument("--tradeoff-model", type=str, default="", help="TradeoffAgent 模型 ID")
    parser.add_argument("--verification-model", type=str, default="", help="Verification 模型 ID")
    parser.add_argument("--writer-model", type=str, default="", help="ScientificWriter 模型 ID")
    parser.add_argument("--polisher-model", type=str, default="", help="TerminologyPolisher 模型 ID")
    parser.add_argument("--meta-reviewer-model", type=str, default="", help="MetaReviewer 模型 ID")
    parser.add_argument("--proof-planner-model", type=str, default="", help="ProofPlanner 模型 ID")
    parser.add_argument("--formal-deriver-model", type=str, default="", help="FormalDeriver 模型 ID")
    parser.add_argument("--proof-auditor-model", type=str, default="", help="ProofAuditor 模型 ID")
    parser.add_argument("--patcher-model", type=str, default="", help="PatcherAgent 模型 ID")
    parser.add_argument("--mechanism-inferer-model",
                        type=str,
                        default="",
                        help="MechanismInfererAgent 模型 ID (默认复用 hypothesis-model)")
    parser.add_argument("--critique-model", type=str, default="", help="CritiqueAgent 模型 ID (默认复用 tradeoff-model)")
    parser.add_argument("--estimator-model", type=str, default="", help="EstimatorAgent 模型 ID (默认复用 formal-deriver-model)")
    parser.add_argument("--synthesizer-model", type=str, default="", help="SynthesizerAgent 模型 ID (默认复用 writer-model)")
    parser.add_argument("--mode", type=str, default="hq", choices=["fast", "hq"], help="运行模式")
    parser.add_argument("--output-file", type=str, default="", help="输出保存路径（可选）")
    parser.add_argument("--log-file", type=str, default="", help="完整日志保存路径（可选）")
    parser.add_argument("--payload-report-file", type=str, default="", help="Payload 消耗对比报告保存路径（可选）")
    return parser


def _summarize_payload_views(payload_views: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_rendered = sum(int(v.get("rendered_token_cost", v.get("token_cost", 0)) or 0) for v in payload_views)
    total_legacy = sum(int(v.get("legacy_token_cost", 0) or 0) for v in payload_views if v.get("legacy_token_cost") is not None)
    comparable = [v for v in payload_views if v.get("legacy_token_cost") is not None]
    by_role: Dict[str, Dict[str, Any]] = {}
    for view in payload_views:
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
        if view.get("payload_verified"):
            bucket["verified"] += 1
        else:
            bucket["fail_soft"] += 1
    savings = total_legacy - total_rendered if comparable else None
    return {
        "payload_view_count": len(payload_views),
        "comparable_view_count": len(comparable),
        "verified_count": sum(1 for v in payload_views if v.get("payload_verified")),
        "fail_soft_count": sum(1 for v in payload_views if not v.get("payload_verified")),
        "total_rendered_token_cost": total_rendered,
        "total_legacy_token_cost": total_legacy if comparable else None,
        "total_token_savings_vs_legacy": savings,
        "total_token_savings_ratio_vs_legacy": round(savings / total_legacy, 4) if comparable and total_legacy else None,
        "by_role": by_role,
    }


def main():
    load_dotenv(override=True)
    parser = build_parser()
    args = parser.parse_args()

    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = log_path.open("w", encoding="utf-8")

        class _Tee:

            def __init__(self, *streams):
                self._streams = streams

            def write(self, data: str) -> int:
                for stream in self._streams:
                    stream.write(data)
                    stream.flush()
                return len(data)

            def flush(self) -> None:
                for stream in self._streams:
                    stream.flush()

        sys.stdout = _Tee(sys.stdout, log_fp)
        sys.stderr = _Tee(sys.stderr, log_fp)

    model_overrides = {
        "context": args.context_model,
        "ground_truth_searcher": args.ground_truth_model,
        "question_intent": args.question_intent_model,
        "task_graph": args.task_graph_model,
        "axiom_builder": args.axiom_builder_model,
        "hypothesis": args.hypothesis_model,
        "prompt_proximity_selector": args.prompt_proximity_model,
        "wetlab": args.wetlab_model,
        "insilico": args.insilico_model,
        "data_analysis": args.data_analysis_model,
        "pathway_mapping": args.pathway_mapping_model,
        "comparison_matrix": args.comparison_matrix_model,
        "tradeoff": args.tradeoff_model,
        "verification": args.verification_model,
        "writer": args.writer_model,
        "polisher": args.polisher_model,
        "meta_reviewer": args.meta_reviewer_model,
        "proof_planner": args.proof_planner_model,
        "formal_deriver": args.formal_deriver_model,
        "proof_auditor": args.proof_auditor_model,
        "patcher": args.patcher_model,
        "mechanism_inferer": args.mechanism_inferer_model,
        "critique": args.critique_model,
        "estimator": args.estimator_model,
        "synthesizer": args.synthesizer_model,
    }
    model_overrides = {k: v for k, v in model_overrides.items() if v}

    return_dossier = bool(args.payload_report_file)

    if args.dataset_file:
        result = run_from_dataset(
            args.dataset_file,
            args.problem_id,
            args.director_model,
            model_overrides=model_overrides,
            mode=args.mode,
            return_dossier=return_dossier,
        )
    else:
        if not args.input_file:
            raise ValueError("未提供 input-file 或 dataset-file + problem-id。")
        result = run_from_file(
            args.input_file,
            args.director_model,
            model_overrides=model_overrides,
            mode=args.mode,
            return_dossier=return_dossier,
        )
    if return_dossier:
        dossier = result
        output = dossier.final or dossier.draft or ""
        payload_views = getattr(dossier, "payload_views", []) or []
        report = {
            "summary": _summarize_payload_views(payload_views),
            "payload_views": payload_views,
        }
        report_path = Path(args.payload_report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            __import__("json").dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        output = result
    if args.output_file:
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

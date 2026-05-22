try:
    from .workflow_parser import build_sample_workflow_session, parse_workflow_log, workflow_session_to_json
except ModuleNotFoundError:  # Optional showcase helpers are not present in this repo snapshot.
    build_sample_workflow_session = None
    parse_workflow_log = None
    workflow_session_to_json = None

try:
    from .workflow_showcase import render_workflow_showcase_html, write_workflow_showcase_html
except ModuleNotFoundError:  # Optional showcase helpers are not present in this repo snapshot.
    render_workflow_showcase_html = None
    write_workflow_showcase_html = None
from .schemas import (
    ContextBrief,
    ContractReport,
    DecisionRecord,
    DerivationBlock,
    DerivationIntent,
    DirectorDecision,
    DomainRoute,
    GeneralityReport,
    HypothesisItem,
    HypothesisPack,
    MethodPlan,
    PatchPlan,
    ProofGapReport,
    ProofPlan,
    ProofStep,
    ResearchDossier,
    ResearchTask,
    ResearchTaskGraph,
    VerificationIssue,
    VerificationReport,
)

try:
    from .runner import run_from_dataset, run_from_file, run_research_agent
except Exception:  # pragma: no cover - optional during lightweight showcase usage
    run_research_agent = None
    run_from_file = None
    run_from_dataset = None

__all__ = [
    # Runner functions
    "run_research_agent",
    "run_from_file",
    "run_from_dataset",
    "parse_workflow_log",
    "build_sample_workflow_session",
    "workflow_session_to_json",
    "render_workflow_showcase_html",
    "write_workflow_showcase_html",
    # Schemas
    "ContextBrief",
    "ContractReport",
    "DecisionRecord",
    "DerivationBlock",
    "DerivationIntent",
    "DirectorDecision",
    "DomainRoute",
    "GeneralityReport",
    "HypothesisItem",
    "HypothesisPack",
    "MethodPlan",
    "PatchPlan",
    "ProofGapReport",
    "ProofPlan",
    "ProofStep",
    "ResearchDossier",
    "ResearchTask",
    "ResearchTaskGraph",
    "VerificationIssue",
    "VerificationReport",
]

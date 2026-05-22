from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SubquestionIntent(BaseModel):
    """单个子问题的题意约束结构（不是解释结构）。

    This is a CONSTRAINT structure, not an INTERPRETATION structure.
    It defines what the question is asking and what counts as on-topic,
    but it MUST NOT infer the scientific answer.
    """

    subquestion: str = Field(description="The original subquestion text (verbatim from the prompt).", )
    question_goal: str = Field(description="What this subquestion is asking for (task-level, not answer-level). "
                               "E.g., 'Describe the consequence of changing X', 'Explain why Y occurs', "
                               "'Compare A and B'. Do NOT include the actual answer or preferred mechanism.", )
    required_answer_shape: str = Field(
        default="",
        description="The expected structure of the answer: e.g., 'consequence + brief rationale', "
        "'list of entities with roles', 'numerical value with derivation', 'comparison table'. "
        "Do NOT specify what the answer content should be.",
    )
    on_topic_entities: List[str] = Field(
        default_factory=list,
        description="Entities/materials/conditions explicitly mentioned in the prompt that are relevant to this subquestion. "
        "E.g., ['DIC', 'PLS', 'DMF', 'carbodiimide coupling']. Do NOT add inferred entities.",
    )
    operations_under_question: List[str] = Field(
        default_factory=list,
        description="The specific operations/steps/conditions being questioned. "
        "E.g., ['changing MWCO from 10kDa to 1kDa', 'adjusting pH to 6.5-7.0']. "
        "Extract from prompt, do NOT infer operational intent.",
    )
    explicit_conditions: List[str] = Field(
        default_factory=list,
        description="Conditions/constraints explicitly stated in the prompt for this subquestion. "
        "E.g., ['reaction in DMF', 'dialysis at 10kDa MWCO', 'pH 6.0-6.5']. "
        "Do NOT add inferred conditions.",
    )
    answer_scope: str = Field(
        default="",
        description="The scope within which the answer should stay: 'protocol-level consequence', "
        "'mechanism at the reaction step level', 'comparison of stated conditions only'. "
        "Do NOT specify which mechanism is correct.",
    )
    do_not_assume: List[str] = Field(
        default_factory=list,
        description="Topics/mechanisms that should NOT be assumed or introduced unless explicitly required. "
        "E.g., 'Do not assume pharmacokinetics is relevant', 'Do not introduce EPR model', "
        "'Do not discuss general hydrolysis unless pH stability is explicitly questioned'.",
    )


class ConstraintEntry(BaseModel):
    id: str = Field(description="Unique constraint ID, e.g., 'c_1', 'c_2'.")
    constraint_type: Literal["deliverable", "scope", "format",
                             "content"] = Field(description="Category: deliverable (list/show items), scope (only/exclude), "
                                                "format (step-by-step/derivation), content (must mention specific terms).")
    text: str = Field(description="The constraint in natural language.")
    source: str = Field(
        default="problem_text",
        description="Where this constraint was extracted from.",
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Surface-form keywords/phrases that a compliant output MUST contain. "
        "Used for deterministic verification (case-insensitive substring match).",
    )
    verification_strategy: Literal["keyword_presence", "section_presence", "count_check", "llm_required"] = Field(
        default="keyword_presence",
        description="How to verify this constraint deterministically.",
    )
    satisfied_by: List[str] = Field(
        default_factory=list,
        description="List of agent step IDs or task IDs that have satisfied this constraint.",
    )
    status: Literal["pending", "satisfied", "violated", "deferred"] = Field(default="pending", )


class ConstraintLedger(BaseModel):

    constraints: List[ConstraintEntry] = Field(default_factory=list)
    last_validated_at: str = Field(
        default="",
        description="Pipeline stage name where last validation occurred.",
    )


class QuestionIntent(BaseModel):
    """题意约束层：定义题目边界，不预判答案。

    This is a CONSTRAINT structure, NOT a reasoning structure.
    Its purpose is to define what the question is asking and what counts as on-topic,
    but it MUST NOT infer the scientific answer or preferred mechanism.

    DO NOT OUTPUT:
    - "The answer is likely X"
    - "The primary mechanism is Y"
    - "The main bottleneck is Z"
    - "Preferred explanation: ..."

    ONLY OUTPUT:
    - What the question is asking (task-level)
    - What entities/operations are in scope
    - What would count as off-topic expansion
    """

    question_type: str = Field(
        default="exam_problem",
        description="Type of question: 'protocol_consequence', 'mechanism_explanation', 'comparison', "
        "'design_experiment', 'calculation', etc. Do NOT include answer hints.",
    )
    global_goal: str = Field(
        default="",
        description="One-sentence summary of what the entire question wants the solver to DO (not what the answer IS). "
        "E.g., 'Explain the consequences of protocol modifications', 'Compare two experimental setups'. "
        "Do NOT include preferred conclusions.",
    )
    subquestion_intents: List[SubquestionIntent] = Field(
        default_factory=list,
        description="Per-subquestion constraint alignment. One entry per subquestion.",
    )
    scope_limits: str = Field(
        default="",
        description="Global scope constraint: 'Stay within protocol-level reasoning', "
        "'Focus on stated conditions only', 'Do not generalize beyond the experimental setup'. "
        "Do NOT specify which scientific direction is correct.",
    )
    forbidden_expansions: List[str] = Field(
        default_factory=list,
        description="Topics/mechanisms that should NOT be introduced unless explicitly required by the question. "
        "E.g., 'Do not discuss pharmacokinetics', 'Do not introduce EPR/biodistribution models', "
        "'Do not analyze general stability unless pH stability is the question'.",
    )
    grading_focus: List[str] = Field(
        default_factory=list,
        description="What the grading rubric likely cares about (task-level, not answer-level): "
        "e.g., 'Correctly identify the consequence', 'Provide rationale anchored to prompt conditions', "
        "'Compare stated setups without introducing external models'. "
        "Do NOT specify what the correct answer content is.",
    )


class RationalSelection(BaseModel):
    """PromptProximitySelector 的输出：选择最贴题的解释。

    在无 rubric 的情况下，正确性的唯一锚点是贴近题干。
    这个结构记录了为什么某个解释被选中，以及为什么其他解释被拒绝。
    """

    subquestion_id: str = Field(description="Which subquestion this selection is for.", )
    selected_rationale: str = Field(
        description="The explanation that is closest to the prompt logic and requires fewest external assumptions.", )
    selection_reason: str = Field(
        description="Why this rationale was selected: how it stays closest to prompt entities/operations/conditions.", )
    prompt_distance_score: int = Field(
        default=0,
        description="How many external assumptions this rationale requires (lower is better). "
        "0 = uses only prompt entities/operations, 1 = adds one external concept, etc.",
    )
    rejected_rationales: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Other candidate explanations that were rejected, with rejection reasons. "
        "Format: [{'rationale': '...', 'rejection_reason': '...'}]",
    )
    answer_scope_alignment: str = Field(
        default="",
        description="Whether the selected rationale stays within the answer_scope defined by QuestionIntent. "
        "E.g., 'protocol-level consequence' vs 'deep mechanistic chemistry'.",
    )


class EntityMap(BaseModel):
    """生物题：实体分层映射（强制区分基因/蛋白/细胞/个体表型层级）。"""

    genetic_level: List[str] = Field(
        default_factory=list,
        description="Genes, promoters/enhancers, alleles/mutants (e.g., *waslb*, promoter, GOF/LOF).",
    )
    protein_level: List[str] = Field(
        default_factory=list,
        description="Proteins/complexes, PTMs, conformations, activity states (e.g., Waslb, phosphorylated).",
    )
    cellular_level: List[str] = Field(
        default_factory=list,
        description="Cell-level processes (migration, proliferation, apoptosis, signaling output).",
    )
    organismal_level: List[str] = Field(
        default_factory=list,
        description="Organism/tissue phenotypes (lethality, limb defects, morphology).",
    )


class PhenotypeSummary(BaseModel):
    """生物题：显式区分生存表型与形态表型，避免混淆。"""

    viability: Literal["lethal", "viable", "sub-lethal", "unknown"] = Field(
        default="unknown",
        description="Viability phenotype explicitly stated in the prompt (lethal/viable/sub-lethal/unknown).",
    )
    morphology: List[str] = Field(
        default_factory=list,
        description="Explicit morphology phenotypes stated in the prompt (verbatim-like short phrases).",
    )
    notes: List[str] = Field(default_factory=list, description="Optional notes about phenotype extraction limits.")


class ContextBrief(BaseModel):
    """题目上下文摘要。"""

    key_terms: List[str]
    entities: List[str]
    given_data: Dict[str, Any]
    assumptions_in_text: List[str]
    constraints: List[str]
    deliverables: List[str]
    subquestions: List[str]
    negative_constraints: List[str] = Field(
        default_factory=list,
        description=("Explicit statements of what is NOT affected, unchanged, or absent "
                     "(e.g., 'fin rays are unaffected', 'no obvious defects')."),
    )
    core_conflicts: List[str] = Field(
        default_factory=list,
        description=("Key contradictions or opposing results mentioned in the text "
                     "(e.g., 'GOF is lethal while LOF is viable')."),
    )
    # ---- Biology-specific (exam-oriented) ----
    entity_map: EntityMap = Field(
        default_factory=EntityMap,
        description="Biology-only: hierarchical entity mapping to prevent gene/protein/phenotype confusion.",
    )
    temporal_context: List[str] = Field(
        default_factory=list,
        description="Biology-only: time window / developmental stage constraints explicitly stated in the prompt.",
    )
    spatial_context: List[str] = Field(
        default_factory=list,
        description="Biology-only: tissue/organ/cell-type specificity explicitly stated in the prompt.",
    )
    # ---- Chemistry-specific (exam-oriented) ----
    reaction_conditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Chemistry-only: extracted reaction conditions (solvent, temperature, catalyst, pH, light, pressure, time).",
    )
    # ---- Evidence indexing (biology/chemistry often relies on textual evidence) ----
    empirical_evidence: List[str] = Field(
        default_factory=list,
        description=("Explicit empirical findings stated in the prompt (phenotypes, observations, assay results). "
                     "Keep each item short and verbatim-like; do NOT interpret."),
    )
    text_segments: Dict[str, str] = Field(
        default_factory=dict,
        description=("Short indexed text segments from the prompt for downstream retrieval. "
                     "Keys like 'p1','p2'... Values must be short excerpts (avoid full long paragraphs)."),
    )
    # ---- Evidence anchoring (exam-style quote-then-write) ----
    evidence_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description=("Map each sub-question (or 'main') to ONE most relevant verbatim-like key sentence from the prompt. "
                     "Used to force quote-then-write and prevent semantic drift."),
    )
    unchanged_features: List[str] = Field(
        default_factory=list,
        description=("Explicit list of features/states that are stated as unchanged/unaffected/normal/intact. "
                     "These are 'negative points' and must be protected from hallucinated changes."),
    )
    must_have_terms: List[str] = Field(
        default_factory=list,
        description=("Specialized terms/entities that must appear verbatim in the final answer (rubric keyword hit-rate). "
                     "Prefer domain-specific proper nouns (e.g., 'Intermediate radials')."),
    )
    phenotype_summary: PhenotypeSummary = Field(
        default_factory=PhenotypeSummary,
        description="Biology-only: explicit phenotype classification extracted from prompt.",
    )
    # ---- Chemistry-only: condition->product binding ----
    reaction_tuples: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=("Chemistry-only: extracted tuples binding (reactants, conditions) -> products. "
                     "Each item is a dict with keys like reactants/conditions/products (short, verbatim-like)."),
    )
    # ---- Physics-specific (exam-oriented) ----
    equations_and_formulas: List[str] = Field(
        default_factory=list,
        description=("Physics-only: mathematical formulas/equations extracted verbatim from the prompt. "
                     "Preserve LaTeX notation exactly as written (e.g., '\\hat{R}', '\\langle A \\rangle_w'). "
                     "Do NOT paraphrase or interpret; keep original symbols and structure."),
    )


class ResearchTask(BaseModel):
    """科研任务节点。

    micro_checklists field enforces dense requirement unpacking.
    When a deliverable contains comma-separated items (e.g., "explain A, B, and C"),
    TaskGraphBuilder MUST extract them into micro_checklists for explicit tracking.
    This prevents list item omissions that lose rubric points.
    """

    id: str
    title: str
    task_type: Literal[
        "retrieval_task",
        "derive",
        "mechanism_inference",
        "pathway_mapping",
        "comparison_table",
        "design_wetlab",
        "design_insilico",
        "design_data_analysis",
        "critique_and_tradeoff",
        "parameter_estimation",
        "sanity_check",
        "synthesis",
    ]
    inputs: List[str]
    deliverable: str

    # 微观清单字段：强迫 TaskGraph 将长句拆解成数组
    micro_checklists: List[str] = Field(
        default_factory=list,
        description="Extract dense requirements into isolated verifiable points. "
        "Example: If deliverable is 'Explain roles of geneA, geneB, geneC', "
        "micro_checklists should be ['Explain role of geneA', 'Explain role of geneB', 'Explain role of geneC']. "
        "Each item in this list corresponds to an independent rubric scoring point.")

    depends_on: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)


class ResearchTaskGraph(BaseModel):
    """科研任务图。"""

    tasks: List[ResearchTask]
    notes: List[str] = Field(default_factory=list)


class HypothesisItem(BaseModel):
    """假设或机制条目（受题干约束的局部解释器）。

    CRITICAL DESIGN: Each hypothesis must declare its inference_level and answer_relevance.
    This prevents the system from promoting speculative domain-template explanations
    to the same status as stem-supported conclusions.
    """

    id: str
    statement: str
    variables: List[str] = Field(default_factory=list)
    observables: List[str] = Field(default_factory=list)
    causal_chain: List[str] = Field(default_factory=list)
    falsifiable_tests: List[str] = Field(default_factory=list)
    validation_paths: List[str] = Field(default_factory=list)

    evidence_support: List[str] = Field(
        default_factory=list,
        description="Verbatim or near-verbatim evidence from the problem text that supports this hypothesis. "
        "If no direct evidence exists, this list should be empty.",
    )
    inference_level: Literal["explicit", "inference", "speculative"] = Field(
        default="inference",
        description="How strongly the problem text supports this hypothesis: "
        "'explicit' = directly stated in the prompt, "
        "'inference' = logically derivable from prompt facts with minimal external knowledge, "
        "'speculative' = requires significant domain knowledge beyond what the prompt provides.",
    )
    answer_relevance: str = Field(
        default="",
        description="Which subquestion(s) this hypothesis directly answers. "
        "E.g., 'Directly answers Q2: consequence of using 1 kDa MWCO'.",
    )
    eliminated_alternatives: List[str] = Field(
        default_factory=list,
        description="Common domain-template explanations that were considered but rejected, with reasons. "
        "E.g., 'EPR-based biodistribution model rejected: question does not ask about in vivo distribution'.",
    )


class HypothesisPack(BaseModel):
    """假设集合。"""

    hypotheses: List[HypothesisItem]
    notes: List[str] = Field(default_factory=list)


class AxiomLedger(BaseModel):
    """
    全局公理账本 
    """

    # Core physical framework axioms
    space_type: str = Field(default="",
                            description="Fundamental space structure (e.g., 'Discrete 3D Cubic Lattice with L sites', "
                            "'Continuous 3D Euclidean space', 'Curved spacetime with metric g_μν'). "
                            "IMMUTABLE: All subsequent derivations MUST respect this space structure.")

    particle_type: str = Field(default="",
                               description="Particle species and interaction status (e.g., 'Interacting spin-1/2 nucleons', "
                               "'Free non-relativistic electrons', 'Relativistic fermions with Yukawa coupling'). "
                               "IMMUTABLE: Determines which Hamiltonians/Lagrangians are valid.")

    state_hierarchy: List[str] = Field(
        default_factory=list,
        description="Energy level structure and state classification (e.g., 'Ground state is bound (E < 0)', "
        "'First excited state at E = 81.38 MeV', 'Continuum states for E > 0'). "
        "IMMUTABLE: Prevents sign errors and wrong energy ordering.")

    # Theoretical framework axioms
    formalism: str = Field(default="",
                           description="Mathematical formalism in use (e.g., 'Fock space second quantization', "
                           "'Schrödinger wavefunction formalism', 'Path integral formulation'). "
                           "IMMUTABLE: Determines valid operators and commutation relations.")

    symmetries: List[str] = Field(
        default_factory=list,
        description="Fundamental symmetries that MUST be preserved (e.g., 'Translational invariance', "
        "'SU(2) spin symmetry', 'Gauge invariance under U(1)'). "
        "IMMUTABLE: All derived quantities must respect these symmetries.")

    boundary_conditions: List[str] = Field(
        default_factory=list,
        description="Boundary/initial conditions that constrain solutions (e.g., 'Periodic boundary conditions', "
        "'Box size L_phy = 3.4 fm', 'Asymptotic flatness at spatial infinity'). "
        "IMMUTABLE: Determines allowed momentum/energy quantization.")

    explicit_protocol_facts: List[str] = Field(
        default_factory=list,
        description="VERBATIM facts from the prompt: materials, sequence, conditions, observations. "
        "Examples: 'PLS is dissolved in DMF', 'Dialysis uses 10 kDa MWCO', 'pH is adjusted to 6.0-6.5'. "
        "Do NOT include: 'PLS must be in free acid form for activation' (this is interpretation). "
        "IMMUTABLE: Final answer cannot contradict these stated facts.")

    biological_axioms: List[str] = Field(
        default_factory=list,
        description="Biology-only: VERBATIM biological facts from prompt "
        "(e.g., 'waslb GOF is embryonic lethal', 'Fin rays are unaffected'). "
        "Do NOT include interpretations like 'Waslb regulates actin polymerization' unless explicitly stated. "
        "IMMUTABLE: Prevents hallucination of contradictory phenotypes.")

    chemical_axioms: List[str] = Field(default_factory=list,
                                       description="Chemistry-only: VERBATIM reaction conditions from prompt "
                                       "(e.g., 'Reaction in DMF', 'pH 6.0-6.5', 'Temperature 25°C'). "
                                       "Do NOT include mechanistic interpretations like 'Requires protonation for activation'. "
                                       "IMMUTABLE: Prevents wrong condition assumptions.")

    soft_interpretations: List[str] = Field(
        default_factory=list,
        description="Interpretive claims that are reasonable but NOT explicitly stated in the prompt. "
        "These MUST NOT be used in violation_checks. They serve as guidance only, not hard constraints. "
        "Examples: 'protonation state likely affects binding', 'EPR effect may contribute to accumulation'. "
        "If an axiom cannot be traced to a verbatim prompt statement, it belongs here, not in the hard fields.")

    violation_checks: List[str] = Field(
        default_factory=list,
        description="Explicit checks that downstream outputs MUST pass. "
        "CRITICAL CONSTRAINT: Only encode checks that enforce fidelity to EXPLICIT conditions/facts from the prompt. "
        "Do NOT convert a preferred explanation or mechanism into a violation check. "
        "Examples of VALID checks: 'All energy expressions must contain lattice dispersion term', "
        "'Lethality must be stated if phenotype_summary.viability=lethal'. "
        "Examples of INVALID checks: 'Must discuss protonation state', 'Must address EPR effect' "
        "(these are explanatory preferences, not prompt-stated facts).")

    notes: List[str] = Field(default_factory=list)


class MethodPlan(BaseModel):
    """实验/模拟/分析方法方案。
    """

    id: str
    task_id: str
    method_type: Literal["wetlab", "insilico", "data_analysis"]
    title: str

    # 1. 拆分原有的宽泛 materials，强制具象化
    materials_and_reagents: List[str] = Field(
        default_factory=list,
        description="Must include exact concentrations (e.g., '10^5 CFU/ml', '0.5 mM IPTG'), "
        "cell lines (e.g., 'HEK293T'), or buffer formulas (e.g., 'PBS pH 7.4'). "
        "Generic terms like 'appropriate buffer' will fail rubric scoring.")
    software_and_scripts: List[str] = Field(default_factory=list,
                                            description="Must list exact software names (e.g., 'GROMACS 2021.3', 'PyMOL') "
                                            "and script names (e.g., 'martinize.py', 'INSANE.py'). "
                                            "Generic terms like 'molecular dynamics software' will fail rubric scoring.")
    structural_or_database_ids: List[str] = Field(
        default_factory=list,
        description="e.g., 'PDB ID: 7KOO', 'UniProt: P12345', 'AlphaFold: AF-P12345-F1'. "
        "Required when the task involves structural biology or bioinformatics.")

    steps: List[str]
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Must include exact numerical ranges (e.g., '10^5 CFU/ml', '300K', '1 atm', '100 ns'). "
        "Generic terms like 'standard conditions' will fail rubric scoring.")

    # 2. 新增统计学硬性约束
    statistical_power_and_n_value: str = Field(
        default="",
        description="Explicitly state the number of biological/technical replicates (e.g., 'n=6 biological replicates', "
        "'5 independent MD runs of 100 ns each'). Required for experimental design tasks.")

    controls: List[str] = Field(default_factory=list)
    readouts: List[str] = Field(default_factory=list)
    failure_modes: List[str] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)


class DecisionRecord(BaseModel):
    """方案决策记录。"""

    options: List[str]
    criteria: List[str]
    chosen: str
    risks: List[str] = Field(default_factory=list)
    switch_conditions: List[str] = Field(default_factory=list)


class VerificationIssue(BaseModel):
    """验证与一致性问题。"""

    id: str
    severity: Literal["low", "medium", "high"]
    message: str
    suggestion: str = ""
    affected_component_id: str = ""  # ID of the Task or DerivationBlock causing the issue


class VerificationReport(BaseModel):
    """验证与一致性报告。"""

    issues: List[VerificationIssue]
    notes: List[str] = Field(default_factory=list)


class DomainRoute(BaseModel):
    """领域路由结果。"""

    domain: Literal["physics", "chemistry", "biology", "mixed"]
    confidence: float
    evidence_terms: List[str]


class SubjectProfile(BaseModel):
    """按学科注入的约束/术语表（非从题面抽取，而是系统侧配置）。"""

    domain: Literal["physics", "chemistry", "biology", "mixed"]
    banned_terms: List[str] = Field(default_factory=list, description="Forbidden vague/incorrect terms for the domain.")
    preferred_terms: List[str] = Field(default_factory=list, description="Recommended precise terms for the domain.")
    disambiguation_rules: List[str] = Field(
        default_factory=list,
        description="Rules to avoid common confusions (e.g., gene vs protein; transcription vs translation).",
    )
    writer_constraints: List[str] = Field(
        default_factory=list,
        description="Writer-level constraints (e.g., gene symbols italic in markdown).",
    )


class DirectorDecision(BaseModel):
    """ResearchDirector 的决策结果。"""

    domain: Literal["physics", "chemistry", "biology", "mixed"]
    role_set: List[str]
    routing_notes: List[str] = Field(default_factory=list)
    synthesis_strategy: str
    output_structure: List[str]


class ContractReport(BaseModel):
    """科学方法契约检查报告。"""

    passed: bool
    missing_sections: List[str]
    missing_tasks: List[str]
    issues: List[str]


class PatchAction(BaseModel):
    """单个修补操作。"""

    action_type: Literal["insert_section", "modify_section", "add_content", "replace_content", "delete_content"]
    target_location: str  # 目标位置，如 "after_section: Key context", "section: Method / protocol", "task_id: task_1"
    content: str  # 要插入或替换的内容
    description: str  # 操作描述


class PatchPlan(BaseModel):
    """修补计划。支持增量修补操作。"""

    actions: List[str] = Field(default_factory=list)  # 向后兼容：保留旧的字符串格式
    patch_actions: List[PatchAction] = Field(default_factory=list)  # 新的结构化修补操作
    notes: List[str] = Field(default_factory=list)


class DerivationIntent(BaseModel):
    """证明/推导意图。"""

    proof_heavy: bool
    required_proof_types: List[str] = Field(default_factory=list)
    must_have_artifacts: List[str] = Field(default_factory=list)
    triggers: List[str] = Field(default_factory=list)


class ProofStep(BaseModel):
    """证明步骤骨架。"""

    id: str
    title: str
    goal: str
    proof_type: str
    expected_eqs: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)


class ProofPlan(BaseModel):
    """证明/推导计划。"""

    steps: List[ProofStep]
    notes: List[str] = Field(default_factory=list)


class DerivationBlock(BaseModel):
    """形式化推导块。"""

    id: str
    title: str
    latex: str
    assumptions: List[str] = Field(default_factory=list)
    result: str = ""


class ProofGapReport(BaseModel):
    """证明缺口报告（查缺）。"""

    missing_steps: List[str] = Field(default_factory=list)
    missing_eqs: List[str] = Field(default_factory=list)
    missing_definitions: List[str] = Field(default_factory=list)
    generality_issues: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GeneralityReport(BaseModel):
    """一般性覆盖检查报告。"""

    general_markers: int
    example_markers: int
    ratio: float
    issues: List[str] = Field(default_factory=list)


class MechanismModel(BaseModel):
    """机理推断模型。"""

    inferred_mechanism: List[str] = Field(default_factory=list)
    key_intermediates: List[str] = Field(default_factory=list)
    evidence_mapping: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class PathwayMap(BaseModel):
    """生物题：通路拓扑/因果链结构化表示。"""

    entities: List[str] = Field(default_factory=list)
    edges: List[Dict[str, str]] = Field(
        default_factory=list,
        description=
        'Each edge: {"source": "...", "target": "...", "relation": "activates|inhibits|binds|phosphorylates|unknown"}',
    )
    causal_chain: List[str] = Field(
        default_factory=list,
        description="Explicit directed chain (Signal -> Receptor -> Kinase -> TF -> Gene Expression).",
    )
    epistasis_checks: List[str] = Field(
        default_factory=list,
        description="Explicit epistasis logic checks extracted or proposed based on prompt evidence.",
    )
    assumptions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ComparisonMatrix(BaseModel):
    """试题：对比分析矩阵（维度×对象）。"""

    items: List[str] = Field(default_factory=list, description="Compared items (e.g., A, B, WT, mutant).")
    dimensions: List[str] = Field(default_factory=list, description="Comparison dimensions (e.g., size, color, acidity, bp).")
    cells: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="cells[dimension][item] = statement; keep each cell short and precise.",
    )
    notes: List[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    """封闭式检索任务的输出：只返回原文证据片段与命中的关键词。"""

    snippets: List[str] = Field(default_factory=list, description="Evidence snippets copied from problem_text/text_segments.")
    matched_terms: List[str] = Field(default_factory=list, description="Query terms that matched snippets.")
    notes: List[str] = Field(default_factory=list)


class CritiqueReport(BaseModel):
    """批判性评估报告。"""

    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    hidden_assumptions: List[str] = Field(default_factory=list)
    identified_tradeoffs: List[str] = Field(default_factory=list)
    improvement_suggestions: List[str] = Field(default_factory=list)


class ParameterEstimate(BaseModel):
    """参数估计结果。"""

    target_parameter: str
    formula_used: str

    # 1. 强制第一步：把代入前的值与物理符号显式绑定
    variable_mapping: Dict[str, str] = Field(default_factory=dict,
                                             description="Explicitly map symbols to context values before calculation. "
                                             "Example: {'M_phy': '1634 MeV', 'L_phy': '3.4 fm', 'hbar*c': '197.327 MeV*fm'}. "
                                             "This forces the Agent to show 'what goes where' before computing, "
                                             "preventing jumps directly to final answer.")

    # 2. 约束计算步骤必须包含四则运算展开
    calculation_steps: List[str] = Field(
        default_factory=list,
        description="Must show explicit arithmetic substitution and intermediate results. "
        "Example: ['Step 1: L = 3.4 fm / 0.1973 = 17.23 MeV^-1', "
        "'Step 2: L^2 = (17.23)^2 = 296.87 MeV^-2', "
        "'Step 3: E = 9.8696 / 296.87 = 0.0332 MeV^-1']. "
        "Each arithmetic operation (division, multiplication, squaring) must be a separate step.")

    final_value: float
    final_unit: str
    notes_on_uncertainty: str = ""


class SynthesisReport(BaseModel):
    """综合总结报告。"""

    main_conclusion: str
    key_supporting_findings: List[str] = Field(default_factory=list)
    scientific_implications: str = ""
    recommended_next_steps: List[str] = Field(default_factory=list)


class ResearchDossier(BaseModel):
    """研究工作流总汇。"""

    problem: str = ""
    question_intent: QuestionIntent | Dict[str, Any] | None = None
    context: ContextBrief | Dict[str, Any] | None = None
    task_graph: ResearchTaskGraph | Dict[str, Any] | None = None
    domain_route: DomainRoute | Dict[str, Any] | None = None
    subject_profile: SubjectProfile | Dict[str, Any] | None = None
    director: DirectorDecision | Dict[str, Any] | None = None
    axiom_ledger: AxiomLedger | Dict[str, Any] | None = None
    constraint_ledger: ConstraintLedger | Dict[str, Any] | None = None
    hypotheses: HypothesisPack | Dict[str, Any] | None = None
    rational_selections: List[Dict[str,
                                   Any]] = Field(default_factory=list,
                                                 description="P0: Selected minimal rationales from PromptProximitySelector. "
                                                 "Each entry contains the most prompt-aligned explanation for a subquestion.")
    methods: List[MethodPlan | Dict[str, Any]] = Field(default_factory=list)
    decision: DecisionRecord | Dict[str, Any] | None = None
    verification: VerificationReport | Dict[str, Any] | None = None
    derivation_intent: DerivationIntent | Dict[str, Any] | None = None
    proof_plan: ProofPlan | Dict[str, Any] | None = None
    derivations: List[DerivationBlock | Dict[str, Any]] = Field(default_factory=list)
    proof_gaps: ProofGapReport | Dict[str, Any] | None = None
    task_outputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    payload_views: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Compiled PayloadView reports for OC-HMG/OPC debugging and evaluation.",
    )
    draft: Optional[str] = None
    final: Optional[str] = None

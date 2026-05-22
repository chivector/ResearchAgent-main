from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from smolagents import LiteLLMModel

from sciagent.agents import (
    build_context_miner_agent,
    build_ground_truth_searcher_agent,
    build_comparison_matrix_agent,
    build_critique_agent,
    build_data_analysis_designer_agent,
    build_director_agent,
    build_estimator_agent,
    build_formal_deriver_agent,
    build_axiom_builder_agent,
    build_hypothesis_modeler_agent,
    build_insilico_designer_agent,
    build_mechanism_inferer_agent,
    build_meta_reviewer_agent,
    build_patcher_agent,
    build_pathway_mapping_agent,
    build_proof_auditor_agent,
    build_proof_planner_agent,
    build_prompt_proximity_selector_agent,
    build_question_intent_aligner_agent,
    build_scientific_writer_agent,
    build_synthesizer_agent,
    build_task_graph_builder_agent,
    build_terminology_polisher_agent,
    build_tradeoff_agent,
    build_verification_agent,
    build_wetlab_designer_agent,
)
from sciagent.agents.payload_builder import compile_agent_payload, render_payload_view
from sciagent.memory import ResearchMemory
from sciagent.memory_graph import estimate_token_cost
from sciagent.schemas import ResearchDossier
from sciagent.tools import (
    ArchiveArtifactTool,
    MemorySummaryTool,
    ReadTextFileTool,
    WriteTextFileTool,
    answer_contract_check_tool,
    build_task_graph_tool,
    consistency_lint_tool,
    derivation_intent_tool,
    domain_route_tool,
    generality_guard_tool,
    patch_plan_tool,
    proof_contract_check_tool,
    proof_patch_plan_tool,
    protocol_template_tool,
    task_role_router_tool,
)
from sciagent.utils import read_jsonl_problem, read_text_file


def build_model(model_id: str) -> LiteLLMModel:
    """构建统一的 LiteLLM 模型对象。"""
    return LiteLLMModel(
        model_id=model_id,
        api_key=os.environ.get("API_KEY") or os.environ.get("DF_API_KEY"),
        api_base=os.environ.get("API_BASE") or os.environ.get("DF_API_URL"),
        max_completion_tokens=12000,
        num_retries=2,
        timeout=600,
    )


DEFAULT_AGENT_MODELS = {
    "director": "gpt-5.4",
    "context": "gemini-3-flash-preview",
    "ground_truth_searcher": "claude-opus-4-6",
    "question_intent": "gemini-3.1-pro-preview",
    "task_graph": "gpt-5.4",
    "axiom_builder": "claude-opus-4-6",
    "hypothesis": "gpt-5.4",
    "prompt_proximity_selector": "gemini-3.1-pro-preview",
    "wetlab": "gpt-5.4",
    "insilico": "gpt-5.4",
    "data_analysis": "claude-sonnet-4-6",
    "mechanism_inferer": "claude-opus-4-6",
    "pathway_mapping": "claude-opus-4-6",
    "comparison_matrix": "gemini-3.1-pro-preview",
    "critique": "claude-opus-4-6",
    "estimator": "gpt-5.4",
    "synthesizer": "claude-opus-4-6",
    "tradeoff": "gpt-5.4",
    "verification": "claude-opus-4-6",
    "writer": "gpt-5.4",
    "patcher": "claude-sonnet-4-6",
    "polisher": "gpt-5.4",
    "meta_reviewer": "claude-opus-4-6",
    "proof_planner": "claude-opus-4-6",
    "formal_deriver": "claude-opus-4-6",
    "proof_auditor": "claude-opus-4-6",
}


def _resolve_model_id(agent_key: str, director_model_id: str, model_overrides: Dict[str, str]) -> str:
    """解析 agent 默认模型，沿用 director 的 provider 前缀。"""
    override = model_overrides.get(agent_key)
    if override:
        return override

    base_model = DEFAULT_AGENT_MODELS.get(agent_key, director_model_id)
    if "/" in base_model:
        return base_model

    if "/" in director_model_id:
        provider, _ = director_model_id.split("/", 1)
        return f"{provider}/{base_model}"
    return base_model



def _parse_json_maybe(value: Any):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return value


def _fix_code_block(agent_output: str) -> str:
    r"""
    修复 LLM 输出的代码块格式问题（兜底方案）。

    常见问题：
    1. 代码块未闭合
    2. 代码块外有文本
    3. 多个代码块
    4. LaTeX 转义序列错误（如 \sigma, \tau 未使用 r"..." 前缀）

    返回修复后的输出，如果无法修复则返回原文。
    """
    import re

    if not isinstance(agent_output, str):
        return agent_output

    # 尝试提取第一个完整的代码块
    match = re.search(r'```python\s*(.*?)\s*```', agent_output, re.DOTALL)
    if match:
        code = match.group(1)
        # 修复 LaTeX 转义序列问题
        code = _fix_latex_escapes_in_code(code)
        return f"```python\n{code}\n```"

    # 如果没有找到完整代码块，尝试修复未闭合的代码块
    match = re.search(r'```python\s*(.*)', agent_output, re.DOTALL)
    if match:
        code = match.group(1)
        # 移除代码块后的文本（如果有多余的 ``` 标记）
        code = re.sub(r'```.*$', '', code, flags=re.DOTALL)
        # 移除尾部的不完整思考文本
        code = code.rstrip()
        # 修复 LaTeX 转义序列问题
        code = _fix_latex_escapes_in_code(code)
        return f"```python\n{code}\n```"

    # 如果完全没有代码块标记，返回原文（让 smolagents 报错）
    return agent_output


def _fix_latex_escapes_in_code(code: str) -> str:
    r"""
    修复 Python 代码中的 LaTeX 转义序列问题。

    将包含 LaTeX 符号的普通字符串转换为原始字符串（r"..."）。
    例如: "Define $\\sigma$" -> r"Define $\sigma$"

    这是一个启发式修复，处理常见的 LaTeX 符号。
    """
    import re

    # 常见的 LaTeX 转义序列模式
    latex_patterns = [
        r'\\sigma',
        r'\\tau',
        r'\\alpha',
        r'\\beta',
        r'\\gamma',
        r'\\delta',
        r'\\epsilon',
        r'\\theta',
        r'\\lambda',
        r'\\mu',
        r'\\nu',
        r'\\pi',
        r'\\rho',
        r'\\phi',
        r'\\psi',
        r'\\omega',
        r'\\Sigma',
        r'\\Omega',
        r'\\uparrow',
        r'\\downarrow',
        r'\\leftarrow',
        r'\\rightarrow',
        r'\\langle',
        r'\\rangle',
        r'\\in',
        r'\\subset',
        r'\\cup',
        r'\\cap',
        r'\\sum',
        r'\\prod',
        r'\\int',
        r'\\frac',
        r'\\sqrt',
        r'\\text',
        r'\\hat',
        r'\\bar',
        r'\\vec',
        r'\\dot',
        r'\\ddot',
        r'\\partial',
        r'\\nabla',
        r'\\infty',
        r'\\times',
        r'\\cdot',
    ]

    # 查找所有字符串字面量（包括单引号和双引号）
    # 匹配模式：非原始字符串（不以 r 开头）且包含反斜杠
    def fix_string_literal(match):
        quote = match.group(1)  # ' 或 "
        content = match.group(2)

        # 检查是否包含 LaTeX 转义序列
        has_latex = any(re.search(pattern, content) for pattern in latex_patterns)

        if has_latex:
            # 转换为原始字符串
            # 注意：需要处理内部的引号转义
            if quote == '"':
                # 双引号字符串：保持内部单引号不变，转义双引号
                content_escaped = content.replace('\\', '\\\\').replace('"', '\\"')
                return f'r"{content}"'
            else:
                # 单引号字符串：保持内部双引号不变，转义单引号
                content_escaped = content.replace('\\', '\\\\').replace("'", "\\'")
                return f"r'{content}'"

        # 如果不包含 LaTeX，保持原样
        return match.group(0)

    # 匹配非原始字符串字面量
    # 负向前瞻确保不匹配 r"..." 或 r'...'
    pattern = r'(?<!r)(["\'])((?:[^"\'\\]|\\.)*)(["\'])'

    # 简化版本：只处理明显包含反斜杠的字符串
    # 使用更简单的正则表达式避免复杂的嵌套匹配
    lines = code.split('\n')
    fixed_lines = []

    for line in lines:
        # 跳过已经是原始字符串的行
        if 'r"' in line or "r'" in line:
            fixed_lines.append(line)
            continue

        # 检查是否包含 LaTeX 转义序列
        has_latex = any(pattern in line for pattern in [
            '\\sigma', '\\tau', '\\alpha', '\\beta', '\\gamma', '\\uparrow', '\\downarrow', '\\langle', '\\rangle', '\\in',
            '\\sum', '\\frac', '\\hat', '\\bar'
        ])

        if has_latex:
            # 简单替换：在字符串引号前添加 r
            # 处理双引号字符串
            line = re.sub(r'(?<!r)"([^"]*(?:\\.[^"]*)*)"', r'r"\1"', line)
            # 处理单引号字符串
            line = re.sub(r"(?<!r)'([^']*(?:\\.[^']*)*)'", r"r'\1'", line)

        fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def _safe_agent_json(agent_output: Any, fallback: Any):
    # 先尝试修复格式（如果是字符串）
    if isinstance(agent_output, str):
        agent_output = _fix_code_block(agent_output)

    parsed = _parse_json_maybe(agent_output)
    if isinstance(parsed, dict):
        return parsed
    return fallback


def _safe_agent_list(agent_output: Any, fallback: Any):
    # 先尝试修复格式（如果是字符串）
    if isinstance(agent_output, str):
        agent_output = _fix_code_block(agent_output)

    parsed = _parse_json_maybe(agent_output)
    if isinstance(parsed, list):
        return parsed
    return fallback


def build_tools(memory: ResearchMemory):
    """构建工具集合。"""
    return {
        "read_file": ReadTextFileTool(),
        "write_file": WriteTextFileTool(),
        "archive": ArchiveArtifactTool(memory),
        "memory_summary": MemorySummaryTool(memory),
        "domain_route": domain_route_tool,
        "build_task_graph": build_task_graph_tool,
        "task_role_router": task_role_router_tool,
        "protocol_template": protocol_template_tool,
        "consistency_lint": consistency_lint_tool,
        "answer_contract": answer_contract_check_tool,
        "patch_plan": patch_plan_tool,
        "derivation_intent": derivation_intent_tool,
        "proof_contract": proof_contract_check_tool,
        "generality_guard": generality_guard_tool,
        "proof_patch_plan": proof_patch_plan_tool,
    }


def _merge_gap_reports(primary: Dict, secondary: Dict) -> Dict:
    merged = {
        "missing_steps": sorted(set(primary.get("missing_steps", []) + secondary.get("missing_steps", []))),
        "missing_eqs": sorted(set(primary.get("missing_eqs", []) + secondary.get("missing_eqs", []))),
        "missing_definitions": sorted(set(primary.get("missing_definitions", []) + secondary.get("missing_definitions", []))),
        "generality_issues": sorted(set(primary.get("generality_issues", []) + secondary.get("generality_issues", []))),
        "notes": sorted(set(primary.get("notes", []) + secondary.get("notes", []))),
    }
    return merged


def _compile_payload_for_agent(
    dossier: ResearchDossier,
    agent_role: str,
    runtime_inputs: Dict[str, Any],
    task: Optional[Dict[str, Any]] = None,
    archive_tool: Optional[Any] = None,
    archive_key: str = "",
    legacy_payload_text: str = "",
) -> str:
    payload_view = compile_agent_payload(
        dossier=dossier,
        agent_role=agent_role,
        task=task,
        runtime_inputs=runtime_inputs,
        max_repair_rounds=3,
    )
    rendered_payload = render_payload_view(payload_view)
    report = payload_view.report()
    report["rendered_token_cost"] = estimate_token_cost(rendered_payload)
    if legacy_payload_text:
        legacy_cost = estimate_token_cost(legacy_payload_text)
        report["legacy_token_cost"] = legacy_cost
        report["token_savings_vs_legacy"] = legacy_cost - report["rendered_token_cost"]
        report["token_savings_ratio_vs_legacy"] = (
            round((legacy_cost - report["rendered_token_cost"]) / legacy_cost, 4) if legacy_cost else 0.0
        )
    if not hasattr(dossier, "payload_views") or dossier.payload_views is None:
        dossier.payload_views = []
    dossier.payload_views.append(report)
    if archive_tool is not None:
        key = archive_key or f"{agent_role}_{len(dossier.payload_views)}"
        archive_tool.forward(f"payload_view_{key}", json.dumps(report, ensure_ascii=False))
    return rendered_payload


def _legacy_task_payload_text(
    dossier: ResearchDossier,
    task: Dict[str, Any],
    dependent_outputs: Dict[str, Any],
    derivation_intent: Optional[Any] = None,
    proof_plan: Optional[Any] = None,
    all_prior_task_outputs: Optional[Dict[str, Any]] = None,
) -> str:
    lines = [
        f"problem_text: {dossier.problem}",
        f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}",
        f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}",
        f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}",
        f"task_definition: {json.dumps(task, ensure_ascii=False)}",
    ]
    if task.get("micro_checklists"):
        lines.append(f"MANDATORY_CHECKLIST: {json.dumps(task.get('micro_checklists'), ensure_ascii=False)}")
    if dossier.axiom_ledger:
        lines.append(
            "AXIOM_LEDGER (IMMUTABLE CONSTRAINTS - DO NOT VIOLATE): "
            f"{json.dumps(dossier.axiom_ledger, ensure_ascii=False)}"
        )
    if dossier.constraint_ledger and isinstance(dossier.constraint_ledger, dict):
        pending = [c for c in dossier.constraint_ledger.get("constraints", []) if c.get("status") == "pending"]
        if pending:
            lines.append(
                "CONSTRAINT_LEDGER (MANDATORY - your output MUST address these):\n"
                f"{json.dumps(pending, ensure_ascii=False)}"
            )
    sp = dossier.subject_profile if isinstance(dossier.subject_profile, dict) else {}
    dc = sp.get("derivation_constraints")
    if dc and isinstance(dc, list):
        lines.append("DERIVATION_METHODOLOGY (MANDATORY):\n" + "\n".join(f"- {c}" for c in dc))
    if dossier.hypotheses:
        lines.append(f"hypotheses: {json.dumps(dossier.hypotheses, ensure_ascii=False)}")
    if dossier.derivations:
        lines.append(f"global_derivations: {json.dumps(dossier.derivations, ensure_ascii=False)}")
    lines.append(f"dependent_task_outputs: {json.dumps(dependent_outputs, ensure_ascii=False)}")
    if derivation_intent is not None:
        lines.append(f"derivation_intent: {json.dumps(derivation_intent, ensure_ascii=False)}")
    if proof_plan is not None:
        lines.append(f"proof_plan: {json.dumps(proof_plan, ensure_ascii=False)}")
    if all_prior_task_outputs is not None:
        lines.append(f"all_prior_task_outputs: {json.dumps(all_prior_task_outputs, ensure_ascii=False)}")
    return "\n".join(lines)


def _legacy_writer_payload_text(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _legacy_verification_payload_text(dossier: ResearchDossier, draft: str) -> str:
    return (
        f"problem_text: {dossier.problem}\n"
        f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
        f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}\n"
        f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}\n"
        f"task_graph: {json.dumps(dossier.task_graph, ensure_ascii=False)}\n"
        f"task_outputs: {json.dumps(dossier.task_outputs, ensure_ascii=False)}\n"
        f"draft: {draft}"
    )


def _prepare_writer_payload(dossier: ResearchDossier,
                            patch_plan: Optional[Dict] = None,
                            intermediate_validation: Optional[Dict] = None) -> Dict[str, Any]:
    """
    为 ScientificWriter 准备精简的 payload。

    只包含写作真正需要的信息，排除冗余的中间产物和决策过程。
    相比完整 dossier，减少约 75-85% 的 token 消耗。

    只喂 validated 内容给 Writer，包含 question_intent 作为最高优先级约束。
    """
    context = dossier.context or {}

    # 写作必需的上下文字段（证据锚点、关键词、结构信息）
    essential_context = {
        "subquestions": context.get("subquestions", []),
        "deliverables": context.get("deliverables", []),
        "evidence_mapping": context.get("evidence_mapping", {}),
        "empirical_evidence": context.get("empirical_evidence", []),
        "must_have_terms": context.get("must_have_terms", []),
        "unchanged_features": context.get("unchanged_features", []),
        "core_conflicts": context.get("core_conflicts", []),
        "negative_constraints": context.get("negative_constraints", []),
        "phenotype_summary": context.get("phenotype_summary", {}),
        "reaction_conditions": context.get("reaction_conditions", {}),
        "temporal_context": context.get("temporal_context", []),
        "spatial_context": context.get("spatial_context", []),
    }

    # 可选参考字段（仅在非空时包含）
    optional_context = {}
    for key in ["key_terms", "entities", "given_data", "constraints"]:
        value = context.get(key)
        if value:
            optional_context[key] = value

    # 压缩 task_outputs：移除冗余字段
    compacted_outputs = {}
    for task_id, output in (dossier.task_outputs or {}).items():
        if not isinstance(output, dict):
            compacted_outputs[task_id] = output
            continue

        # 移除已在顶层存在的冗余字段
        redundant_keys = {"context_brief", "domain_route", "subject_profile", "task_definition", "dependent_task_outputs"}
        cleaned = {k: v for k, v in output.items() if k not in redundant_keys}
        compacted_outputs[task_id] = cleaned

    payload = {
        "problem": dossier.problem,
        "essential_context": essential_context,
        "optional_context": optional_context,
        "task_graph": dossier.task_graph,
        "task_outputs": compacted_outputs,
        "subject_profile": dossier.subject_profile,
    }

    # 注入 question_intent 作为 Writer 的最高优先级约束
    if dossier.question_intent:
        payload["question_intent"] = dossier.question_intent

    # 注入中间校准结果，让 Writer 只写 validated 内容
    if intermediate_validation:
        # Provide validated hypotheses (demoted ones only as alternatives)
        payload["validated_hypotheses"] = intermediate_validation.get("validated_hypotheses", [])
        demoted = intermediate_validation.get("demoted_hypotheses", [])
        if demoted:
            payload["demoted_hypotheses_for_alternatives_only"] = demoted
        flagged = intermediate_validation.get("flagged_issues", [])
        if flagged:
            payload["reasoning_alignment_warnings"] = flagged
        # 注入 selected_rationales（最贴题的解释）
        selected_rationales = intermediate_validation.get("selected_rationales", {})
        if selected_rationales:
            payload["selected_rationales"] = selected_rationales
        # Inject unsatisfied constraints so Writer explicitly addresses them
        unsatisfied = intermediate_validation.get("unsatisfied_constraints", [])
        if unsatisfied:
            payload["unsatisfied_constraints"] = unsatisfied

    # 将推导块暴露给 Writer（修复数据流断裂）
    # 如果没有这段，Writer 看不到 FormalDeriver 推导的公式，会导致幻觉或跳过推导
    if dossier.proof_plan:
        payload["proof_plan"] = dossier.proof_plan
    if dossier.derivations:
        payload["derivations"] = dossier.derivations

    # Inject constraint ledger so Writer can address all mandatory constraints
    if dossier.constraint_ledger:
        payload["constraint_ledger"] = dossier.constraint_ledger

    if patch_plan:
        payload["patch_plan"] = patch_plan

    return payload


def _call_writer(writer_agent,
                 dossier: ResearchDossier,
                 patch_plan: Optional[Dict] = None,
                 intermediate_validation: Optional[Dict] = None,
                 archive_tool: Optional[Any] = None) -> str:
    """
    调用写作代理生成草稿
    """
    payload = _prepare_writer_payload(dossier, patch_plan, intermediate_validation)
    compiled_payload = _compile_payload_for_agent(
        dossier=dossier,
        agent_role="writer",
        runtime_inputs=payload,
        task=None,
        archive_tool=archive_tool,
        archive_key=f"writer_{len(getattr(dossier, 'payload_views', [])) + 1}",
        legacy_payload_text=_legacy_writer_payload_text(payload),
    )

    prompt = (
        "Write the scientific response strictly following the provided dossier.\n"
        "The dossier contains COMPILED_PAYLOAD_VIEW: a compact OC-HMG/OPC view with task contract, "
        "problem kernel, supported evidence/claims, derivations, warnings, and compact runtime inputs when needed.\n"
        "Treat task_contract and problem_kernel as mandatory. Use only allowed_claims, evidence, derivations, "
        "validated_hypotheses, selected_rationales, and task outputs for main claims. Warnings and demoted hypotheses "
        "may only be used as caveats or rejected alternatives.\n"
        "\n"
        "CRITICAL INSTRUCTION: For each subquestion, if selected_rationales contains an entry, USE THAT RATIONALE as the primary answer.\n"
        "It was selected because it stays closest to the prompt and requires fewest external assumptions.\n"
        "Do NOT replace it with a more sophisticated explanation unless explicitly required by the question.\n"
        "\n"
        "DERIVATION METHODOLOGY: If subject_profile contains derivation_constraints, you MUST follow them.\n"
        "Key rules: (1) Show cofactor tallies (NADH, FADH2, GTP) at each step BEFORE computing ATP totals. "
        "(2) Derive each subquestion independently — do NOT compute one answer and adjust for others. "
        "(3) For metabolic cycles, count only standard pathway steps — do not drain catalytic intermediates out of cycles.\n"
        f"\nDossier: {compiled_payload}")

    response = writer_agent.run(prompt)
    return str(response)


def _apply_patch_plan_deterministic(current_draft: str, patch_plan: Dict) -> str:
    """
    Deterministically apply PatchPlan.patch_actions to a draft without using an LLM.

    This is a safety fallback for cases where CodeAgent-generated patch code is syntactically invalid
    (most commonly due to unescaped newlines inside quoted strings).
    """
    import re

    text = current_draft or ""
    patch_actions = patch_plan.get("patch_actions", []) or []

    def insert_at_beginning(t: str, c: str) -> str:
        return (c.rstrip() + "\n\n" + t) if c else t

    def insert_at_end(t: str, c: str) -> str:
        return (t.rstrip() + "\n\n" + c) if c else t

    def insert_after_heading_line(t: str, heading_line: str, c: str) -> str:
        """Insert content right after a specific heading line if found; otherwise append at end."""
        if not c:
            return t
        # Match exact heading line on its own line.
        pattern = r"(^" + re.escape(heading_line) + r"\s*$)"
        m = re.search(pattern, t, flags=re.MULTILINE)
        if not m:
            return insert_at_end(t, c)
        # Insert after the heading line (after its line break)
        insert_pos = t.find("\n", m.end())
        if insert_pos == -1:
            insert_pos = len(t)
            suffix = ""
        else:
            insert_pos = insert_pos + 1
            suffix = t[insert_pos:]
        prefix = t[:insert_pos]
        return prefix + c.rstrip() + "\n\n" + suffix

    def insert_into_component(t: str, component_id: str, c: str) -> str:
        """
        Best-effort: map component_id like 'Q1' -> heading starting with '## 1.'.
        If not found, append at end with a marker.
        """
        if not c:
            return t
        cid = (component_id or "").strip()
        if cid.lower() == "draft":
            return insert_at_end(t, c)
        m = re.fullmatch(r"Q(\d+)", cid, flags=re.IGNORECASE)
        if m:
            n = m.group(1)
            # Try common heading formats: "## 1." or "## 1 " (writer uses subquestion headings)
            for pat in (rf"^##\s*{n}\.\s+.*$", rf"^##\s*{n}\s+.*$"):
                hm = re.search(pat, t, flags=re.MULTILINE)
                if hm:
                    heading_line = hm.group(0)
                    return insert_after_heading_line(t, heading_line, c)
        # Fallback: append with marker so content isn't lost
        return insert_at_end(t, f"<!-- component_id: {cid} -->\n{c}")

    for action in patch_actions:
        action_type = (action.get("action_type") or "").strip()
        target = (action.get("target_location") or "").strip()
        content = action.get("content") or ""

        if action_type in ("insert_section", "add_content", "modify_section", "replace_content"):
            if target == "at_beginning":
                text = insert_at_beginning(text, content)
            elif target == "at_end":
                text = insert_at_end(text, content)
            elif target.startswith("after_section:"):
                section_name = target.split("after_section:", 1)[1].strip()
                heading_line = f"## {section_name}"
                text = insert_after_heading_line(text, heading_line, content)
            elif target.startswith("component_id:"):
                cid = target.split("component_id:", 1)[1].strip()
                text = insert_into_component(text, cid, content)
            elif target.startswith("task_id:"):
                tid = target.split("task_id:", 1)[1].strip()
                text = insert_at_end(text, f"<!-- task_id: {tid} -->\n{content}")
            else:
                text = insert_at_end(text, content)
        elif action_type == "delete_content":
            # Conservative: do nothing (avoid accidental deletion without exact anchors)
            continue

    return text


def _build_text_segments(problem_text: str, max_segments: int = 12, max_len: int = 300) -> Dict[str, str]:
    """Split long problem_text into short single-line excerpts for retrieval."""
    raw = (problem_text or "").strip()
    if not raw:
        return {}
    # Prefer paragraph split; fall back to line split.
    chunks = [c.strip() for c in raw.split("\n\n") if c.strip()]
    if len(chunks) <= 1:
        chunks = [c.strip() for c in raw.splitlines() if c.strip()]
    segments: Dict[str, str] = {}
    for i, chunk in enumerate(chunks[:max_segments], start=1):
        one_line = " ".join(chunk.split())
        segments[f"p{i}"] = one_line[:max_len]
    return segments


def _retrieve_evidence_snippets(problem_text: str, context: Dict, query: str, k: int = 6) -> Dict[str, Any]:
    """Deterministically retrieve top-k evidence snippets from prompt text/segments given a query."""
    import re

    q = (query or "").strip()
    # Candidate pool
    candidates: List[str] = []
    candidates.extend([str(x) for x in (context.get("empirical_evidence") or []) if str(x).strip()])
    for v in (context.get("text_segments") or {}).values():
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())

    # Add sentence-level candidates from full problem text (cap to keep fast)
    raw = (problem_text or "").strip()
    if raw:
        raw_one = " ".join(raw.split())
        sents = re.split(r"(?<=[.!?])\s+|(?<=[。！？])", raw_one)
        for s in sents[:80]:
            s = s.strip()
            if s:
                candidates.append(s)

    # Build query terms (English tokens + entities)
    terms: List[str] = []
    terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_\\-]{2,}", q))
    for ent in (context.get("entities") or []):
        if isinstance(ent, str) and ent.strip():
            terms.append(ent.strip())
    # De-dup + normalize
    norm_terms: List[str] = []
    seen = set()
    for t in terms:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            norm_terms.append(tl)

    def score(text: str) -> int:
        tlow = text.lower()
        return sum(1 for t in norm_terms if t and t in tlow)

    ranked = sorted(((score(c), c) for c in candidates), key=lambda x: x[0], reverse=True)
    snippets: List[str] = []
    for sc, c in ranked:
        if sc <= 0:
            continue
        if c in snippets:
            continue
        snippets.append(c)
        if len(snippets) >= k:
            break

    return {"snippets": snippets, "matched_terms": norm_terms[:20], "notes": [f"retrieved={len(snippets)}", f"query={q[:120]}"]}


def _infer_unchanged_features(problem_text: str, negative_constraints: List[str]) -> List[str]:
    """
    Best-effort extraction of 'unchanged/unaffected/normal/intact' subjects as noun phrases.
    This is intentionally conservative: it tries to capture the feature name without inventing content.
    """
    import re

    feats: List[str] = []

    def _add(x: str):
        x = " ".join((x or "").split()).strip(" .;,:")
        if not x:
            return
        # avoid overly long captures
        if len(x) > 80:
            return
        if x not in feats:
            feats.append(x)

    # Candidate sentences: from negative_constraints + problem_text sentence split
    candidates: List[str] = []
    candidates.extend([str(x) for x in (negative_constraints or []) if str(x).strip()])
    raw = " ".join((problem_text or "").split())
    if raw:
        candidates.extend([s.strip() for s in re.split(r"(?<=[.!?])\s+|(?<=[。！？])", raw) if s.strip()])

    # Patterns capturing the *subject* that is unchanged/unaffected.
    patterns = [
        r"^(?P<subj>.+?)\s+(?:is|was|were|are)\s+(?:unaffected|unchanged|normal|intact)\b",
        r"^(?P<subj>.+?)\s+(?:remains|remained)\s+(?:unaffected|unchanged|normal|intact)\b",
        r"^(?P<subj>.+?)\s+showed\s+no\s+(?:effect|change|difference)\b",
        r"^(?P<subj>.+?)\s+(?:did\s+not|does\s+not)\s+(?:change|affect)\b",
        r"^no\s+(?:effect|change)\s+on\s+(?P<subj>.+?)\b",
        r"^(?P<subj>.+?)\s+is\s+not\s+affected\b",
    ]

    for sent in candidates:
        s = " ".join(str(sent).split()).strip()
        if not s:
            continue
        for pat in patterns:
            m = re.search(pat, s, flags=re.IGNORECASE)
            if not m:
                continue
            subj = m.groupdict().get("subj", "") or ""
            # Strip leading determiners / clutter
            subj = re.sub(r"^(the|a|an|in|for|of)\s+", "", subj.strip(), flags=re.IGNORECASE)
            # Heuristic: keep last 1-5 words if the capture is too broad
            words = subj.split()
            if len(words) > 6:
                subj = " ".join(words[-6:])
            _add(subj)
            break

    return feats[:20]


def _infer_must_have_terms(problem_text: str, context: Dict) -> List[str]:
    """
    Best-effort extraction of rubric-sensitive surface-form terms.
    Priority:
    1) Multi-word/Hyphen terms from entities/key_terms that appear in the problem_text.
    2) Italic gene symbols like *waslb* (kept with asterisks if present).
    3) Capitalized multi-word phrases (conservative).
    """
    import re

    raw = (problem_text or "")
    if not raw.strip():
        return []

    terms: List[str] = []

    def _add(t: str):
        t = " ".join((t or "").split()).strip()
        if not t:
            return
        if len(t) > 60:
            return
        if t not in terms:
            terms.append(t)

    # 1) From context entities/key_terms (surface-form match)
    pool = []
    pool.extend([str(x) for x in (context.get("entities") or []) if isinstance(x, str)])
    pool.extend([str(x) for x in (context.get("key_terms") or []) if isinstance(x, str)])
    for t in pool:
        t = t.strip()
        if not t:
            continue
        if (" " in t) or ("-" in t) or ("_" in t):
            if t in raw:
                _add(t)

    # 2) Italic gene symbols in markdown like *waslb*
    for m in re.finditer(r"\*[A-Za-z0-9_\\-]{2,}\*", raw):
        _add(m.group(0))

    # 3) Capitalized multi-word phrases (very conservative, avoid sentence-start artifacts)
    one_line = " ".join(raw.split())
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[a-z]+)?\s+[a-z]{3,})\b", one_line):
        cand = m.group(1)
        # Filter obvious non-terms
        if cand.lower().startswith(("this ", "that ", "these ", "those ")):
            continue
        if cand in raw:
            _add(cand)

    return terms[:25]


def _infer_phenotype_summary(context: Dict) -> Dict[str, Any]:
    """Infer phenotype_summary from explicit evidence only (best-effort)."""
    ev = [str(x) for x in (context.get("empirical_evidence") or []) if str(x).strip()]
    neg = [str(x) for x in (context.get("negative_constraints") or []) if str(x).strip()]
    text = " ".join((" ".join(ev + neg)).split()).lower()

    viability = "unknown"
    if any(k in text for k in ["embryonic lethal", "embryonically lethal", "lethal", "non-viable", "nonviable"]):
        viability = "lethal"
    elif any(k in text for k in ["viable", "survived", "survival", "live-born", "alive"]):
        viability = "viable"
    elif any(k in text for k in ["sublethal", "sub-lethal", "partially lethal"]):
        viability = "sub-lethal"

    # Morphology: keep explicit phenotype phrases if present; do NOT infer.
    morphology: List[str] = []
    for s in ev:
        sl = s.lower()
        if any(k in sl for k in [
                "defect", "malformation", "abnormal", "changed", "expanded", "reduced", "loss", "gain", "radial", "fin", "limb",
                "joint", "skeletal"
        ]):
            morphology.append(" ".join(s.split())[:160])
        if len(morphology) >= 15:
            break

    return {"viability": viability, "morphology": morphology, "notes": []}


def _enrich_context_for_exam(problem_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic post-processing to reduce 'micro-fact hallucinations':
    - Fill missing evidence_mapping by retrieving best snippet per subquestion.
    - Fill missing unchanged_features / must_have_terms / phenotype_summary.
    """
    if not isinstance(context, dict):
        return context

    # Ensure keys exist
    context.setdefault("evidence_mapping", {})
    context.setdefault("unchanged_features", [])
    context.setdefault("must_have_terms", [])
    context.setdefault("phenotype_summary", {"viability": "unknown", "morphology": [], "notes": []})
    context.setdefault("reaction_tuples", [])

    # evidence_mapping: retrieve one best snippet per subquestion (or main)
    if not context.get("evidence_mapping"):
        mapping: Dict[str, str] = {}
        subs = context.get("subquestions") or []
        if isinstance(subs, list) and subs:
            for sq in subs[:10]:
                q = str(sq).strip()
                if not q:
                    continue
                ret = _retrieve_evidence_snippets(problem_text, context, q, k=3)
                snippets = ret.get("snippets") or []
                if snippets:
                    mapping[q] = str(snippets[0])
        else:
            ret = _retrieve_evidence_snippets(problem_text, context, "main", k=3)
            snippets = ret.get("snippets") or []
            if snippets:
                mapping["main"] = str(snippets[0])
        context["evidence_mapping"] = mapping

    # unchanged_features
    if not context.get("unchanged_features"):
        context["unchanged_features"] = _infer_unchanged_features(problem_text, context.get("negative_constraints") or [])

    # must_have_terms
    if not context.get("must_have_terms"):
        context["must_have_terms"] = _infer_must_have_terms(problem_text, context)

    # phenotype_summary
    ps = context.get("phenotype_summary")
    if not isinstance(ps, dict) or not ps.get("viability"):
        context["phenotype_summary"] = _infer_phenotype_summary(context)

    return context


# Signal phrases in problem text → (constraint_type, verification_strategy)
_CONSTRAINT_SIGNAL_PHRASES = {
    "show all relevant steps": ("format", "section_presence"),
    "show all steps": ("format", "section_presence"),
    "include all intermediate": ("deliverable", "keyword_presence"),
    "all intermediate": ("deliverable", "keyword_presence"),
    "list all": ("deliverable", "keyword_presence"),
    "step by step": ("format", "section_presence"),
    "step-by-step": ("format", "section_presence"),
    "show your work": ("format", "section_presence"),
    "show work": ("format", "section_presence"),
    "how many": ("deliverable", "count_check"),
    "calculate each": ("deliverable", "keyword_presence"),
    "for each": ("deliverable", "keyword_presence"),
    "enumerate": ("deliverable", "keyword_presence"),
    "detailed derivation": ("format", "section_presence"),
    "include all": ("deliverable", "keyword_presence"),
    "derive both": ("format", "section_presence"),
    "compare": ("deliverable", "keyword_presence"),
}


def _extract_constraint_ledger(problem_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic extraction of verifiable constraints from problem text and ContextBrief.

    Called as post-processing after ContextMiner, before any downstream agent.
    Modeled after _infer_unchanged_features / _infer_must_have_terms.

    Returns a ConstraintLedger dict (not a Pydantic object, for JSON compatibility).
    """
    import re

    constraints: List[Dict[str, Any]] = []
    seen_texts: set = set()
    counter = 0

    def _add(ctype: str, text: str, keywords: List[str], strategy: str, source: str = "problem_text"):
        nonlocal counter
        text_norm = " ".join(text.split()).strip()
        if not text_norm or text_norm in seen_texts:
            return
        seen_texts.add(text_norm)
        counter += 1
        constraints.append({
            "id": f"c_{counter}",
            "constraint_type": ctype,
            "text": text_norm,
            "source": source,
            "keywords": [k for k in keywords if k],
            "verification_strategy": strategy,
            "satisfied_by": [],
            "status": "pending",
        })

    lowered = (problem_text or "").lower()

    # 1) Scan problem_text for signal phrases
    for phrase, (ctype, strategy) in _CONSTRAINT_SIGNAL_PHRASES.items():
        if phrase in lowered:
            _add(ctype, f"Problem requires: \"{phrase}\"", [phrase], strategy, "problem_text")

    # 2) Mine context["constraints"] and context["deliverables"]
    for field_name in ("constraints", "deliverables"):
        items = context.get(field_name) or []
        if not isinstance(items, list):
            continue
        for item in items:
            item_str = str(item).strip()
            if not item_str:
                continue
            item_lower = item_str.lower()

            # Classify the constraint
            ctype = "deliverable"
            strategy = "keyword_presence"
            if any(k in item_lower for k in ["show all", "list all", "include all", "enumerate"]):
                ctype = "deliverable"
            elif any(k in item_lower for k in ["step by step", "derivation", "show your work", "derive"]):
                ctype = "format"
                strategy = "section_presence"
            elif any(k in item_lower for k in ["only", "do not", "exclude", "ignore", "without"]):
                ctype = "scope"
            elif any(k in item_lower for k in ["calculate", "compute", "value of", "how many", "how much"]):
                ctype = "deliverable"
                strategy = "count_check"

            # Extract potential keywords from the item (entities, capitalized terms, quoted terms)
            keywords = []
            # Quoted terms
            for m in re.finditer(r'["\']([^"\']+)["\']', item_str):
                keywords.append(m.group(1).strip())
            # Terms that look like chemical formulas or specific entities (e.g., FADH2, NADH, ATP)
            for m in re.finditer(r'\b[A-Z][A-Za-z0-9_]{1,}(?:[-_][A-Za-z0-9]+)*\b', item_str):
                term = m.group(0)
                # Filter common English words
                if term.lower() not in {
                        "the", "and", "for", "with", "from", "that", "this", "show", "all", "list", "include", "each",
                        "calculate", "compute", "derive", "step", "steps", "value", "how", "many", "much"
                }:
                    keywords.append(term)

            _add(ctype, item_str, keywords, strategy, f"context.{field_name}")

    # 3) Mine context["must_have_terms"] → content constraints
    for term in (context.get("must_have_terms") or []):
        term_str = str(term).strip()
        if term_str:
            _add("content", f"Must include term: {term_str}", [term_str], "keyword_presence", "context.must_have_terms")

    # 4) Mine context["negative_constraints"] → scope constraints
    for neg in (context.get("negative_constraints") or []):
        neg_str = str(neg).strip()
        if neg_str:
            _add("scope", neg_str, [], "keyword_presence", "context.negative_constraints")

    # 5) Auto-detect metabolic/energy derivation problems → require cofactor tallies
    # Generalizable: any problem asking to "derive/calculate ATP" should list intermediate cofactors
    deliverables_text = " ".join(str(d) for d in (context.get("deliverables") or []))
    combined_lower = (lowered + " " + deliverables_text).lower()
    is_energy_derivation = any(kw in combined_lower for kw in [
        "atp",
        "gtp",
        "nadh",
        "fadh",
        "energy yield",
        "oxidation",
        "glycolysis",
        "beta-oxidation",
        "tca cycle",
        "krebs cycle",
        "oxidative phosphorylation",
        "metabolic yield",
    ])
    has_derivation_request = any(kw in combined_lower for kw in [
        "derive",
        "calculate",
        "show all",
        "step by step",
        "how many",
    ])

    return {
        "constraints": constraints,
        "last_validated_at": "extraction",
    }


def _enrich_constraints_from_intent(
    constraint_ledger: Dict[str, Any],
    question_intent: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Enrich the ConstraintLedger with scope constraints from QuestionIntent.

    Adds forbidden_expansions and do_not_assume items as scope constraints.
    Called after QuestionIntentAligner runs.
    """
    if not isinstance(constraint_ledger, dict) or not isinstance(question_intent, dict):
        return constraint_ledger or {"constraints": [], "last_validated_at": ""}

    constraints = constraint_ledger.get("constraints", [])
    seen = {c.get("text", "") for c in constraints}
    counter = len(constraints)

    # forbidden_expansions → scope constraints
    for exp in (question_intent.get("forbidden_expansions") or []):
        exp_str = str(exp).strip()
        if exp_str and exp_str not in seen:
            counter += 1
            constraints.append({
                "id": f"c_{counter}",
                "constraint_type": "scope",
                "text": f"Forbidden expansion: {exp_str}",
                "source": "question_intent.forbidden_expansions",
                "keywords": [],
                "verification_strategy": "keyword_presence",
                "satisfied_by": [],
                "status": "pending",
            })
            seen.add(exp_str)

    # do_not_assume from each subquestion_intent → scope constraints
    for sub_intent in (question_intent.get("subquestion_intents") or []):
        if not isinstance(sub_intent, dict):
            continue
        for dna in (sub_intent.get("do_not_assume") or []):
            dna_str = str(dna).strip()
            if dna_str and dna_str not in seen:
                counter += 1
                constraints.append({
                    "id": f"c_{counter}",
                    "constraint_type": "scope",
                    "text": f"Do not assume: {dna_str}",
                    "source": "question_intent.do_not_assume",
                    "keywords": [],
                    "verification_strategy": "llm_required",
                    "satisfied_by": [],
                    "status": "deferred",
                })
                seen.add(dna_str)

    constraint_ledger["constraints"] = constraints
    constraint_ledger["last_validated_at"] = "question_intent_enrichment"
    return constraint_ledger


def _append_deterministic_exam_checks(problem_text: str, context: Dict[str, Any], draft: str,
                                      verification: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic (non-LLM) exam checks:
    - evidence_mapping quotes must appear verbatim in draft
    - must_have_terms must appear verbatim in draft
    - unchanged_features must not be described with change verbs
    - lethality must be stated if explicitly marked
    """
    import re

    if not isinstance(verification, dict):
        verification = {"issues": [], "notes": []}
    issues = verification.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    notes = verification.get("notes") or []
    if not isinstance(notes, list):
        notes = []

    def _add_issue(issue_id: str, severity: str, message: str, suggestion: str, affected: str = "draft"):
        issues.append({
            "id": issue_id,
            "severity": severity,
            "message": message,
            "suggestion": suggestion,
            "affected_component_id": affected,
        })

    d = draft or ""
    d_norm = " ".join(d.split())

    # 1) Evidence quote presence
    em = context.get("evidence_mapping") or {}
    if isinstance(em, dict):
        for i, (k, quote) in enumerate(list(em.items())[:10], start=1):
            q = str(quote or "").strip()
            if not q:
                continue
            # Allow harmless whitespace normalization differences while still enforcing surface-form copying.
            q_norm = " ".join(q.split())
            if q_norm and q_norm not in d_norm:
                _add_issue(
                    f"evidence_quote_missing_{i}",
                    "high",
                    f"Draft missing required verbatim evidence quote for key='{str(k)[:60]}': \"{q[:160]}\"",
                    f"Insert the exact quote verbatim (e.g., `Evidence (verbatim): \"{q}\"`) in the relevant sub-answer, then restate the supported conclusion without paraphrasing the quote.",
                )

    # 2) Must-have term hit-rate
    mht = context.get("must_have_terms") or []
    if isinstance(mht, list) and mht:
        missing = []
        for t in mht[:25]:
            ts = str(t).strip()
            if ts and ts not in d:
                missing.append(ts)
        if missing:
            _add_issue(
                "must_have_terms_missing",
                "medium",
                f"Draft missing rubric-sensitive terms (verbatim): {', '.join(missing[:10])}",
                "Add the missing terms verbatim (exact surface form) in the relevant section(s); avoid paraphrasing specialized anatomy/chemistry keywords.",
            )

    # 3) Hallucinated growth on unchanged features
    change_verbs = [
        "expanded",
        "thickened",
        "increased",
        "decreased",
        "altered",
        "affected",
        "changed",
        "reduced",
        "enhanced",
        "stabilized",
        "destabilized",
        "elongated",
        "shortened",
        # common bio phrasing
        "upregulated",
        "downregulated",
    ]
    uf = context.get("unchanged_features") or []
    if isinstance(uf, list) and uf:
        # Sentence split (English/Chinese punctuation)
        sentences = re.split(r"(?<=[.!?])\s+|(?<=[。！？])", " ".join(d.split()))
        for j, feat in enumerate(uf[:20], start=1):
            f = str(feat).strip()
            if not f:
                continue
            for sent in sentences:
                if f.lower() in sent.lower():
                    sl = sent.lower()
                    if any(v in sl for v in change_verbs):
                        _add_issue(
                            f"unchanged_feature_violated_{j}",
                            "high",
                            f"Draft describes change for an explicitly unchanged feature '{f}'. Offending sentence: \"{sent[:220]}\"",
                            f"Replace the change claim with an explicit unchanged statement (e.g., \"{f} is unaffected/unchanged\"), consistent with ContextBrief.unchanged_features/negative_constraints.",
                        )
                    break

    # 4) Viability priority (lethal)
    ps = context.get("phenotype_summary") or {}
    if isinstance(ps, dict) and ps.get("viability") == "lethal":
        if re.search(r"\blethal\b", d, flags=re.IGNORECASE) is None and re.search(r"致死|胚胎致死", d) is None:
            _add_issue(
                "viability_lethal_missing",
                "high",
                "Context indicates lethality, but draft does not explicitly state lethality.",
                "State lethality as the primary conclusion (e.g., 'embryonically lethal' / '致死'), and avoid substituting it with morphology-only descriptions unless explicitly stated in evidence.",
            )

    verification["issues"] = issues
    verification["notes"] = notes + ["deterministic_exam_checks_applied=true"]
    return verification


def _call_patcher(patcher_agent, current_draft: str, patch_plan: Dict) -> str:
    """
    调用修补代理进行增量修补。
    """
    patch_actions = patch_plan.get("patch_actions", [])
    if not patch_actions:
        # 如果没有结构化修补操作，返回原草稿（将回退到完全重写）
        return current_draft

    # 检查是否含有必须要替换或修改的操作
    # 如果有，不能用确定性修补（因为 insert_into_component 只追加不替换）
    has_complex_action = any(
        a.get("action_type") in ("modify_section", "replace_content", "delete_content") for a in patch_actions)

    if not has_complex_action:
        # 只有简单的 insert_section/add_content 操作，可以用确定性修补
        try:
            return _apply_patch_plan_deterministic(current_draft, patch_plan)
        except Exception:
            # 确定性修补失败，回退到 LLM Patcher
            pass

    # 对于复杂操作（replace/modify/delete），直接使用 LLM Patcher
    prompt = (
        "Apply incremental patches to `current_draft` according to `patch_plan`.\n"
        "CRITICAL: For 'replace_content' or 'modify_section', you MUST REMOVE the old incorrect text and substitute the new one.\n"
        "Do NOT just append. Find the target text and replace it.\n"
        "Hard rules: do NOT rewrite the whole document; apply minimal edits only.\n"
        "Use the provided Python variables `current_draft` (str) and `patch_plan` (dict).")

    try:
        response = patcher_agent.run(prompt, additional_args={"current_draft": current_draft, "patch_plan": patch_plan})
        return str(response)
    except Exception as e:
        # 捕获所有异常（包括语法错误），让上层回退到完全重写
        # 语法错误通常是因为文档内容包含三引号导致字符串提前终止
        error_msg = str(e)
        if "triple-quoted" in error_msg.lower() or "unterminated" in error_msg.lower():
            # 这是三引号相关的语法错误，提供更清晰的错误信息
            raise RuntimeError(f"PatcherAgent failed due to syntax error (likely triple quotes in content): {error_msg}\n"
                               f"Falling back to full rewrite.") from e
        else:
            # 其他错误
            raise RuntimeError(f"PatcherAgent execution failed: {error_msg}") from e


def _filter_axiom_ledger(axiom_ledger: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """过滤 AxiomLedger 中的解释性公理和 violation_checks。

    如果某条 axiom/violation_check 包含强解释性语言（如 "must discuss", "must address",
    "must be due to", "requires X mechanism", "necessarily implies"）但在题干证据中找不到对应表述，
    就把它降级到 soft_interpretations 或删除。
    """
    import re

    if not isinstance(axiom_ledger, dict):
        return axiom_ledger

    # 处理所有可能包含解释性内容的字段
    fields_to_filter = [
        ("biological_axioms", "biological_axioms"),
        ("chemical_axioms", "chemical_axioms"),
        ("explicit_protocol_facts", "explicit_protocol_facts"),
        ("violation_checks", "violation_checks"),
    ]

    soft_interpretations = axiom_ledger.get("soft_interpretations", [])
    if not isinstance(soft_interpretations, list):
        soft_interpretations = []

    # Collect evidence text for matching
    evidence_pool = ""
    if isinstance(context, dict):
        for ev in (context.get("empirical_evidence") or []):
            evidence_pool += " " + str(ev)
        for seg in (context.get("text_segments") or {}).values():
            evidence_pool += " " + str(seg)
        for uf in (context.get("unchanged_features") or []):
            evidence_pool += " " + str(uf)
        for nc in (context.get("negative_constraints") or []):
            evidence_pool += " " + str(nc)
        # 也检查 reaction_conditions
        rc = context.get("reaction_conditions", {})
        if isinstance(rc, dict):
            for k, v in rc.items():
                evidence_pool += f" {k}: {v}"
    evidence_lower = evidence_pool.lower()

    # 扩展解释性模式列表
    # 策略：如果匹配任何解释性模式，默认标记为解释性，除非整个语句在证据中
    explanatory_patterns = [
        # 原有模式
        r"\bmust\s+discuss\b",
        r"\bmust\s+address\b",
        r"\bmust\s+consider\b",
        r"\bmust\s+mention\b",
        r"\bmust\s+include.*(?:mechanism|pathway|effect|analysis|discussion)\b",
        r"\bshould\s+discuss\b",
        r"\bshould\s+address\b",
        # （解释性因果/要求）
        r"\b(?:must\s+be|is)\s+due\s+to\b",
        r"\brequires?\s+\w+\s+(?:mechanism|for|to)\b",
        r"\bnecessarily\s+implies?\b",
        r"\bprimary\s+bottleneck\s+is\b",
        r"\bmain\s+reason\s+is\b",
        r"\bmust\s+be\s+in\s+\w+\s+(?:form|state)\s+for\b",  # "must be in free acid form for"
        r"\brequired\s+for\s+(?:activation|coupling|reaction|stability|optimal)\b",
        r"\bneeded\s+for\s+(?:optimal|efficient)\b",
        r"\bmust\s+be\s+adjusted\s+(?:to|for)\s+\w+\s+for\b",  # "must be adjusted to X for Y"
        r"\bactivation\s+requires\b",
        r"\bcoupling\s+requires\b",
    ]

    for field_name, schema_key in fields_to_filter:
        field_content = axiom_ledger.get(field_name, [])
        if not isinstance(field_content, list):
            continue

        filtered_content = []
        for item in field_content:
            item_str = str(item).strip()
            if not item_str:
                continue

            is_explanatory = False
            matched_pattern = None

            for pat in explanatory_patterns:
                if re.search(pat, item_str, flags=re.IGNORECASE):
                    # 强化策略：如果匹配解释性模式，默认标记为解释性
                    is_explanatory = True

                    # 关键规则：如果包含 "for X" 后缀（表示目的/原因），一律降级
                    # 例如："must be in X form for Y", "adjusted to X for Y"
                    if re.search(r"\s+for\s+\w+", item_str, flags=re.IGNORECASE):
                        is_explanatory = True
                        break

                    # 如果不包含 "for"，检查是否包含其他解释性词汇
                    if re.search(r"\b(?:requires?|needed|due to|activation|coupling|stability|mechanism|bottleneck|reason)\b",
                                 item_str,
                                 flags=re.IGNORECASE):
                        is_explanatory = True
                        break

                    # 如果都不包含，可能是误判，检查是否在证据中
                    item_lower = item_str.lower()
                    if item_lower in evidence_lower or any(
                            item_lower in ev.lower() for ev in [str(x) for x in (context.get("empirical_evidence") or [])]):
                        is_explanatory = False

                    break

            if is_explanatory:
                # 降级到 soft_interpretations
                soft_interpretations.append(f"[demoted from {field_name}] {item_str}")
            else:
                filtered_content.append(item_str)

        axiom_ledger[field_name] = filtered_content

    axiom_ledger["soft_interpretations"] = soft_interpretations
    return axiom_ledger


def _verify_intermediate_reasoning(
    question_intent: Dict[str, Any],
    task_outputs: Dict[str, Dict[str, Any]],
    hypotheses: Dict[str, Any],
    rational_selections: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """pre-writer 中间校准器（使用 rational_selections）。

    在 Writer 之前检查：
    1. task_outputs 是否围绕题意
    2. hypotheses 是否超出题干支持范围
    3. 是否把推测写成了结论
    4. 优先使用 rational_selections 中选出的最贴题解释

    返回一个 validation_report，包含 validated_hypotheses 和 flagged_issues。
    """
    import re

    report = {
        "validated_hypotheses": [],
        "demoted_hypotheses": [],
        "flagged_issues": [],
        "validated_task_outputs": {},
        "selected_rationales": {},  # 新增：每个子问题的最贴题解释
    }

    # 优先使用 PromptProximitySelector 的选择结果
    if isinstance(rational_selections, list):
        for selection in rational_selections:
            if isinstance(selection, dict):
                subq_id = selection.get("subquestion_id", "")
                selected = selection.get("selected_rationale", "")
                if subq_id and selected:
                    report["selected_rationales"][subq_id] = {
                        "rationale": selected,
                        "reason": selection.get("selection_reason", ""),
                        "prompt_distance": selection.get("prompt_distance_score", 0),
                        "scope_alignment": selection.get("answer_scope_alignment", ""),
                    }

    if not isinstance(question_intent, dict):
        # No question_intent available, pass everything through
        report["validated_hypotheses"] = (hypotheses or {}).get("hypotheses", [])
        report["validated_task_outputs"] = task_outputs or {}
        return report

    # Collect disallowed expansions
    disallowed = set()
    for exp in (question_intent.get("forbidden_expansions") or []):
        disallowed.add(str(exp).lower().strip())
    for sub_intent in (question_intent.get("subquestion_intents") or []):
        if isinstance(sub_intent, dict):
            for exp in (sub_intent.get("do_not_assume") or []):
                disallowed.add(str(exp).lower().strip())

    # Collect evidence text for support checking
    evidence_pool = ""
    if isinstance(context, dict):
        for ev in (context.get("empirical_evidence") or []):
            evidence_pool += " " + str(ev)
        for seg in (context.get("text_segments") or {}).values():
            evidence_pool += " " + str(seg)
    evidence_lower = evidence_pool.lower()

    # 1) Validate hypotheses
    all_hypotheses = (hypotheses or {}).get("hypotheses", [])
    if not isinstance(all_hypotheses, list):
        all_hypotheses = []

    for hyp in all_hypotheses:
        if not isinstance(hyp, dict):
            continue

        inference_level = str(hyp.get("inference_level", "inference")).lower()
        statement = str(hyp.get("statement", "")).lower()

        # Check if hypothesis touches a disallowed expansion
        touches_disallowed = False
        for d in disallowed:
            if d and d in statement:
                touches_disallowed = True
                report["flagged_issues"].append(f"Hypothesis '{hyp.get('id', '?')}' touches disallowed expansion: '{d}'")
                break

        if touches_disallowed:
            # Demote: still available as alternative but not primary
            hyp["inference_level"] = "speculative"
            report["demoted_hypotheses"].append(hyp)
        elif inference_level == "speculative":
            report["demoted_hypotheses"].append(hyp)
        else:
            report["validated_hypotheses"].append(hyp)

    # 2) Validate task_outputs (lightweight check)
    for task_id, output in (task_outputs or {}).items():
        if not isinstance(output, dict):
            report["validated_task_outputs"][task_id] = output
            continue

        # Pass through all task outputs but flag potential issues
        report["validated_task_outputs"][task_id] = output

    return report


def run_research_agent(
    problem_text: str,
    director_model_id: str,
    model_overrides: Optional[Dict[str, str]] = None,
    mode: str = "hq",
    return_dossier: bool = False,
):
    """运行 ResearchFlowAgent（确定性编排）。"""
    memory = ResearchMemory()
    model_overrides = model_overrides or {}
    model_map = {
        "director": build_model(_resolve_model_id("director", director_model_id, model_overrides)),
        "context": build_model(_resolve_model_id("context", director_model_id, model_overrides)),
        "ground_truth_searcher": build_model(_resolve_model_id("ground_truth_searcher", director_model_id, model_overrides)),
        "question_intent": build_model(_resolve_model_id("question_intent", director_model_id, model_overrides)),
        "task_graph": build_model(_resolve_model_id("task_graph", director_model_id, model_overrides)),
        "axiom_builder": build_model(_resolve_model_id("axiom_builder", director_model_id, model_overrides)),
        "hypothesis": build_model(_resolve_model_id("hypothesis", director_model_id, model_overrides)),
        "prompt_proximity_selector":
        build_model(_resolve_model_id("prompt_proximity_selector", director_model_id, model_overrides)),
        "wetlab": build_model(_resolve_model_id("wetlab", director_model_id, model_overrides)),
        "insilico": build_model(_resolve_model_id("insilico", director_model_id, model_overrides)),
        "data_analysis": build_model(_resolve_model_id("data_analysis", director_model_id, model_overrides)),
        "mechanism_inferer": build_model(_resolve_model_id("mechanism_inferer", director_model_id, model_overrides)),
        "pathway_mapping": build_model(_resolve_model_id("pathway_mapping", director_model_id, model_overrides)),
        "comparison_matrix": build_model(_resolve_model_id("comparison_matrix", director_model_id, model_overrides)),
        "critique": build_model(_resolve_model_id("critique", director_model_id, model_overrides)),
        "estimator": build_model(_resolve_model_id("estimator", director_model_id, model_overrides)),
        "synthesizer": build_model(_resolve_model_id("synthesizer", director_model_id, model_overrides)),
        "tradeoff": build_model(_resolve_model_id("tradeoff", director_model_id, model_overrides)),
        "verification": build_model(_resolve_model_id("verification", director_model_id, model_overrides)),
        "writer": build_model(_resolve_model_id("writer", director_model_id, model_overrides)),
        "polisher": build_model(_resolve_model_id("polisher", director_model_id, model_overrides)),
        "meta_reviewer": build_model(_resolve_model_id("meta_reviewer", director_model_id, model_overrides)),
        "proof_planner": build_model(_resolve_model_id("proof_planner", director_model_id, model_overrides)),
        "formal_deriver": build_model(_resolve_model_id("formal_deriver", director_model_id, model_overrides)),
        "proof_auditor": build_model(_resolve_model_id("proof_auditor", director_model_id, model_overrides)),
        "patcher": build_model(_resolve_model_id("patcher", director_model_id, model_overrides)),
    }

    tools = build_tools(memory)
    director = build_director_agent(model_map["director"])
    context_miner = build_context_miner_agent(model_map["context"])
    ground_truth_searcher = build_ground_truth_searcher_agent(model_map["ground_truth_searcher"])
    question_intent_aligner = build_question_intent_aligner_agent(model_map["question_intent"])
    task_graph_builder = build_task_graph_builder_agent(model_map["task_graph"])
    axiom_builder = build_axiom_builder_agent(model_map["axiom_builder"])
    hypothesis_modeler = build_hypothesis_modeler_agent(model_map["hypothesis"])
    prompt_proximity_selector = build_prompt_proximity_selector_agent(model_map["prompt_proximity_selector"])
    wetlab_designer = build_wetlab_designer_agent(model_map["wetlab"])
    insilico_designer = build_insilico_designer_agent(model_map["insilico"])
    data_analysis_designer = build_data_analysis_designer_agent(model_map["data_analysis"])
    mechanism_inferer_agent = build_mechanism_inferer_agent(model_map["mechanism_inferer"])
    pathway_mapping_agent = build_pathway_mapping_agent(model_map["pathway_mapping"])
    comparison_matrix_agent = build_comparison_matrix_agent(model_map["comparison_matrix"])
    critique_agent = build_critique_agent(model_map["critique"])
    estimator_agent = build_estimator_agent(model_map["estimator"])
    synthesizer_agent = build_synthesizer_agent(model_map["synthesizer"])
    tradeoff_agent = build_tradeoff_agent(model_map["tradeoff"])
    verification_agent = build_verification_agent(model_map["verification"])
    writer_agent = build_scientific_writer_agent(model_map["writer"])
    polisher_agent = build_terminology_polisher_agent(model_map["polisher"])
    meta_reviewer_agent = build_meta_reviewer_agent(model_map["meta_reviewer"], [tools["consistency_lint"]])
    proof_planner_agent = build_proof_planner_agent(model_map["proof_planner"])
    formal_deriver_agent = build_formal_deriver_agent(model_map["formal_deriver"])
    proof_auditor_agent = build_proof_auditor_agent(model_map["proof_auditor"])
    patcher_agent = build_patcher_agent(model_map["patcher"])

    dossier = ResearchDossier(problem=problem_text)

    context_fallback = {
        "key_terms": [],
        "entities": [],
        "given_data": {},
        "assumptions_in_text": [],
        "constraints": [],
        "deliverables": [],
        "subquestions": [],
        "negative_constraints": [],
        "core_conflicts": [],
        "entity_map": {
            "genetic_level": [],
            "protein_level": [],
            "cellular_level": [],
            "organismal_level": [],
        },
        "temporal_context": [],
        "spatial_context": [],
        "reaction_conditions": {},
        "reaction_tuples": [],
        "empirical_evidence": [],
        "text_segments": {},
        "evidence_mapping": {},
        "unchanged_features": [],
        "must_have_terms": [],
        "phenotype_summary": {
            "viability": "unknown",
            "morphology": [],
            "notes": [],
        },
    }

    try:
        context_output = context_miner.run(problem_text)
        dossier.context = _safe_agent_json(context_output, fallback=context_fallback)
    except Exception as e:
        # Most common failure mode: CodeAgent output truncated -> SyntaxError -> pipeline crash.
        # We fall back to a safe minimal ContextBrief so the pipeline can continue.
        dossier.context = dict(context_fallback)
        tools["archive"].forward("context_miner_error", str(e))

    try:
        subquestions = dossier.context.get("subquestions") or []
        must_have_terms = dossier.context.get("must_have_terms") or []
        key_terms = dossier.context.get("key_terms") or []

        if not subquestions:
            subquestions = ["Retrieve external evidence relevant to the core comparison or mechanism asked by the problem."]

        selected_subquestions = subquestions[:2]
        focus_terms = must_have_terms[:8] or key_terms[:8]

        gt_input = (
            "Retrieval task for GroundTruthSearcher:\n"
            "Goal: collect external evidence to reduce hallucination risk; do NOT solve the original problem.\n"
            f"Step budget: {ground_truth_searcher.max_steps} total steps. Remember that current-step code output is NOT visible until the next step, so finalize conservatively.\n"
            "Search at most the following subquestions in this run:\n" + "\n".join(f"- {sq}" for sq in selected_subquestions) +
            "\n\n" + "Focus terms:\n" + (", ".join(focus_terms) if focus_terms else "None provided") + "\n\n" +
            "Problem text (for context only; do not try to answer all of it):\n" + problem_text)
        gt_output = ground_truth_searcher.run(gt_input)
        gt_data = _safe_agent_json(gt_output, fallback={})
        dossier.context["external_ground_truth"] = gt_data
    except Exception as e:
        dossier.context["external_ground_truth"] = {"error": str(e), "confidence": "none"}

    # Ensure evidence index exists even if ContextMiner missed it.
    if not isinstance(dossier.context, dict):
        dossier.context = dict(context_fallback)
    if not dossier.context.get("text_segments"):
        dossier.context["text_segments"] = _build_text_segments(problem_text)
    # Sanitize: ensure empirical_evidence is a list of single-line strings
    ev = dossier.context.get("empirical_evidence")
    if isinstance(ev, list):
        dossier.context["empirical_evidence"] = [" ".join(str(x).split()) for x in ev if str(x).strip()]
    else:
        dossier.context["empirical_evidence"] = []
    # Deterministic enrichment for exam anti-hallucination fields (quote anchors / negatives / keywords)
    dossier.context = _enrich_context_for_exam(problem_text, dossier.context)
    tools["archive"].forward("context_brief", json.dumps(dossier.context, ensure_ascii=False))

    dossier.constraint_ledger = _extract_constraint_ledger(problem_text, dossier.context)
    tools["archive"].forward("constraint_ledger", json.dumps(dossier.constraint_ledger, ensure_ascii=False))

    dossier.domain_route = tools["domain_route"](dossier.context)
    tools["archive"].forward("domain_route", json.dumps(dossier.domain_route, ensure_ascii=False))

    # 学科侧配置：受控术语表 / 易混点规约（用于 Writer/Polisher/Verifier）
    domain = (dossier.domain_route or {}).get("domain", "mixed")
    if domain == "biology":
        dossier.subject_profile = {
            "domain":
            "biology",
            "banned_terms": [
                "faster",
                "slower",
                "increase",
                "decrease",
            ],
            "preferred_terms": [
                "mRNA expression",
                "protein abundance",
                "protein activity",
                "phosphorylation state",
                "genotype",
                "phenotype",
                "upstream",
                "downstream",
            ],
            "disambiguation_rules": [
                "Do not confuse gene symbol vs protein product (gene vs protein level).",
                "Do not confuse transcription (DNA->RNA) vs translation (RNA->protein).",
                "Do not confuse mutant/genotype vs phenotype/readout.",
                "Keep causal direction explicit (upstream/downstream; inhibition of inhibitor).",
            ],
            "writer_constraints": [
                "If gene symbols appear in the prompt as italic (e.g., *waslb*), preserve italicization in markdown.",
                "Do not generalize beyond stated developmental stage/tissue if temporal_context/spatial_context is provided.",
            ],
            "derivation_constraints": [
                "For metabolic energy yield calculations, use cofactor-first accounting: "
                "list ALL cofactors (NADH, FADH2, GTP, ATP) produced at EACH step separately, "
                "sum them, THEN convert to ATP using given conversion factors.",
                "TCA cycle intermediates are catalytic — do not drain them out for further oxidation.",
                "Each subquestion must be derived independently from first principles.",
            ],
        }
    elif domain == "chemistry":
        dossier.subject_profile = {
            "domain":
            "chemistry",
            "banned_terms": [
                "more reactive",
                "less reactive",
                "stronger",
                "weaker",
            ],
            "preferred_terms": [
                "kinetic control",
                "thermodynamic control",
                "inductive effect",
                "resonance effect",
                "steric effect",
                "atom economy",
                "charge conservation",
            ],
            "disambiguation_rules": [
                "Always gate conclusions by reaction_conditions (solvent/temperature/catalyst/pH/light/time).",
                "Separate kinetics (rate) vs thermodynamics (equilibrium/stability).",
                "Check atom and charge conservation when writing reaction equations.",
            ],
            "writer_constraints": [
                "If reaction_conditions are present, mention them explicitly where conclusions depend on them.",
                "If giving mechanisms/properties, tie explanations back to structure/electronic effects.",
            ],
            "derivation_constraints": [],
        }
    elif domain == "physics":
        dossier.subject_profile = {
            "domain":
            "physics",
            "banned_terms": [
                "proportional to",  # when exact equation is needed
                "roughly",
                "approximately",  # unless uncertainty is explicitly discussed
                "similar to",
            ],
            "preferred_terms": [
                "eigenstate",
                "eigenvalue",
                "Hamiltonian operator",
                "degeneracy",
                "commutator",
                "expectation value",
                "basis representation",
                "boundary condition",
            ],
            "disambiguation_rules": [
                "CRITICAL: Never confuse discrete lattice models with continuous space models. Always verify spatial boundary conditions (periodic vs fixed vs infinite).",
                "Always state the basis (e.g., momentum basis, real space basis, energy basis) before writing operator representations.",
                "Do not confuse single-particle energy levels with multi-particle states (many-body vs single-particle Hamiltonian).",
                "Distinguish between classical and quantum regimes explicitly (when ℏ matters vs classical limit).",
                "For lattice models: verify dimensionality (1D chain vs 2D square vs 3D cubic) and coordination number before deriving dispersion relations.",
                "Always check units consistency throughout derivations, not just at the end.",
            ],
            "writer_constraints": [
                "Use strict LaTeX formatting for all equations (inline: $...$, display: $$...$$).",
                "Track explicit units (e.g., MeV, fm, eV, ℏ) throughout the derivation, not just at the end.",
                "For quantum operators: always specify if they act on position space, momentum space, or abstract Hilbert space.",
                "When comparing models (e.g., finite box vs periodic lattice): create explicit side-by-side comparison before stating differences.",
            ],
        }
    elif domain == "mixed":
        dossier.subject_profile = {
            "domain":
            "mixed",
            "banned_terms": [],
            "preferred_terms": [],
            "disambiguation_rules": [
                "Clearly separate physics/chemistry/biology reasoning sections to avoid cross-domain confusion.",
                "When multiple disciplines are involved, state which discipline's framework is being used for each conclusion.",
            ],
            "writer_constraints": [
                "Use discipline-appropriate notation (LaTeX for physics/chemistry, gene symbols for biology).",
            ]
        }
    else:
        dossier.subject_profile = {
            "domain": domain,
            "banned_terms": [],
            "preferred_terms": [],
            "disambiguation_rules": [],
            "writer_constraints": []
        }

    tools["archive"].forward("subject_profile", json.dumps(dossier.subject_profile, ensure_ascii=False))

    question_intent_fallback = {
        "question_type": "protocol_consequence",
        "global_goal": "",
        "subquestion_intents": [],
        "scope_limits": "Stay within protocol-level reasoning",
        "forbidden_expansions": [],
        "grading_focus": [],
    }
    try:
        intent_output = question_intent_aligner.run(f"problem_text: {problem_text}\n"
                                                    f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}")
        dossier.question_intent = _safe_agent_json(intent_output, fallback=question_intent_fallback)
    except Exception as e:
        dossier.question_intent = dict(question_intent_fallback)
        tools["archive"].forward("question_intent_error", str(e))
    tools["archive"].forward("question_intent", json.dumps(dossier.question_intent, ensure_ascii=False))

    dossier.constraint_ledger = _enrich_constraints_from_intent(
        dossier.constraint_ledger if isinstance(dossier.constraint_ledger, dict) else {
            "constraints": [],
            "last_validated_at": ""
        },
        dossier.question_intent if isinstance(dossier.question_intent, dict) else {},
    )
    tools["archive"].forward("constraint_ledger_enriched", json.dumps(dossier.constraint_ledger, ensure_ascii=False))

    task_output = task_graph_builder.run(f"problem_text: {problem_text}\n"
                                         f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
                                         f"question_intent: {json.dumps(dossier.question_intent, ensure_ascii=False)}\n"
                                         f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}\n"
                                         f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}")
    fallback_graph = tools["build_task_graph"](problem_text, dossier.context)
    dossier.task_graph = _safe_agent_json(task_output, fallback=fallback_graph)
    dossier.task_graph = tools["task_role_router"](dossier.task_graph)
    tools["archive"].forward("task_graph", json.dumps(dossier.task_graph, ensure_ascii=False))

    dossier.derivation_intent = tools["derivation_intent"](problem_text, dossier.task_graph)
    tools["archive"].forward("derivation_intent", json.dumps(dossier.derivation_intent, ensure_ascii=False))

    # director_output = director.run("Produce a DirectorDecision dict via final_answer based on:\n"
    #                                f"problem_text: {problem_text}\n"
    #                                f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
    #                                f"task_graph: {json.dumps(dossier.task_graph, ensure_ascii=False)}\n"
    #                                f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}")
    # fallback_director = {
    #     "domain":
    #     dossier.domain_route.get("domain", "mixed"),
    #     "role_set":
    #     sorted({role
    #             for task in dossier.task_graph.get("tasks", [])
    #             for role in task.get("roles", [])}),
    #     "routing_notes": ["Fallback director decision used."],
    #     "synthesis_strategy":
    #     "Prioritize feasibility and explicit validation paths.",
    #     "output_structure": [
    #         "Problem restatement & deliverables",
    #         "Key context & assumptions / notation",
    #         "Hypotheses / model (mechanism)",
    #         "Method / protocol / computational strategy",
    #         "Analysis plan & expected outcomes",
    #         "Sanity checks, limitations, confounders",
    #         "Downstream tasks / next experiments",
    #     ],
    # }
    # dossier.director = _safe_agent_json(director_output, fallback=fallback_director)
    # tools["archive"].forward("director_decision", json.dumps(dossier.director, ensure_ascii=False))

    dossier.derivations = []
    dossier.proof_plan = None

    axiom_output = axiom_builder.run(f"problem_text: {problem_text}\n"
                                     f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
                                     f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}\n"
                                     f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}")
    dossier.axiom_ledger = _safe_agent_json(axiom_output,
                                            fallback={
                                                "space_type": "",
                                                "particle_type": "",
                                                "state_hierarchy": [],
                                                "formalism": "",
                                                "symmetries": [],
                                                "boundary_conditions": [],
                                                "explicit_protocol_facts": [],
                                                "biological_axioms": [],
                                                "chemical_axioms": [],
                                                "soft_interpretations": [],
                                                "violation_checks": [],
                                                "notes": []
                                            })
    dossier.axiom_ledger = _filter_axiom_ledger(dossier.axiom_ledger,
                                                dossier.context if isinstance(dossier.context, dict) else {})
    tools["archive"].forward("axiom_ledger", json.dumps(dossier.axiom_ledger, ensure_ascii=False))

    hypothesis_output = hypothesis_modeler.run(f"problem_text: {problem_text}\n"
                                               f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
                                               f"question_intent: {json.dumps(dossier.question_intent, ensure_ascii=False)}\n"
                                               f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}\n"
                                               f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}\n"
                                               f"task_graph: {json.dumps(dossier.task_graph, ensure_ascii=False)}")
    dossier.hypotheses = _safe_agent_json(hypothesis_output, fallback={"hypotheses": [], "notes": []})
    tools["archive"].forward("hypotheses", json.dumps(dossier.hypotheses, ensure_ascii=False))

    dossier.rational_selections = []
    if isinstance(dossier.question_intent, dict) and isinstance(dossier.hypotheses, dict):
        subquestion_intents = dossier.question_intent.get("subquestion_intents", [])
        all_hypotheses = dossier.hypotheses.get("hypotheses", [])

        for sub_intent in subquestion_intents:
            if not isinstance(sub_intent, dict):
                continue

            subquestion = sub_intent.get("subquestion", "")
            answer_scope = sub_intent.get("answer_scope", "protocol-level")

            # 为每个子问题选择最贴题的解释
            try:
                selector_output = prompt_proximity_selector.run(
                    f"problem_text: {problem_text}\n"
                    f"subquestion: {subquestion}\n"
                    f"question_goal: {sub_intent.get('question_goal', '')}\n"
                    f"answer_scope: {answer_scope}\n"
                    f"on_topic_entities: {json.dumps(sub_intent.get('on_topic_entities', []), ensure_ascii=False)}\n"
                    f"operations_under_question: {json.dumps(sub_intent.get('operations_under_question', []), ensure_ascii=False)}\n"
                    f"candidate_hypotheses: {json.dumps(all_hypotheses, ensure_ascii=False)}\n"
                    f"context_evidence: {json.dumps(dossier.context.get('empirical_evidence', []) if isinstance(dossier.context, dict) else [], ensure_ascii=False)}\n"
                    f"constraint_ledger: {json.dumps(dossier.constraint_ledger, ensure_ascii=False)}")
                selection = _safe_agent_json(selector_output,
                                             fallback={
                                                 "subquestion_id": subquestion,
                                                 "selected_rationale": "",
                                                 "selection_reason": "fallback",
                                                 "prompt_distance_score": 999,
                                                 "rejected_rationales": [],
                                                 "answer_scope_alignment": answer_scope,
                                             })
                dossier.rational_selections.append(selection)
            except Exception as e:
                tools["archive"].forward(f"prompt_proximity_selector_error_{subquestion[:30]}", str(e))

    tools["archive"].forward("rational_selections", json.dumps(dossier.rational_selections, ensure_ascii=False))

    # 任务执行引擎：处理所有类型的任务
    dossier.task_outputs = {}
    dossier.methods = []  # 保留 methods 以向后兼容，但主要使用 task_outputs

    # 按依赖关系排序任务（简单的拓扑排序）
    tasks = dossier.task_graph.get("tasks", [])
    task_dict = {task.get("id"): task for task in tasks}
    executed_tasks = set()

    # 简单的拓扑排序：执行没有依赖或依赖已执行的任务
    while len(executed_tasks) < len(tasks):
        progress_made = False
        for task in tasks:
            task_id = task.get("id")
            if task_id in executed_tasks:
                continue

            # 检查依赖是否都已执行
            depends_on = task.get("depends_on", [])
            if all(dep_id in executed_tasks for dep_id in depends_on):
                task_type = task.get("task_type")

                # 收集依赖任务的输出
                dependent_outputs = {}
                for dep_id in depends_on:
                    if dep_id in dossier.task_outputs:
                        dependent_outputs[dep_id] = dossier.task_outputs[dep_id]

                sp = dossier.subject_profile if isinstance(dossier.subject_profile, dict) else {}
                dc = sp.get("derivation_constraints")
                payload_role = {
                    "derive": "formal_deriver",
                    "parameter_estimation": "estimator",
                    "synthesis": "writer",
                }.get(task_type, "task_executor")
                runtime_inputs = {
                    "task_definition": task,
                    "domain_route": dossier.domain_route,
                    "subject_profile": dossier.subject_profile,
                    "dependent_task_outputs": dependent_outputs,
                }
                if task.get("micro_checklists"):
                    runtime_inputs["mandatory_checklist"] = task.get("micro_checklists")
                if dc and isinstance(dc, list):
                    runtime_inputs["derivation_methodology"] = dc
                payload = ""
                if task_type not in {"retrieval_task", "synthesis", "derive", "sanity_check"}:
                    payload = _compile_payload_for_agent(
                        dossier=dossier,
                        agent_role=payload_role,
                        runtime_inputs=runtime_inputs,
                        task=task,
                        archive_tool=tools["archive"],
                        archive_key=f"task_{task_id}_{task_type}",
                        legacy_payload_text=_legacy_task_payload_text(dossier, task, dependent_outputs),
                    )

                output = None
                if task_type == "design_wetlab":
                    plan_output = wetlab_designer.run(payload)
                    plan = _safe_agent_json(
                        plan_output,
                        fallback={
                            "id": f"plan_{task_id}",
                            "task_id": task_id,
                            "method_type": "wetlab",
                            "title": task.get("title", "Method Plan"),
                            "materials": [],
                            "steps": [],
                            "parameters": {},
                            "controls": [],
                            "readouts": [],
                            "failure_modes": [],
                            "alternatives": [],
                        },
                    )
                    dossier.methods.append(plan)
                    output = plan
                elif task_type == "design_insilico":
                    plan_output = insilico_designer.run(payload)
                    plan = _safe_agent_json(
                        plan_output,
                        fallback={
                            "id": f"plan_{task_id}",
                            "task_id": task_id,
                            "method_type": "insilico",
                            "title": task.get("title", "Method Plan"),
                            "materials": [],
                            "steps": [],
                            "parameters": {},
                            "controls": [],
                            "readouts": [],
                            "failure_modes": [],
                            "alternatives": [],
                        },
                    )
                    dossier.methods.append(plan)
                    output = plan
                elif task_type == "design_data_analysis":
                    plan_output = data_analysis_designer.run(payload)
                    plan = _safe_agent_json(
                        plan_output,
                        fallback={
                            "id": f"plan_{task_id}",
                            "task_id": task_id,
                            "method_type": "data_analysis",
                            "title": task.get("title", "Method Plan"),
                            "materials": [],
                            "steps": [],
                            "parameters": {},
                            "controls": [],
                            "readouts": [],
                            "failure_modes": [],
                            "alternatives": [],
                        },
                    )
                    dossier.methods.append(plan)
                    output = plan
                elif task_type == "retrieval_task":
                    query = task.get("deliverable") or task.get("title") or ""
                    output = _retrieve_evidence_snippets(problem_text,
                                                         dossier.context if isinstance(dossier.context, dict) else {},
                                                         query,
                                                         k=8)
                elif task_type == "mechanism_inference":
                    output = mechanism_inferer_agent.run(payload)
                    output = _safe_agent_json(output,
                                              fallback={
                                                  "inferred_mechanism": [],
                                                  "key_intermediates": [],
                                                  "evidence_mapping": {},
                                                  "notes": []
                                              })
                elif task_type == "pathway_mapping":
                    output = pathway_mapping_agent.run(payload)
                    output = _safe_agent_json(
                        output,
                        fallback={
                            "entities": [],
                            "edges": [],
                            "causal_chain": [],
                            "epistasis_checks": [],
                            "assumptions": [],
                            "notes": [],
                        },
                    )
                elif task_type == "comparison_table":
                    output = comparison_matrix_agent.run(payload)
                    output = _safe_agent_json(
                        output,
                        fallback={
                            "items": [],
                            "dimensions": [],
                            "cells": {},
                            "notes": [],
                        },
                    )
                elif task_type == "critique_and_tradeoff":
                    output = critique_agent.run(payload)
                    output = _safe_agent_json(output,
                                              fallback={
                                                  "strengths": [],
                                                  "weaknesses": [],
                                                  "hidden_assumptions": [],
                                                  "identified_tradeoffs": [],
                                                  "improvement_suggestions": []
                                              })
                elif task_type == "parameter_estimation":
                    output = estimator_agent.run(payload)
                    output = _safe_agent_json(output,
                                              fallback={
                                                  "target_parameter": "",
                                                  "formula_used": "",
                                                  "calculation_steps": [],
                                                  "final_value": 0.0,
                                                  "final_unit": "",
                                                  "notes_on_uncertainty": ""
                                              })
                elif task_type == "synthesis":
                    # Synthesis 任务需要所有其他任务的输出
                    all_other_outputs = dossier.task_outputs.copy()
                    synthesis_payload = _compile_payload_for_agent(
                        dossier=dossier,
                        agent_role="writer",
                        runtime_inputs={
                            "task_definition": task,
                            "domain_route": dossier.domain_route,
                            "subject_profile": dossier.subject_profile,
                            "all_prior_task_outputs": all_other_outputs,
                        },
                        task=task,
                        archive_tool=tools["archive"],
                        archive_key=f"task_{task_id}_synthesis",
                        legacy_payload_text=_legacy_task_payload_text(
                            dossier,
                            task,
                            dependent_outputs={},
                            all_prior_task_outputs=all_other_outputs,
                        ),
                    )
                    output = synthesizer_agent.run(synthesis_payload)
                    output = _safe_agent_json(output,
                                              fallback={
                                                  "main_conclusion": "",
                                                  "key_supporting_findings": [],
                                                  "scientific_implications": "",
                                                  "recommended_next_steps": []
                                              })
                elif task_type == "derive":
                    derive_runtime_inputs = {
                        "task_definition": task,
                        "domain_route": dossier.domain_route,
                        "subject_profile": dossier.subject_profile,
                        "dependent_task_outputs": dependent_outputs,
                        "derivation_intent": dossier.derivation_intent,
                    }
                    if task.get("micro_checklists"):
                        derive_runtime_inputs["mandatory_checklist"] = task.get("micro_checklists")
                    if dc and isinstance(dc, list):
                        derive_runtime_inputs["derivation_methodology"] = dc
                    derive_payload = _compile_payload_for_agent(
                        dossier=dossier,
                        agent_role="formal_deriver",
                        runtime_inputs=derive_runtime_inputs,
                        task=task,
                        archive_tool=tools["archive"],
                        archive_key=f"derive_{task_id}_planner",
                        legacy_payload_text=_legacy_task_payload_text(
                            dossier,
                            task,
                            dependent_outputs,
                            derivation_intent=dossier.derivation_intent,
                        ),
                    )

                    proof_plan_output = proof_planner_agent.run(derive_payload)
                    task_proof_plan = _safe_agent_json(proof_plan_output, fallback={"steps": [], "notes": []})

                    formal_runtime_inputs = dict(derive_runtime_inputs)
                    formal_runtime_inputs["proof_plan"] = task_proof_plan
                    formal_payload = _compile_payload_for_agent(
                        dossier=dossier,
                        agent_role="formal_deriver",
                        runtime_inputs=formal_runtime_inputs,
                        task=task,
                        archive_tool=tools["archive"],
                        archive_key=f"derive_{task_id}_formal",
                        legacy_payload_text=_legacy_task_payload_text(
                            dossier,
                            task,
                            dependent_outputs,
                            derivation_intent=dossier.derivation_intent,
                            proof_plan=task_proof_plan,
                        ),
                    )
                    batch_payload = (
                        f"{formal_payload}\n"
                        "Execute ALL steps in the proof plan and return a list of DerivationBlocks (one per step).\n"
                        "CRITICAL: Return a JSON list containing all derivation blocks, not individual blocks.\n"
                        "Maintain the order of steps from the proof plan.")
                    derivation_output = formal_deriver_agent.run(batch_payload)
                    task_derivations = _safe_agent_list(derivation_output, fallback=[])

                    output = {
                        "task_type": "derive",
                        "task_id": task_id,
                        "proof_plan": task_proof_plan,
                        "derivations": task_derivations,
                        "key_results": [d.get("result") for d in task_derivations if isinstance(d, dict) and d.get("result")]
                    }

                    dossier.derivations.extend(task_derivations)

                    tools["archive"].forward(f"proof_plan_{task_id}", json.dumps(task_proof_plan, ensure_ascii=False))
                    tools["archive"].forward(f"derivations_{task_id}", json.dumps(task_derivations, ensure_ascii=False))

                elif task_type == "sanity_check":
                    output = {
                        "task_type": task_type,
                        "status": "handled_by_verification_agent",
                        "note": "Sanity checks are performed during the verification phase"
                    }
                else:
                    # 对于其他未明确处理的 task_type，至少记录任务信息
                    output = {"task_type": task_type, "status": "not_handled", "task_title": task.get("title", "")}

                if output:
                    dossier.task_outputs[task_id] = output
                executed_tasks.add(task_id)
                progress_made = True

        if not progress_made:
            # 如果无法继续执行（可能是循环依赖），强制执行剩余任务
            for task in tasks:
                task_id = task.get("id")
                if task_id not in executed_tasks:
                    dossier.task_outputs[task_id] = {
                        "task_type": task.get("task_type"),
                        "status": "skipped_due_to_dependency_issue",
                        "task_title": task.get("title", "")
                    }
                    executed_tasks.add(task_id)
            break

    tools["archive"].forward("task_outputs", json.dumps(dossier.task_outputs, ensure_ascii=False))
    tools["archive"].forward("methods", json.dumps(dossier.methods, ensure_ascii=False))

    from sciagent.tools.constraint_validation import validate_constraints, get_violations
    if dossier.constraint_ledger and dossier.constraint_ledger.get("constraints"):
        all_task_text = " ".join(
            json.dumps(v, ensure_ascii=False) for v in dossier.task_outputs.values() if isinstance(v, dict))
        dossier.constraint_ledger = validate_constraints(all_task_text, dossier.constraint_ledger, "task_execution")
        tools["archive"].forward("constraint_ledger_post_tasks", json.dumps(dossier.constraint_ledger, ensure_ascii=False))

    decision_output = tradeoff_agent.run(f"problem_text: {problem_text}\n"
                                         f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
                                         f"task_graph: {json.dumps(dossier.task_graph, ensure_ascii=False)}\n"
                                         f"hypotheses: {json.dumps(dossier.hypotheses, ensure_ascii=False)}\n"
                                         f"methods: {json.dumps(dossier.methods, ensure_ascii=False)}\n"
                                         f"task_outputs: {json.dumps(dossier.task_outputs, ensure_ascii=False)}")
    dossier.decision = _safe_agent_json(
        decision_output,
        fallback={
            "options": [],
            "criteria": [],
            "chosen": "N/A",
            "risks": [],
            "switch_conditions": []
        },
    )
    tools["archive"].forward("decision", json.dumps(dossier.decision, ensure_ascii=False))

    intermediate_validation = _verify_intermediate_reasoning(
        dossier.question_intent if isinstance(dossier.question_intent, dict) else {},
        dossier.task_outputs,
        dossier.hypotheses if isinstance(dossier.hypotheses, dict) else {},
        dossier.rational_selections if hasattr(dossier, 'rational_selections') else [],
        dossier.context if isinstance(dossier.context, dict) else {},
    )

    if dossier.constraint_ledger:
        unsatisfied = get_violations(dossier.constraint_ledger)
        if unsatisfied:
            intermediate_validation["unsatisfied_constraints"] = unsatisfied

    tools["archive"].forward("intermediate_validation", json.dumps(intermediate_validation, ensure_ascii=False))

    draft = _call_writer(writer_agent,
                         dossier,
                         intermediate_validation=intermediate_validation,
                         archive_tool=tools["archive"])

    has_derive_tasks = any(task.get("task_type") == "derive" for task in dossier.task_graph.get("tasks", []))

    if has_derive_tasks and dossier.derivations:
        global_proof_plan = {"steps": [], "notes": []}
        for task_id, task_output in dossier.task_outputs.items():
            if isinstance(task_output, dict) and task_output.get("task_type") == "derive":
                task_plan = task_output.get("proof_plan", {})
                if task_plan.get("steps"):
                    global_proof_plan["steps"].extend(task_plan["steps"])
                if task_plan.get("notes"):
                    global_proof_plan["notes"].extend(task_plan["notes"])

        dossier.proof_plan = global_proof_plan
        tools["archive"].forward("proof_plan_global", json.dumps(dossier.proof_plan, ensure_ascii=False))
        tools["archive"].forward("derivations_global", json.dumps(dossier.derivations, ensure_ascii=False))

        proof_gap_report = tools["proof_contract"](draft, dossier.proof_plan)
        if mode == "hq":
            auditor_output = proof_auditor_agent.run(
                f"draft: {draft}\n"
                f"proof_plan: {json.dumps(dossier.proof_plan, ensure_ascii=False)}\n"
                f"derivation_blocks: {json.dumps(dossier.derivations, ensure_ascii=False)}")
            auditor_report = _safe_agent_json(
                auditor_output,
                fallback={
                    "missing_steps": [],
                    "missing_eqs": [],
                    "missing_definitions": [],
                    "generality_issues": [],
                    "notes": [],
                },
            )
            proof_gap_report = _merge_gap_reports(proof_gap_report, auditor_report)

        generality_report = tools["generality_guard"](draft)
        dossier.proof_gaps = proof_gap_report
        tools["archive"].forward("proof_gaps", json.dumps(dossier.proof_gaps, ensure_ascii=False))

        proof_patch_plan = tools["proof_patch_plan"](proof_gap_report, generality_report)
        # 如果需要修补证明，重写草稿
        if proof_patch_plan.get("actions"):
            draft = _call_writer(writer_agent, dossier, patch_plan=proof_patch_plan, archive_tool=tools["archive"])

    # 在生成草稿后进行阅卷式事实审计：对照 ContextBrief 做否定证据/冲突/完备性/幻觉检查
    # 这里的 draft 是经过推导审查后的最终稳定版本
    verification_payload = _compile_payload_for_agent(
        dossier=dossier,
        agent_role="verification",
        runtime_inputs={
            "domain_route": dossier.domain_route,
            "subject_profile": dossier.subject_profile,
            "task_graph": dossier.task_graph,
            "task_outputs": dossier.task_outputs,
            "draft": draft,
        },
        archive_tool=tools["archive"],
        archive_key="verification_final",
        legacy_payload_text=_legacy_verification_payload_text(dossier, draft),
    )
    verification_output = verification_agent.run(verification_payload)
    dossier.verification = _safe_agent_json(verification_output, fallback={"issues": [], "notes": []})
    dossier.verification = _append_deterministic_exam_checks(
        problem_text, dossier.context if isinstance(dossier.context, dict) else {}, draft,
        dossier.verification if isinstance(dossier.verification, dict) else {
            "issues": [],
            "notes": []
        })

    if dossier.constraint_ledger and dossier.constraint_ledger.get("constraints"):
        dossier.constraint_ledger = validate_constraints(draft, dossier.constraint_ledger, "post_writer")
        verification_dict = dossier.verification if isinstance(dossier.verification, dict) else {"issues": [], "notes": []}
        v_issues = verification_dict.get("issues") or []
        for c in dossier.constraint_ledger.get("constraints", []):
            if isinstance(c, dict) and c.get("status") in ("violated", "pending"):
                v_issues.append({
                    "id":
                    f"constraint_{c.get('id', 'unknown')}",
                    "severity":
                    "high",
                    "message":
                    f"Constraint not satisfied: {c.get('text', '')}",
                    "suggestion":
                    f"Add content addressing: {c.get('text', '')}. Required keywords: {c.get('keywords', [])}",
                })
        verification_dict["issues"] = v_issues
        dossier.verification = verification_dict
        tools["archive"].forward("constraint_ledger_post_writer", json.dumps(dossier.constraint_ledger, ensure_ascii=False))

    tools["archive"].forward("verification", json.dumps(dossier.verification, ensure_ascii=False))

    lint_issues = tools["consistency_lint"](draft)
    if lint_issues:
        verification_issues = dossier.verification.get("issues", []) if dossier.verification else []
        for idx, issue in enumerate(lint_issues, start=1):
            verification_issues.append({
                "id": f"lint_{idx}",
                "severity": "low",
                "message": str(issue),
                "suggestion": "Revise wording or add missing structure.",
            })
        if dossier.verification is None:
            dossier.verification = {"issues": verification_issues, "notes": []}
        else:
            dossier.verification["issues"] = verification_issues

    max_rounds = 2 if mode == "hq" else 1
    for _ in range(max_rounds):
        contract = tools["answer_contract"](draft, dossier.task_graph, dossier.context)
        if contract.get("passed"):
            break
        patch_plan = tools["patch_plan"](contract, dossier.verification)

        # 优先使用增量修补：如果有结构化 patch_actions，使用 PatcherAgent
        patch_actions = patch_plan.get("patch_actions", [])
        if patch_actions:
            try:
                patched_draft = _call_patcher(patcher_agent, draft, patch_plan)
                # 验证修补后的草稿是否满足契约
                patched_contract = tools["answer_contract"](patched_draft, dossier.task_graph, dossier.context)
                if patched_contract.get("passed") or len(patch_actions) <= 3:
                    # 如果修补后通过，或者修补操作较少（说明是精确修补），使用修补后的版本
                    draft = patched_draft
                    continue
                # 如果修补后仍未通过且修补操作较多，回退到完全重写
            except Exception:
                # 如果修补失败，回退到完全重写
                pass

        # 回退方案：完全重写（当没有 patch_actions 或修补失败时）
        draft = _call_writer(writer_agent, dossier, patch_plan=patch_plan, archive_tool=tools["archive"])

    if mode == "hq":
        meta_issues = meta_reviewer_agent.run(f"problem_text: {problem_text}\n"
                                              f"draft: {draft}\n"
                                              f"task_graph: {json.dumps(dossier.task_graph, ensure_ascii=False)}")
        if isinstance(meta_issues, str) and meta_issues.strip():
            draft += "\n\n## Meta Review Notes\n" + meta_issues.strip()

    dossier.draft = draft
    if mode == "hq":
        polisher_input = (f"draft: {draft}\n"
                          f"problem_text: {problem_text}\n"
                          f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}\n"
                          f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}\n"
                          f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}")
        dossier.final = str(polisher_agent.run(polisher_input))
    else:
        dossier.final = dossier.draft

    tools["archive"].forward("payload_views", json.dumps(dossier.payload_views, ensure_ascii=False))

    if return_dossier:
        return dossier

    return dossier.final


def run_from_file(
    input_file: str,
    director_model_id: str,
    model_overrides: Optional[Dict[str, str]] = None,
    mode: str = "hq",
    return_dossier: bool = False,
):
    """从文件读取题目并运行。"""
    problem_text = read_text_file(input_file)
    return run_research_agent(
        problem_text,
        director_model_id,
        model_overrides=model_overrides,
        mode=mode,
        return_dossier=return_dossier,
    )


def run_from_dataset(
    dataset_file: str,
    problem_id: int,
    director_model_id: str,
    model_overrides: Optional[Dict[str, str]] = None,
    mode: str = "hq",
    return_dossier: bool = False,
):
    """从 JSONL 数据集读取指定题号并运行。"""
    problem_text = read_jsonl_problem(dataset_file, problem_id)
    return run_research_agent(
        problem_text,
        director_model_id,
        model_overrides=model_overrides,
        mode=mode,
        return_dossier=return_dossier,
    )

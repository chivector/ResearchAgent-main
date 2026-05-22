from __future__ import annotations

from smolagents import tool


@tool
def patch_plan_tool(contract_report: dict, verification_report: dict) -> dict:
    """
    Build a patch plan to fix missing sections and verification issues.
    Generates both backward-compatible string actions and structured patch_actions.

    Args:
        contract_report: ContractReport JSON.
        verification_report: VerificationReport JSON.

    Returns:
        PatchPlan JSON with actions (backward-compatible) and patch_actions (structured).
    """
    actions = []  # 向后兼容的字符串格式
    patch_actions = []  # 新的结构化修补操作
    notes = []
    
    # 处理缺失的章节
    for section in contract_report.get("missing_sections", []):
        actions.append(f"Add section: {section}")
        # 确定插入位置：根据章节顺序推断
        if "Problem restatement" in section:
            target_location = "at_beginning"
        elif "Key context" in section:
            target_location = "after_section: Problem restatement & deliverables"
        elif "Hypotheses" in section:
            target_location = "after_section: Key context & assumptions / notation"
        elif "Method" in section:
            target_location = "after_section: Hypotheses / model (mechanism)"
        elif "Analysis plan" in section:
            target_location = "after_section: Method / protocol / computational strategy"
        elif "Sanity checks" in section:
            target_location = "after_section: Analysis plan & expected outcomes"
        elif "Downstream" in section:
            target_location = "after_section: Sanity checks, limitations, confounders"
        else:
            target_location = "at_end"
        
        patch_actions.append({
            "action_type": "insert_section",
            "target_location": target_location,
            "content": f"## {section}\n\n[需要添加此章节的内容]",
            "description": f"添加缺失的章节: {section}"
        })
    
    # 处理缺失的任务
    for task_id in contract_report.get("missing_tasks", []):
        actions.append(f"Cover missing task: {task_id}")
        patch_actions.append({
            "action_type": "add_content",
            "target_location": f"task_id: {task_id}",
            "content": f"[需要添加任务 {task_id} 的相关内容]",
            "description": f"补充缺失任务 {task_id} 的内容"
        })
    
    # 处理验证问题，利用 affected_component_id 进行精确修补
    for issue in verification_report.get("issues", []):
        issue_msg = issue.get('message', '')
        actions.append(f"Address verification issue: {issue_msg}")
        
        affected_id = issue.get('affected_component_id', '')
        suggestion = issue.get('suggestion', '')
        severity = issue.get('severity', 'medium')
        
        # 如果有 affected_component_id，进行精确修补
        if affected_id:
            if severity == "high":
                action_type = "replace_content"
            else:
                action_type = "modify_section"
            
            patch_actions.append({
                "action_type": action_type,
                "target_location": f"component_id: {affected_id}",
                "content": suggestion if suggestion else f"[需要修复: {issue_msg}]",
                "description": f"修复验证问题 ({severity}): {issue_msg}"
            })
        else:
            # 没有 affected_component_id，使用通用修补
            patch_actions.append({
                "action_type": "add_content",
                "target_location": "at_end",
                "content": suggestion if suggestion else f"[需要处理: {issue_msg}]",
                "description": f"处理验证问题: {issue_msg}"
            })

    if not actions and not patch_actions:
        notes.append("No patch required.")
    
    return {
        "actions": actions,  # 向后兼容
        "patch_actions": patch_actions,  # 新的结构化操作
        "notes": notes
    }

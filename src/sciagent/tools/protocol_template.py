from __future__ import annotations

from smolagents import tool


@tool
def protocol_template_tool(method_plan: dict) -> str:
    """
    Convert MethodPlan JSON to a standardized protocol template string.

    Args:
        method_plan: MethodPlan JSON.

    Returns:
        A formatted protocol string.
    """
    title = method_plan.get("title", "Protocol")
    materials = method_plan.get("materials", [])
    steps = method_plan.get("steps", [])
    parameters = method_plan.get("parameters", {})
    controls = method_plan.get("controls", [])
    readouts = method_plan.get("readouts", [])
    failure_modes = method_plan.get("failure_modes", [])
    alternatives = method_plan.get("alternatives", [])

    lines = [f"# {title}", "## Materials"]
    lines.extend([f"- {item}" for item in materials] or ["- None specified"])
    lines.append("## Steps")
    lines.extend([f"{i+1}. {step}" for i, step in enumerate(steps)] or ["1. None specified"])
    lines.append("## Parameters")
    if parameters:
        for key, value in parameters.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- None specified")
    lines.append("## Controls")
    lines.extend([f"- {item}" for item in controls] or ["- None specified"])
    lines.append("## Readouts")
    lines.extend([f"- {item}" for item in readouts] or ["- None specified"])
    lines.append("## Failure Modes")
    lines.extend([f"- {item}" for item in failure_modes] or ["- None specified"])
    lines.append("## Alternatives")
    lines.extend([f"- {item}" for item in alternatives] or ["- None specified"])
    return "\n".join(lines)

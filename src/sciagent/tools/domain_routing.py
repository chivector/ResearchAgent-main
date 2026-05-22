from __future__ import annotations

from typing import Dict, List

from smolagents import tool

PHYSICS_TERMS = {
    "quantum",
    "hamiltonian",
    "wavefunction",
    "field",
    "relativity",
    "entropy",
    "thermodynamics",
    "fisher",
    "spin",
    "lattice",
}
CHEMISTRY_TERMS = {
    "catalyst",
    "reaction",
    "stoichiometry",
    "molecule",
    "ligand",
    "bond",
    "spectroscopy",
    "redox",
    "pH",
    "solvent",
    "kinetic",
    "thermodynamic",
    "equilibrium",
    "rate",
    "mechanism",
    "nucleophile",
    "electrophile",
    "substitution",
    "elimination",
    "oxidation",
    "reduction",
    "pka",
    "acid",
    "base",
    "temperature",
    "hv",
}
BIOLOGY_TERMS = {
    "gene",
    "protein",
    "cell",
    "enzyme",
    "pathway",
    "genome",
    "transcription",
    "translation",
    "metabolism",
    "assay",
    "mutant",
    "knockout",
    "overexpression",
    "phosphorylation",
    "phenotype",
    "genotype",
    "epistasis",
    "promoter",
    "enhancer",
    "tissue",
    "embryo",
    "development",
}


def _infer_domain(context_brief: Dict) -> Dict:
    """根据关键词启发式推断领域。"""
    terms: List[str] = []
    for key in ("key_terms", "entities", "assumptions_in_text", "constraints", "deliverables", "subquestions"):
        value = context_brief.get(key, [])
        if isinstance(value, list):
            terms.extend([str(item).lower() for item in value])
    text = " ".join(terms)

    scores = {
        "physics": sum(term in text for term in PHYSICS_TERMS),
        "chemistry": sum(term in text for term in CHEMISTRY_TERMS),
        "biology": sum(term in text for term in BIOLOGY_TERMS),
    }
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_domain, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0

    if top_score == 0:
        return {"domain": "mixed", "confidence": 0.25, "evidence_terms": []}
    if top_score == second_score:
        return {"domain": "mixed", "confidence": 0.5, "evidence_terms": []}

    evidence_terms = [t for t in terms if any(k in t for k in (PHYSICS_TERMS | CHEMISTRY_TERMS | BIOLOGY_TERMS))]
    confidence = min(1.0, 0.5 + 0.1 * top_score)
    # return {"domain": top_domain, "confidence": confidence, "evidence_terms": evidence_terms[:10]}
    return {"domain": top_domain, "confidence": confidence}


@tool
def domain_route_tool(context_brief: dict) -> dict:
    """
    Infer the scientific domain of the problem from extracted context.

    Args:
        context_brief: ContextBrief JSON.

    Returns:
        DomainRoute JSON with fields:
          - domain: "physics"|"chemistry"|"biology"|"mixed"
          - confidence: float in [0,1]
          - evidence_terms: list[str]
    """
    return _infer_domain(context_brief)

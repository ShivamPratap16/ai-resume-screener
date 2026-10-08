from .keywords import AI_QUALIFYING_GROUPS, NOT_GENUINE_CUES
from .models import LEVEL_RANK, EligibilityResult, EvidenceLevel, ParsedResume

# Too generic to prove hands-on AI work when it only appears in a skills list.
GENERIC_AI_TERMS = {"LLM"}


def check_eligibility(resume: ParsedResume) -> EligibilityResult:
    python_evidence = _python_evidence(resume)
    ai_evidence = _ai_evidence(resume)
    reasons: list[str] = []

    if not python_evidence:
        if any("python" in line.lower() and NOT_GENUINE_CUES.search(line) for line in resume.text.splitlines()):
            reasons.append("Python mentioned only as something being learned, not as a working skill")
        else:
            reasons.append("No evidence of Python stack")

    if not ai_evidence:
        if resume.has_group("classic_ml"):
            reasons.append("Only classical ML evidence; no LLM/RAG/agentic project or framework")
        elif resume.has_group("ai_buzz") or resume.has_group("ai_framework"):
            reasons.append("AI mentioned only as a generic keyword; no AI/agentic project evidence")
        else:
            reasons.append("No AI/agentic project evidence")

    return EligibilityResult(
        eligible=not reasons,
        rejection_reasons=reasons,
        python_evidence=python_evidence,
        ai_evidence=ai_evidence,
    )


def _python_evidence(resume: ParsedResume) -> list[str]:
    found = []
    for ev in resume.evidence.values():
        if ev.term == "Python" or (
            "python_eco" in ev.groups and LEVEL_RANK[ev.level] >= LEVEL_RANK[EvidenceLevel.STACK]
        ):
            found.append(f"{ev.term} ({ev.level.value}): {ev.snippet}")
    return found


def _ai_evidence(resume: ParsedResume) -> list[str]:
    found = []
    for ev in resume.evidence.values():
        if not AI_QUALIFYING_GROUPS.intersection(ev.groups):
            continue
        if ev.level == EvidenceLevel.LISTED and ev.term in GENERIC_AI_TERMS:
            continue
        found.append(f"{ev.term} ({ev.level.value}): {ev.snippet}")
    return found

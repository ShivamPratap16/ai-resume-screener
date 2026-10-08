import re
from dataclasses import dataclass, field

from .config import ScoringConfig
from .keywords import AI_QUALIFYING_GROUPS, ENGINEERING_GROUPS, TERMS, TUTORIAL_CUES, WRAPPER_CUES
from .models import LEVEL_RANK, Block, Evidence, EvidenceLevel, LLMReview, ParsedResume, ScoreBreakdown, ScoreEvidence
from .parser import clip, entry_name, match_terms

# Capability -> keyword groups that show it. Points live in ScoringConfig.ai_capability_points.
# Mirrors the brief: agents, tools, retrieval, state, orchestration, evaluation and meaningful business logic.
AI_CAPABILITIES: dict[str, set[str]] = {
    "agent orchestration": {"ai_agents"},
    "tool calling": {"ai_tools"},
    "retrieval/RAG": {"ai_retrieval"},
    "state/memory": {"ai_state"},
    "evaluation": {"ai_eval"},
    "structured output/guardrails": {"ai_product"},
    "backend integration": {"backend", "database"},
    "data processing": {"data"},
    "production/business impact": {"impact", "deploy"},
    "LLM framework/API": {"ai_framework"},
}
# Present in almost any LLM project, so they don't make a project "more than a wrapper".
SHALLOW_CAPABILITIES = {"LLM framework/API", "production/business impact"}
WRAPPER_SAFE_CAPABILITIES = SHALLOW_CAPABILITIES | {"backend integration", "data processing"}
BARE_AGENT_RE = re.compile(r"(?<!user[- ])\bagents?\b(?!\s+(?:installation|install|based monitoring))", re.IGNORECASE)

# Label -> keyword terms; points per label live in ScoringConfig.
PYTHON_BACKEND_ITEMS: dict[str, set[str]] = {
    "Python": {"Python"},
    "FastAPI": {"FastAPI"},
    "async": {"asyncio", "Async programming"},
    "PostgreSQL": {"PostgreSQL"},
    "Redis": {"Redis"},
    "other backend": {"Django", "Flask", "SQLAlchemy", "Celery", "REST API", "MySQL", "MongoDB", "SQL"},
}
CLOUD_ITEMS: dict[str, set[str]] = {
    "GCP": {"GCP"},
    "Docker": {"Docker"},
    "deployment/CI": {"Deployment", "Kubernetes", "CI/CD"},
}
OTHER_CLOUD_ITEMS: dict[str, set[str]] = {"AWS/Azure": {"AWS", "Azure"}}
FRONTEND_TERMS = {"React", "Next.js"}

HIDDEN_SKILL_GROUPS = {"ai_buzz", "ai_state", "impact"}
# Concepts rather than named technologies; left out of the "stack" in project summaries.
GENERIC_TERMS = {
    "AI agents", "Multi-agent", "Tool calling", "LLM", "RAG", "Embeddings", "Vector search", "Reranking",
    "Chunking", "Agent state / memory", "LLM evaluation", "Structured output", "Prompt engineering",
    "Machine learning", "REST API", "Async programming", "Deployment", "Testing", "Caching", "Queues",
    "Observability", "Concurrency", "Failure handling", "Architecture", "Data pipeline", "Measured impact", "SQL",
}


@dataclass
class BlockAnalysis:
    block: Block
    capabilities: list[str]
    points: float
    thin_wrapper: bool
    tutorial_like: bool

    @property
    def name(self) -> str:
        return entry_name(self.block)


@dataclass
class ScoreResult:
    breakdown: ScoreBreakdown
    total: float
    evidence: ScoreEvidence
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    project_summary: str = ""
    projects: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


def matched_skills(resume: ParsedResume) -> list[str]:
    order = {term.name: i for i, term in enumerate(TERMS)}
    names = [e.term for e in resume.evidence.values() if not HIDDEN_SKILL_GROUPS.intersection(e.groups)]
    return sorted(names, key=order.get)


def analyse_ai_blocks(resume: ParsedResume, cfg: ScoringConfig) -> list[BlockAnalysis]:
    analyses = []
    for block in resume.blocks:
        groups = {g for t in match_terms(block.text) for g in t.groups}
        if not AI_QUALIFYING_GROUPS & groups:
            continue
        # Inside an entry that is already about AI, a bare "agent" means an AI agent.
        if BARE_AGENT_RE.search(block.text):
            groups.add("ai_agents")
        caps = [name for name, cap_groups in AI_CAPABILITIES.items() if cap_groups & groups]
        depth_caps = set(caps) - SHALLOW_CAPABILITIES
        wrapper_cue = bool(WRAPPER_CUES.search(block.text))
        # A wrapper must actually call an LLM; short or vague entries are handled by the tutorial rule.
        calls_llm = "llm_api" in groups or wrapper_cue
        thin = calls_llm and (not depth_caps or (wrapper_cue and depth_caps <= WRAPPER_SAFE_CAPABILITIES))
        detail_words = sum(len(line.split()) for line in block.lines)
        tutorial = bool(TUTORIAL_CUES.search(block.text)) or detail_words < cfg.min_project_detail_words
        points = sum(cfg.ai_capability_points[c] for c in caps)
        analyses.append(BlockAnalysis(block, caps, points, thin, tutorial))
    return sorted(analyses, key=lambda a: a.points, reverse=True)


def _best(resume: ParsedResume, terms: set[str] | None = None, groups: set[str] | None = None) -> Evidence | None:
    candidates = [
        e for e in resume.evidence.values()
        if (terms and e.term in terms) or (groups and groups & set(e.groups))
    ]
    return max(candidates, key=lambda e: LEVEL_RANK[e.level], default=None)


def _credit(label: str, points: float, ev: Evidence, cfg: ScoringConfig) -> tuple[float, str]:
    earned = points * cfg.evidence_multiplier[ev.level.value]
    return earned, f"{label} +{earned:.1f}/{points} ({ev.level.value}): {clip(ev.snippet)}"


def _score_items(
    resume: ParsedResume, items: dict[str, set[str]], points: dict[str, int], cfg: ScoringConfig
) -> tuple[float, list[str]]:
    total, lines = 0.0, []
    for label, terms in items.items():
        if ev := _best(resume, terms=terms):
            earned, line = _credit(label, points[label], ev, cfg)
            total += earned
            lines.append(line)
    return total, lines


def _capability_line(block: Block, groups: set[str]) -> str:
    for line in [*block.lines, block.title]:
        if any(groups & set(t.groups) for t in match_terms(line)):
            return clip(line)
    return ""


def score_ai_depth(resume: ParsedResume, blocks: list[BlockAnalysis], cfg: ScoringConfig) -> tuple[float, list[str]]:
    cap = cfg.weights.ai_project_depth
    if blocks:
        best = blocks[0]
        lines = [f"Best AI project: {best.name}"]
        lines += [
            f"{c} +{cfg.ai_capability_points[c]}: {_capability_line(best.block, AI_CAPABILITIES[c])}"
            for c in best.capabilities
        ]
        score = best.points
        if len(blocks) > 1 and blocks[1].points:
            extra = cfg.second_project_share * blocks[1].points
            score += extra
            lines.append(f"Second AI project '{blocks[1].name}' adds {cfg.second_project_share:.0%} of its {blocks[1].points}: +{extra:.1f}")
        if score > cap:
            lines.append(f"Capped at {cap}")
        return min(cap, score), lines

    # No project/experience entry mentions AI: use resume-wide evidence, discounted by where it appears.
    score, lines = 0.0, ["No AI project entry found; scored from resume-wide evidence"]
    for name, groups in AI_CAPABILITIES.items():
        if ev := _best(resume, groups=groups):
            earned, line = _credit(name, cfg.ai_capability_points[name], ev, cfg)
            score += earned
            lines.append(line)
    return min(cap, score), lines


def score_python_backend(resume: ParsedResume, cfg: ScoringConfig) -> tuple[float, list[str]]:
    score, lines = _score_items(resume, PYTHON_BACKEND_ITEMS, cfg.python_backend_points, cfg)
    work = next((b for b in resume.blocks if b.section == "experience" and "python" in b.text.lower()), None)
    if work:
        score += cfg.python_at_work_bonus
        lines.append(f"Python used in internship/work +{cfg.python_at_work_bonus}: {entry_name(work)}")
    return min(cfg.weights.python_backend, score), lines


def score_cloud_fullstack(resume: ParsedResume, cfg: ScoringConfig) -> tuple[float, list[str]]:
    items = CLOUD_ITEMS if "GCP" in resume.evidence else {**CLOUD_ITEMS, **OTHER_CLOUD_ITEMS}
    score, lines = _score_items(resume, items, cfg.cloud_points, cfg)
    end_to_end = next((
        b for b in resume.blocks
        if {t.name for t in match_terms(b.text)} & FRONTEND_TERMS
        and {g for t in match_terms(b.text) for g in t.groups} & {"backend", "ai_framework", "ai_agents"}
    ), None)
    if end_to_end:
        score += cfg.end_to_end_frontend_points
        lines.append(f"React/Next.js in an end-to-end project +{cfg.end_to_end_frontend_points}: {entry_name(end_to_end)}")
    elif FRONTEND_TERMS & resume.evidence.keys():
        score += cfg.frontend_only_points
        lines.append(f"React/Next.js outside an end-to-end project +{cfg.frontend_only_points}")
    return min(cfg.weights.cloud_fullstack, score), lines


def score_engineering_depth(resume: ParsedResume, cfg: ScoringConfig) -> tuple[float, list[str]]:
    score, lines = 0.0, []
    for group in ENGINEERING_GROUPS:
        if ev := _best(resume, groups={group}):
            earned, line = _credit(group, cfg.engineering_signal_points, ev, cfg)
            score += earned
            lines.append(line)
    return min(cfg.weights.engineering_depth, score), lines


def compute_penalties(blocks: list[BlockAnalysis], cfg: ScoringConfig) -> tuple[float, list[str]]:
    penalty, notes = 0.0, []
    thin = [b for b in blocks if b.thin_wrapper]
    if blocks and len(thin) == len(blocks):
        penalty += cfg.thin_wrapper_penalty_all
        notes.append(f"-{cfg.thin_wrapper_penalty_all}: every AI project is a thin LLM/API wrapper ({'; '.join(b.name for b in thin)})")
    elif thin:
        penalty += cfg.thin_wrapper_penalty_some
        notes.append(f"-{cfg.thin_wrapper_penalty_some}: thin-wrapper AI project ({'; '.join(b.name for b in thin)})")
    for b in [b for b in blocks if b.tutorial_like][:2]:
        penalty += cfg.tutorial_penalty
        notes.append(f"-{cfg.tutorial_penalty}: tutorial-style or no implementation detail ({b.name})")
    if penalty > cfg.max_total_penalty:
        notes.append(f"Penalties capped at -{cfg.max_total_penalty}")
    return min(penalty, cfg.max_total_penalty), notes


def has_meaningful_ai_project(resume: ParsedResume, blocks: list[BlockAnalysis]) -> bool:
    if blocks:
        return any(not b.thin_wrapper and not b.tutorial_like for b in blocks)
    ev = _best(resume, groups={"ai_agents", "ai_retrieval"})
    return ev is not None and ev.level == EvidenceLevel.APPLIED


def score_candidate(
    resume: ParsedResume,
    github_points: float,
    cfg: ScoringConfig,
    llm_review: LLMReview | None = None,
    github_reasons: list[str] | None = None,
) -> ScoreResult:
    blocks = analyse_ai_blocks(resume, cfg)
    ai_depth, ai_lines = score_ai_depth(resume, blocks, cfg)
    penalty, penalty_lines = compute_penalties(blocks, cfg)

    if llm_review is not None:
        llm_depth = max(0, min(cfg.weights.ai_project_depth, llm_review.ai_project_depth))
        blended = (1 - cfg.llm_blend_weight) * ai_depth + cfg.llm_blend_weight * llm_depth
        ai_lines.append(f"Blended with LLM review: rules {ai_depth:.1f} x {1 - cfg.llm_blend_weight:.0%} + LLM {llm_depth} x {cfg.llm_blend_weight:.0%} = {blended:.1f}")
        ai_depth = blended
        if llm_review.thin_wrapper and not any(b.thin_wrapper for b in blocks):
            penalty = min(cfg.max_total_penalty, penalty + cfg.thin_wrapper_penalty_some)
            penalty_lines.append(f"-{cfg.thin_wrapper_penalty_some}: LLM reviewer judged the AI work a thin wrapper")

    python_backend, py_lines = score_python_backend(resume, cfg)
    cloud, cloud_lines = score_cloud_fullstack(resume, cfg)
    engineering, eng_lines = score_engineering_depth(resume, cfg)
    breakdown = ScoreBreakdown(
        ai_project_depth=round(ai_depth, 1),
        python_backend=round(python_backend, 1),
        cloud_fullstack=round(cloud, 1),
        github=round(min(github_points, cfg.weights.github), 1),
        engineering_depth=round(engineering, 1),
        penalties=-round(penalty, 1) if penalty else 0.0,
    )
    total = max(0.0, sum(breakdown.model_dump().values()))
    if not has_meaningful_ai_project(resume, blocks) and total > cfg.no_ai_project_cap:
        penalty_lines.append(f"Total capped at {cfg.no_ai_project_cap}: no meaningful AI project (only thin, tutorial or skills-list AI evidence)")
        total = cfg.no_ai_project_cap

    evidence = ScoreEvidence(
        ai_project_depth=ai_lines,
        python_backend=py_lines,
        cloud_fullstack=cloud_lines,
        github=github_reasons or [],
        engineering_depth=eng_lines,
        penalties=penalty_lines,
    )
    result = ScoreResult(breakdown=breakdown, total=round(total, 1), evidence=evidence)
    _describe(resume, blocks, result, cfg)
    if llm_review is not None:
        result.project_summary = llm_review.project_summary or result.project_summary
        result.highlights = llm_review.evidence or result.highlights
        result.strengths = _merge(result.strengths, llm_review.strengths)
        result.concerns = _merge(result.concerns, llm_review.concerns)
    return result


def _merge(a: list[str], b: list[str], limit: int = 6) -> list[str]:
    seen, merged = set(), []
    for item in [*a, *b]:
        if item and item.lower() not in seen:
            seen.add(item.lower())
            merged.append(item)
    return merged[:limit]


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def summarise_project(analysis: BlockAnalysis) -> str:
    depth = [c for c in analysis.capabilities if c not in SHALLOW_CAPABILITIES] or ["LLM API calls"]
    stack = [t.name for t in match_terms(analysis.block.text)
             if t.name not in GENERIC_TERMS and not HIDDEN_SKILL_GROUPS.intersection(t.groups)][:6]
    summary = f"{analysis.name}: {_join(depth)}"
    return summary + (f", built with {', '.join(stack)}." if stack else ".")


def _describe(resume: ParsedResume, blocks: list[BlockAnalysis], result: ScoreResult, cfg: ScoringConfig) -> None:
    w, b, ev = cfg.weights, result.breakdown, resume.evidence
    project_blocks = [blk for blk in resume.blocks if blk.section == "projects"] or resume.blocks
    result.projects = [entry_name(blk) for blk in project_blocks][:6]

    if blocks:
        best = blocks[0]
        result.project_summary = summarise_project(best)
        ranked_lines = sorted(best.block.lines, key=lambda line: -len(match_terms(line)))
        result.highlights = [clip(line, 200) for line in ranked_lines[:2]]
    else:
        result.project_summary = "No structured AI project entry; AI exposure comes from skills/summary lines."
        result.highlights = [clip(e.snippet, 200) for e in ev.values() if AI_QUALIFYING_GROUPS & set(e.groups)][:2]

    if b.ai_project_depth >= 0.7 * w.ai_project_depth:
        result.strengths.append("Strong AI/agentic project depth")
    if b.python_backend >= 0.7 * w.python_backend:
        result.strengths.append("Solid Python backend evidence in real work")
    if b.cloud_fullstack >= 0.6 * w.cloud_fullstack:
        result.strengths.append("Cloud/deployment experience")
    if b.engineering_depth >= 4:
        result.strengths.append("Shows engineering depth (testing, caching, resilience)")
    if b.github >= 7:
        result.strengths.append("Active, relevant public GitHub")

    for name, terms in (("FastAPI", {"FastAPI"}), ("PostgreSQL", {"PostgreSQL"}), ("Redis", {"Redis"}),
                        ("async", {"asyncio", "Async programming"}), ("Docker", {"Docker"})):
        if not terms & ev.keys():
            result.concerns.append(f"No {name} evidence")
    if not {"GCP", "AWS", "Azure"} & ev.keys():
        result.concerns.append("No cloud platform evidence")
    ai_levels = {e.level.value for e in ev.values() if AI_QUALIFYING_GROUPS & set(e.groups)}
    if ai_levels == {"listed"}:
        result.concerns.append("AI frameworks only listed in skills, no usage shown")
    if any(blk.thin_wrapper for blk in blocks):
        result.concerns.append("Thin-wrapper AI project")
    if any(blk.tutorial_like for blk in blocks):
        result.concerns.append("Tutorial-style AI project without implementation detail")

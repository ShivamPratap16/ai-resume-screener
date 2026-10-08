from screener.models import LLMReview
from screener.scoring import score_candidate

from conftest import SKILLS_ONLY_AI, STRONG_AGENTIC, THIN_WRAPPER, make_resume


def _review(depth: int, thin: bool = False) -> LLMReview:
    return LLMReview(ai_project_depth=depth, thin_wrapper=thin, tutorial_like=False, project_summary="s",
                     evidence=["q"], strengths=[], concerns=[])


def test_scores_stay_within_category_weights(cfg):
    b = score_candidate(make_resume(STRONG_AGENTIC), github_points=10, cfg=cfg).breakdown
    assert b.ai_project_depth <= 40 and b.python_backend <= 30 and b.cloud_fullstack <= 15
    assert b.github <= 10 and b.engineering_depth <= 5


def test_deep_agentic_project_beats_thin_wrapper(cfg):
    strong = score_candidate(make_resume(STRONG_AGENTIC), 0, cfg)
    thin = score_candidate(make_resume(THIN_WRAPPER), 0, cfg)
    assert strong.total > thin.total + 40
    assert strong.breakdown.penalties == 0


def test_thin_wrapper_is_penalised_and_explained(cfg):
    result = score_candidate(make_resume(THIN_WRAPPER), 0, cfg)
    assert result.breakdown.penalties <= -cfg.thin_wrapper_penalty_all
    assert any("thin" in note for note in result.evidence.penalties)
    assert "Thin-wrapper AI project" in result.concerns


def test_tutorial_project_is_penalised(cfg):
    text = """
    Varun Das
    SKILLS
    Python, LangChain
    PROJECTS
    Chat with PDF (LangChain)
    - Followed a YouTube tutorial to build a chat with PDF app using LangChain
    """
    result = score_candidate(make_resume(text), 0, cfg)
    assert any("tutorial" in note for note in result.evidence.penalties)


def test_strong_python_without_ai_project_is_capped(cfg):
    result = score_candidate(make_resume(SKILLS_ONLY_AI), github_points=10, cfg=cfg)
    assert result.total == cfg.no_ai_project_cap
    assert "AI frameworks only listed in skills, no usage shown" in result.concerns


def test_skill_list_keywords_score_less_than_applied_usage(cfg):
    listed = make_resume("Jane Doe\nSKILLS\nPython, FastAPI, PostgreSQL, Redis\n")
    applied = make_resume(
        "Jane Doe\nEXPERIENCE\nBackend Intern | 2025\n- Built async FastAPI services in Python with PostgreSQL and Redis\n"
    )
    assert score_candidate(applied, 0, cfg).breakdown.python_backend > score_candidate(listed, 0, cfg).breakdown.python_backend


def test_llm_review_is_blended_and_clamped(cfg):
    resume = make_resume(STRONG_AGENTIC)
    rules_only = score_candidate(resume, 0, cfg).breakdown.ai_project_depth
    blended = score_candidate(resume, 0, cfg, llm_review=_review(999)).breakdown.ai_project_depth
    assert blended == round((1 - cfg.llm_blend_weight) * rules_only + cfg.llm_blend_weight * 40, 1)


def test_llm_thin_wrapper_flag_adds_penalty_when_rules_missed_it(cfg):
    result = score_candidate(make_resume(STRONG_AGENTIC), 0, cfg, llm_review=_review(10, thin=True))
    assert result.breakdown.penalties == -cfg.thin_wrapper_penalty_some


def test_every_scored_category_explains_its_points(cfg):
    result = score_candidate(make_resume(STRONG_AGENTIC), 0, cfg, github_reasons=["Latest push 3 days ago: +3/3"])
    ev = result.evidence
    assert ev.ai_project_depth[0].startswith("Best AI project: Support Copilot")
    assert any(line.startswith("retrieval/RAG +8") for line in ev.ai_project_depth)
    assert any(line.startswith("FastAPI +6.0/6 (applied)") for line in ev.python_backend)
    assert ev.github == ["Latest push 3 days ago: +3/3"]
    assert ev.cloud_fullstack and ev.engineering_depth


def test_project_summary_uses_clean_entry_name(cfg):
    result = score_candidate(make_resume(STRONG_AGENTIC), 0, cfg)
    assert result.project_summary.startswith("Support Copilot: agent orchestration, tool calling, retrieval/RAG")
    assert "built with" in result.project_summary

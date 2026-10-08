import asyncio

from screener.config import LLMConfig
from screener.llm import LLMService, build_reviewer, verify_evidence
from screener.models import LLMReview

from conftest import STRONG_AGENTIC, make_resume


def _review(evidence):
    return LLMReview(ai_project_depth=30, thin_wrapper=False, tutorial_like=False, project_summary="Agent",
                     evidence=evidence, strengths=[], concerns=[])


class FakeReviewer:
    model_name = "fake"

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    async def review(self, resume_text):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_verify_evidence_drops_hallucinated_quotes():
    text = "Built a LangGraph multi-agent workflow with tool calling against refund APIs"
    review = verify_evidence(_review(["LangGraph multi-agent workflow", "Won a Kaggle gold medal"]), text)
    assert review.evidence == ["LangGraph multi-agent workflow"]


def test_verify_evidence_rejects_review_with_no_real_quotes():
    assert verify_evidence(_review(["Invented quote about Kubernetes"]), "Python developer") is None


def test_model_failure_degrades_gracefully():
    service = LLMService(FakeReviewer(error=RuntimeError("503 overloaded")), LLMConfig())
    review, status = asyncio.run(service.review(make_resume(STRONG_AGENTIC)))
    assert review is None and status.startswith("failed")


def test_successful_review_is_returned():
    reviewer = FakeReviewer(result=_review(["multi-agent workflow with tool calling"]))
    review, status = asyncio.run(LLMService(reviewer, LLMConfig()).review(make_resume(STRONG_AGENTIC)))
    assert status == "ok" and review.ai_project_depth == 30


def test_llm_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    reviewer, mode = build_reviewer(LLMConfig(mode="auto"))
    assert reviewer is None and "disabled" in mode

import asyncio
import json

import anthropic
import httpx2
import pytest

from screener.config import LLMConfig
from screener.llm import AnthropicReviewer, LLMError

REVIEW = {
    "ai_project_depth": 33, "thin_wrapper": False, "tutorial_like": False,
    "project_summary": "Stateful LangGraph agent with retrieval.", "evidence": ["multi-agent workflow"],
    "strengths": ["Agentic depth"], "concerns": [],
}


def _reviewer(handler) -> AnthropicReviewer:
    client = anthropic.AsyncAnthropic(
        api_key="test", max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicReviewer(LLMConfig(), client=client)


def _message(text: str, stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_request_shape_and_structured_parse():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx2.Response(200, json=_message(json.dumps(REVIEW)))

    review = asyncio.run(_reviewer(handler).review("resume text"))
    assert review.ai_project_depth == 33
    assert seen["model"] == "claude-opus-5-5"
    assert seen["output_config"]["format"]["type"] == "json_schema"
    assert seen["fallbacks"] == "default" and "server-side-fallback" in seen["beta"]
    assert "<resume>" in seen["messages"][0]["content"]


def test_api_errors_become_llm_errors():
    handler = lambda request: httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})
    with pytest.raises(LLMError):
        asyncio.run(_reviewer(handler).review("resume text"))


def test_refusal_becomes_llm_error():
    handler = lambda request: httpx2.Response(200, json=_message("", stop_reason="refusal"))
    with pytest.raises(LLMError):
        asyncio.run(_reviewer(handler).review("resume text"))

from pathlib import Path
from textwrap import dedent

import pytest

from screener.config import ScoringConfig
from screener.parser import parse_resume


def make_resume(text: str, name: str = "resume.txt"):
    return parse_resume(Path(name), dedent(text).strip(), file_hash=name)


@pytest.fixture
def cfg() -> ScoringConfig:
    return ScoringConfig()


STRONG_AGENTIC = """
Asha Rao
asha.rao@example.com | github.com/asha-rao-dev
SKILLS
Python, FastAPI, LangGraph, PostgreSQL, Redis, Docker, GCP
PROJECTS
Support Copilot | Python, LangGraph, FastAPI
- Built a LangGraph multi-agent workflow with tool calling against refund APIs
- Implemented hybrid search with pgvector embeddings and re-ranking over 40k tickets
- Persisted agent state in PostgreSQL checkpoints and added Redis caching
- Added an evaluation pipeline with RAGAS and a golden set in CI
- Async FastAPI service with retries and timeouts, deployed on GCP Cloud Run with Docker
"""

THIN_WRAPPER = """
Rahul Verma
rahul@example.com
SKILLS
Python, Streamlit, OpenAI API
PROJECTS
AI Chatbot | Python, Streamlit
- Simple chatbot that sends the user prompt to the OpenAI API and displays the response
"""

SKILLS_ONLY_AI = """
Neha Iyer
neha@example.com
SKILLS
Python, Django, FastAPI, PostgreSQL, Redis, Docker, AWS, LangChain, LlamaIndex
EXPERIENCE
Backend Intern, ShopStack | Jan 2025 - Jun 2025
- Developed async FastAPI services with PostgreSQL and Redis caching
- Containerized services with Docker and deployed to AWS with GitHub Actions
- Wrote pytest unit tests and added retries with exponential backoff
"""

JAVA_REACT_ONLY = """
Riya Gupta
riya@example.com
SKILLS
Java, Spring Boot, React, MySQL
PROJECTS
Library System | Java, Spring Boot
- Developed Spring Boot services with MySQL persistence and a React frontend
"""

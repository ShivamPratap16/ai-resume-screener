import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Weights:
    ai_project_depth: int = 40
    python_backend: int = 30
    cloud_fullstack: int = 15
    github: int = 10
    engineering_depth: int = 5


@dataclass(frozen=True)
class ScoringConfig:
    weights: Weights = field(default_factory=Weights)
    # How much a keyword is worth depending on where it was found.
    evidence_multiplier: dict[str, float] = field(
        default_factory=lambda: {"applied": 1.0, "stack": 0.7, "listed": 0.35}
    )
    # Points per capability found in one AI project entry; must add up to weights.ai_project_depth.
    ai_capability_points: dict[str, int] = field(default_factory=lambda: {
        "agent orchestration": 7,
        "tool calling": 5,
        "retrieval/RAG": 8,
        "state/memory": 5,
        "evaluation": 5,
        "structured output/guardrails": 2,
        "backend integration": 3,
        "data processing": 1,
        "production/business impact": 3,
        "LLM framework/API": 1,
    })
    second_project_share: float = 0.25
    python_backend_points: dict[str, int] = field(default_factory=lambda: {
        "Python": 8, "FastAPI": 6, "async": 4, "PostgreSQL": 4, "Redis": 3, "other backend": 3,
    })
    python_at_work_bonus: int = 2
    cloud_points: dict[str, int] = field(default_factory=lambda: {
        "GCP": 5, "Docker": 4, "deployment/CI": 3, "AWS/Azure": 3,
    })
    end_to_end_frontend_points: int = 3
    frontend_only_points: int = 1
    engineering_signal_points: int = 1
    thin_wrapper_penalty_all: int = 12
    thin_wrapper_penalty_some: int = 5
    tutorial_penalty: int = 5
    max_total_penalty: int = 20
    # Candidates without a single non-trivial AI project can't rank near the top.
    no_ai_project_cap: int = 30
    min_project_detail_words: int = 12
    # The LLM only informs AI project depth; this is its share of that category.
    llm_blend_weight: float = 0.5

    def __post_init__(self) -> None:
        total = sum(self.ai_capability_points.values())
        if total != self.weights.ai_project_depth:
            raise ValueError(f"ai_capability_points add up to {total}, expected {self.weights.ai_project_depth}")


@dataclass(frozen=True)
class GitHubConfig:
    token: str | None = os.getenv("GITHUB_TOKEN") or None
    api_url: str = "https://api.github.com"
    timeout_s: float = 10.0
    max_concurrency: int = 5
    cache_ttl_s: int = 24 * 3600
    # Scoring tiers: (threshold, points), checked in order; recency thresholds are "at most N days ago".
    push_recency_tiers: tuple[tuple[int, int], ...] = ((30, 3), (90, 2), (365, 1))
    active_day_tiers: tuple[tuple[int, int], ...] = ((8, 2), (2, 1))
    recent_repo_tiers: tuple[tuple[int, int], ...] = ((3, 2), (1, 1))  # fallback when events are unavailable
    maintained_repo_tiers: tuple[tuple[int, int], ...] = ((3, 2), (1, 1))
    relevant_repo_tiers: tuple[tuple[int, int], ...] = ((4, 3), (2, 2), (1, 1))
    activity_window_days: int = 90
    maintained_window_days: int = 365


@dataclass(frozen=True)
class LLMConfig:
    # auto: use the LLM only when an Anthropic credential is present; true/false force it.
    mode: str = os.getenv("LLM_ENABLED", "auto").lower()
    model: str = os.getenv("LLM_MODEL", "claude-opus-5-5")
    effort: str = os.getenv("LLM_EFFORT", "medium")
    max_concurrency: int = int(os.getenv("LLM_MAX_CONCURRENCY", "4"))
    timeout_s: float = 90.0


@dataclass(frozen=True)
class Settings:
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    cache_dir: Path = Path(os.getenv("SCREENER_CACHE_DIR", ".cache"))
    min_text_chars: int = 150
    # Each file is parsed in a worker process; one that runs longer is recorded as failed and killed.
    parse_timeout_s: float = float(os.getenv("PARSE_TIMEOUT_S", "20"))
    parse_workers: int = int(os.getenv("PARSE_WORKERS", "4"))
    supported_extensions: tuple[str, ...] = (".pdf", ".docx", ".txt")

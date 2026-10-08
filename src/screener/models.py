from enum import Enum

from pydantic import BaseModel, Field


class EvidenceLevel(str, Enum):
    APPLIED = "applied"  # described in a project/experience bullet
    STACK = "stack"      # tech-stack list inside a project/experience entry
    LISTED = "listed"    # skills section or a bare keyword list


LEVEL_RANK = {EvidenceLevel.LISTED: 0, EvidenceLevel.STACK: 1, EvidenceLevel.APPLIED: 2}


class Evidence(BaseModel):
    term: str
    groups: list[str]
    level: EvidenceLevel
    snippet: str


class Block(BaseModel):
    """One project or experience entry."""
    section: str
    title: str
    lines: list[str] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join([self.title, *self.lines])


class ParsedResume(BaseModel):
    file: str
    file_hash: str
    text: str
    name: str
    email: str | None = None
    phone: str | None = None
    github_usernames: list[str] = Field(default_factory=list)
    sections: dict[str, list[str]] = Field(default_factory=dict)
    blocks: list[Block] = Field(default_factory=list)
    evidence: dict[str, Evidence] = Field(default_factory=dict)

    @property
    def github_username(self) -> str | None:
        return self.github_usernames[0] if self.github_usernames else None

    def has_group(self, group: str, min_level: EvidenceLevel = EvidenceLevel.LISTED) -> bool:
        return any(
            group in e.groups and LEVEL_RANK[e.level] >= LEVEL_RANK[min_level]
            for e in self.evidence.values()
        )


class EligibilityResult(BaseModel):
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    python_evidence: list[str] = Field(default_factory=list)
    ai_evidence: list[str] = Field(default_factory=list)


class GitHubStatus(str, Enum):
    OK = "ok"
    NO_PROFILE = "no_profile"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class RepoInfo(BaseModel):
    name: str
    language: str | None = None
    description: str | None = None
    topics: list[str] = Field(default_factory=list)
    fork: bool = False
    archived: bool = False
    pushed_at: str | None = None
    stars: int = 0


class GitHubActivity(BaseModel):
    username: str | None = None
    status: GitHubStatus
    repos: list[RepoInfo] = Field(default_factory=list)
    # Distinct days with public pushes/PRs in the last 90 days; None if the events call failed.
    active_days_90d: int | None = None
    error: str | None = None

    @property
    def profile_url(self) -> str | None:
        return f"https://github.com/{self.username}" if self.username else None


class LLMReview(BaseModel):
    """Schema the model must return. Scores are clamped by the caller."""
    ai_project_depth: int = Field(description="0-40. Depth of the strongest AI/agentic/RAG work, per the rubric.")
    thin_wrapper: bool = Field(description="True if the AI work is only a thin wrapper around an LLM API call.")
    tutorial_like: bool = Field(description="True if AI projects look like tutorials without ownership/implementation detail.")
    project_summary: str = Field(description="One sentence describing the strongest AI project, grounded in the resume.")
    evidence: list[str] = Field(description="2-4 short verbatim quotes from the resume that justify the depth score.")
    strengths: list[str] = Field(description="Up to 3 short strengths.")
    concerns: list[str] = Field(description="Up to 3 short concerns.")


class ScoreBreakdown(BaseModel):
    ai_project_depth: float = 0
    python_backend: float = 0
    cloud_fullstack: float = 0
    github: float = 0
    engineering_depth: float = 0
    penalties: float = 0


class ScoreEvidence(BaseModel):
    """Why each category got its points: one line per contributing signal."""
    ai_project_depth: list[str] = Field(default_factory=list)
    python_backend: list[str] = Field(default_factory=list)
    cloud_fullstack: list[str] = Field(default_factory=list)
    github: list[str] = Field(default_factory=list)
    engineering_depth: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)


class RankedCandidate(BaseModel):
    rank: int = 0
    candidate_name: str
    eligible: bool = True
    total_score: float
    score_breakdown: ScoreBreakdown
    score_evidence: ScoreEvidence
    matched_skills: list[str]
    project_summary: str
    projects: list[str]
    github_url: str | None
    github_summary: str
    github_status: str
    strengths: list[str]
    concerns: list[str]
    evidence: list[str]
    llm_status: str
    file: str
    email: str | None


class RejectedCandidate(BaseModel):
    candidate_name: str
    eligible: bool = False
    rejection_reasons: list[str]
    matched_skills: list[str]
    evidence: list[str]
    file: str
    email: str | None


class FailedFile(BaseModel):
    file: str
    status: str  # failed | duplicate
    error: str


class BatchSummary(BaseModel):
    total_files: int
    parsed: int
    eligible: int
    rejected: int
    failed: int
    duplicates: int
    github_enriched: int
    llm_reviewed: int
    duration_s: float


class ScreeningReport(BaseModel):
    summary: BatchSummary
    ranked: list[RankedCandidate]
    rejected: list[RejectedCandidate]
    failed: list[FailedFile]

# AI Resume Screening & Ranking

Takes a folder of resumes and does four things:
- drops candidates who don't meet the hard Python + AI/agentic requirement,
- scores the rest out of 100, with resume evidence behind every point,
- adds public GitHub activity,
- writes a ranked JSON report plus an HTML report.

```
resumes/ ──► ingest (PDF/DOCX/TXT, hash + email dedupe) ──► parse (sections, contacts, project entries, evidence levels)
         ──► hard eligibility (rules only) ──► enrich eligible: GitHub + optional LLM review (async, bounded, cached)
         ──► score (100 pts, penalties, cap, per-point evidence) ──► rank ──► results.json + report.html + console table
```

## Setup

Requires **Python 3.10+** (developed and tested on 3.13).

```bash
python -m venv .venv
.venv\Scripts\activate             # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
cp .env.example .env                # optional: GITHUB_TOKEN, ANTHROPIC_API_KEY
```

No keys are required.
- **Without `GITHUB_TOKEN`:** GitHub's anonymous API allows 60 requests/hour, about 30 candidates per hour, since each takes 2 calls. Results are cached on disk for 24 hours. A token with no permissions raises the limit to 5,000/hour.
- **Without `ANTHROPIC_API_KEY`:** scoring is fully rule-based and deterministic.

## Run

```bash
python main.py --input ./resumes --output ./output/results.json      # also writes output/report.html; add --redact-emails to share
python -m pytest -q                                                    # 79 tests
uvicorn screener.api:app --app-dir src                                 # optional API: POST /screen (multipart files), GET /results
python scripts/benchmark_concurrency.py --input resumes --limits 1 5 10
```

The provided resumes go in `resumes/`. They're kept out of git because they contain personal data. For the same reason the committed `output/results.json` was generated with `--redact-emails`, which masks emails as `j***@gmail.com`. Run without the flag to get full addresses.

**Synthetic test resumes.** `tests/fixtures/sample_resumes/` has 51 generated files with fictional names, covering:
- thin wrappers, tutorials, and AI frameworks listed only in skills
- Java-, MERN- and JS-only profiles, classical ML, and "learning Python"
- resumes with no headings, DOCX and TXT files
- a corrupt PDF, an image-only PDF, duplicates and an unsupported file

Each file's expected outcome is in `tests/fixtures/sample_manifest.json`, and a test checks all of them. To regenerate: `python scripts/generate_sample_resumes.py`.

## Results on the provided 50 resumes

| Files | Parsed | Eligible | Rejected | Failed | GitHub enriched | Penalised |
|---|---|---|---|---|---|---|
| 50 | 50 | 33 | 17 | 0 | 31 / 33 | 5 |

Rejections: 9 had AI only as a generic keyword (including AI coding tools such as Cursor/Copilot), 7 had no Python, 4 had only classical ML, and 2 had no AI evidence at all. The top candidates have production agentic + RAG systems with FastAPI/PostgreSQL/Redis and active GitHub profiles. `output/report.html` has the full table with an expandable "why this score" panel per candidate.

**Robustness.** Each file is parsed in a worker process with a 20-second limit (`PARSE_TIMEOUT_S`). A file that hangs is recorded as failed and its worker is killed. A file that crashes the parser is retried on its own, so only that file fails. Neither can stall or crash the rest of the batch.

**Async speed-up** (measured on this set: live GitHub, no cache, LLM off): sequential took **47.7s**, the default `max_concurrency=5` took **10.4s (4.6×)**, and 10 took 7.9s (6.1×).

## Output

`output/results.json` follows the shape in the brief, with a few additions:

- **`summary`**: total files, parsed, eligible, rejected, failed, duplicates, GitHub enriched, LLM reviewed, duration
- **`ranked`** (highest score first):
  - **Scores:** `rank`, `candidate_name`, `total_score`, `score_breakdown` (the 5 categories + `penalties`)
  - **`score_evidence`:** for each category, the signals that earned points, with the resume line and its evidence level, e.g. `"FastAPI +6.0/6 (applied): Developed async FastAPI services…"`
  - **Profile:** `matched_skills`, `project_summary`, `projects`, `strengths`, `concerns`, `evidence` (the most relevant resume lines)
  - **GitHub:** `github_url`, `github_summary`, `github_status`
  - **Other:** `llm_status`, `file`, `email`
- **`rejected`**: `candidate_name`, `eligible: false`, `rejection_reasons`, `matched_skills`, the evidence the rules looked at
- **`failed`**: unreadable, unsupported or duplicate files, with the reason

## Project layout

| File | Responsibility |
|---|---|
| `src/screener/config.py` | Every weight, point value, penalty, threshold and GitHub tier, plus model name and keys from env. Checked at startup. No logic. |
| `src/screener/keywords.py` | Skill taxonomy: one regex per term, in groups checked against a known list (a typo fails at startup) |
| `src/screener/ingest.py` | File discovery, PDF (text + link annotations) / DOCX / TXT extraction, hashing |
| `src/screener/parser.py` | Sections, name/email/GitHub, project/experience entries and their names, evidence levels |
| `src/screener/eligibility.py` | Hard filter (rules only) |
| `src/screener/scoring.py` | 100-point model, penalties, cap, per-point evidence, summaries |
| `src/screener/github.py` | Async GitHub client (dedupe, cache, rate-limit circuit breaker) + scoring |
| `src/screener/llm.py` | Reviewer protocol, Anthropic adapter, quote verification, failure isolation |
| `src/screener/pipeline.py` | Orchestration, per-file failure isolation (worker processes with a timeout), ranking, batch summary |
| `src/screener/report.py` | JSON, HTML and console output |
| `main.py`, `src/screener/api.py` | CLI and FastAPI entry points |
| `tests/` | 79 tests: parser, eligibility, scoring, GitHub, LLM adapter, pipeline (including hanging and crashing files), API, real-layout regressions |

## Design Decisions

**Filtering (rules only, never the LLM).** It's a pass/fail gate, so it has to be predictable.
- **Python** passes on "Python" as a genuine skill, or on a Python-only framework used in a project or job. A generic "async" doesn't count. Lines like "currently learning Python" are ignored.
- **AI** passes on a named LLM/RAG/agentic framework or technique (LangChain, LangGraph, ADK, LlamaIndex, embeddings/vector search, tool calling, LLaMA/Mistral, …). These are deliberately not enough:
  - generic buzzwords ("AI", "LLMs", "prompt engineering")
  - classical ML (scikit-learn, CNNs, Hugging Face for vision models)
  - AI *coding assistants* (Cursor, Copilot, Claude Code), since using an assistant isn't building an AI system
- **JS/Java/React never cause a rejection** on their own.

**Scoring (deterministic, explainable).**
- **Evidence level.** Every keyword is graded by where it appears: *applied* in a project/job bullet ×1.0, *stack* in a project's tech list ×0.7, *listed* in a skills section ×0.35. This puts "prefer evidence over keyword lists" into practice.
- **AI depth (40)** is scored per project entry against the brief's list. It earns points for:
  - agent orchestration 7, tool calling 5, retrieval 8, state/memory 5, evaluation 5
  - guardrails 2, backend integration 3, data processing 1, production/business impact 3, framework 1
  - The best project counts in full and the second adds 25%, so two shallow projects don't equal one deep one.
- **Thin-wrapper penalty.** An entry that calls an LLM API (or uses wrapper wording like "chatbot") and has no retrieval, agents, state or evaluation loses 12 points if every AI project is like this, or 5 if some are.
- **Tutorial penalty.** −5 per tutorial-style or detail-free AI entry (YouTube/Udemy/guided labs, fewer than 12 words of detail). All penalties together are capped at −20.
- **No meaningful AI project → total capped at 30**, so strong Python developers who only list LangChain can't rank near the top.

**LLM usage (optional; Claude via the official SDK, model set in env).**
- **Eligible candidates only.** Rejected candidates don't need a quality judgement.
- **Structured output:** `messages.parse` with a Pydantic schema, plus server-side refusal fallback.
- **Limited influence.** The LLM only adjusts AI depth (50/50 blend with the rules, clamped 0–40) and adds summary, strengths and concerns. The other 60 points and eligibility stay deterministic.
- **Quotes are verified.** Every evidence quote must appear word for word in the resume, or it's dropped. A review with no surviving quotes is discarded. This guards against hallucination and against prompt injection hidden in a resume.
- **Failures never break the batch.** API errors, refusals and schema mismatches fall back to rules-only scoring for that resume. Results are cached by (model, file hash).
- **Provider-agnostic:** the provider sits behind a `ResumeReviewer` protocol.

**GitHub scoring (10).** Two public API calls per user: repos and public events. The split follows the brief's 5 + 5 suggestion.
- **Recent activity, 0–5:**
  - latest push: ≤30 days 3, ≤90 days 2, ≤365 days 1
  - distinct days with pushes/PRs in the last 90 days: ≥8 → 2, ≥2 → 1
- **Maintained & relevant repos, 0–5:**
  - original repos updated within a year: ≥3 → 2, ≥1 → 1
  - Python/AI-relevant ones: ≥4 → 3, ≥2 → 2, 1 → 1
- **Forks are ignored.** When a resume links several accounts, the first one that exists is used.
- **Missing, private, rate-limited or failed lookups score 0** and are recorded in `github_status` and concerns. They never cause a rejection.
- **Rate limiting.** The first rate-limit response stops further calls for the run.
- **Caching.** Lookups are de-duplicated within a run and cached on disk for 24 hours.

## If I Had More Time

1. **Calibrate on labelled data.** Have recruiters rank a held-out resume set, then tune the capability points, evidence multipliers and LLM blend weight against it (pairwise accuracy / NDCG). The current weights are hand-set, and the rules were tuned on this same dataset.
2. **Layout-aware parsing and OCR.** Use PyMuPDF block coordinates instead of line heuristics for multi-column resumes, and add OCR for image-only PDFs, which are currently reported as unreadable.
3. **LLM golden set in CI.** Build expected depth bands for ~30 resumes, check that the LLM and the rules agree, and run it before any prompt or model change. The LLM adapter is tested against a mocked API but hasn't been run against a live key.
4. **Project-to-repo matching.** Credit GitHub repos that match the resume's own projects, so the GitHub score verifies the claimed work instead of just measuring activity.

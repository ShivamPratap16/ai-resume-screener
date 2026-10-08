from html import escape
from pathlib import Path

from .models import ScreeningReport

CATEGORIES = [
    ("ai_project_depth", "AI depth", 40),
    ("python_backend", "Python/backend", 30),
    ("cloud_fullstack", "Cloud/full stack", 15),
    ("github", "GitHub", 10),
    ("engineering_depth", "Engineering", 5),
]


def mask_email(email: str | None) -> str | None:
    """'jane.doe@gmail.com' -> 'j***@gmail.com': proves extraction worked without exposing the address."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def redact_emails(report: ScreeningReport) -> ScreeningReport:
    redacted = report.model_copy(deep=True)
    for candidate in [*redacted.ranked, *redacted.rejected]:
        candidate.email = mask_email(candidate.email)
    return redacted


def write_json(report: ScreeningReport, output: Path, redact: bool = False) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text((redact_emails(report) if redact else report).model_dump_json(indent=2), encoding="utf-8")


def console_summary(report: ScreeningReport, top: int = 10) -> str:
    s = report.summary
    lines = [
        f"Files: {s.total_files} | parsed: {s.parsed} | eligible: {s.eligible} | rejected: {s.rejected} "
        f"| failed: {s.failed} | duplicates: {s.duplicates} | GitHub enriched: {s.github_enriched} "
        f"| LLM reviewed: {s.llm_reviewed} | {s.duration_s}s",
        "",
        f"{'#':>3}  {'Candidate':<24} {'Total':>5}  {'AI':>4} {'Py':>4} {'Cloud':>5} {'GH':>4} {'Eng':>4} {'Pen':>5}",
    ]
    for c in report.ranked[:top]:
        b = c.score_breakdown
        lines.append(
            f"{c.rank:>3}  {c.candidate_name[:24]:<24} {c.total_score:>5.1f}  {b.ai_project_depth:>4.1f} "
            f"{b.python_backend:>4.1f} {b.cloud_fullstack:>5.1f} {b.github:>4.1f} {b.engineering_depth:>4.1f} {b.penalties:>5.1f}"
        )
    return "\n".join(lines)


def _list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>" if items else "<p class=muted>None</p>"


def _bar(value: float, maximum: int) -> str:
    pct = max(0.0, min(100.0, 100 * value / maximum))
    return f'<span class=bar title="{value:g}/{maximum}"><span style="width:{pct:.0f}%"></span></span> {value:g}'


def _candidate_row(c) -> str:
    b, ev = c.score_breakdown, c.score_evidence
    bars = "".join(f"<td>{_bar(getattr(b, key), maximum)}</td>" for key, _, maximum in CATEGORIES)
    details = "".join(
        f"<h4>{label} ({getattr(b, key):g}/{maximum})</h4>{_list(getattr(ev, key))}" for key, label, maximum in CATEGORIES
    ) + f"<h4>Penalties ({b.penalties:g})</h4>{_list(ev.penalties)}"
    github = f'<a href="{escape(c.github_url)}">{escape(c.github_url)}</a>' if c.github_url else "—"
    return f"""
<tr>
  <td class=num>{c.rank}</td><td><strong>{escape(c.candidate_name)}</strong><br><span class=muted>{escape(c.file)}</span></td>
  <td class=num><strong>{c.total_score:g}</strong></td>{bars}<td class=num>{b.penalties:g}</td>
</tr>
<tr class=detail><td></td><td colspan=8>
  <p>{escape(c.project_summary)}</p>
  <details><summary>Why this score</summary>
    <div class=cols>
      <div>{details}</div>
      <div><h4>Strengths</h4>{_list(c.strengths)}<h4>Concerns</h4>{_list(c.concerns)}
      <h4>Resume evidence</h4>{_list(c.evidence)}<h4>GitHub</h4><p>{github}<br>{escape(c.github_summary)}</p>
      <h4>Matched skills</h4><p>{escape(", ".join(c.matched_skills))}</p></div>
    </div>
  </details>
</td></tr>"""


def write_html(report: ScreeningReport, output: Path) -> None:
    s = report.summary
    stats = "".join(
        f"<div class=stat><span>{value}</span>{label}</div>"
        for label, value in [("files", s.total_files), ("parsed", s.parsed), ("eligible", s.eligible),
                             ("rejected", s.rejected), ("failed", s.failed), ("duplicates", s.duplicates),
                             ("GitHub enriched", s.github_enriched), ("LLM reviewed", s.llm_reviewed)]
    )
    headers = "".join(f"<th>{label}</th>" for _, label, _ in CATEGORIES)
    ranked = "".join(_candidate_row(c) for c in report.ranked)
    rejected = "".join(
        f"<tr><td>{escape(c.candidate_name)}<br><span class=muted>{escape(c.file)}</span></td>"
        f"<td>{escape('; '.join(c.rejection_reasons))}</td><td>{escape(', '.join(c.matched_skills[:10]))}</td></tr>"
        for c in report.rejected
    )
    failed = "".join(f"<tr><td>{escape(f.file)}</td><td>{escape(f.status)}</td><td>{escape(f.error)}</td></tr>" for f in report.failed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">
<title>Resume Screening Report</title>
<style>
:root {{ --bg:#fafaf9; --fg:#1c1917; --muted:#78716c; --line:#e7e5e4; --accent:#2563eb; --card:#fff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1c1917; --fg:#f5f5f4; --muted:#a8a29e; --line:#44403c; --accent:#60a5fa; --card:#292524; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.5 system-ui, sans-serif; margin:0; padding:24px 16px; }}
main {{ max-width:1200px; margin:auto; }}
h1 {{ margin:0 0 4px; }} h2 {{ margin-top:32px; }} h4 {{ margin:12px 0 4px; }}
.muted {{ color:var(--muted); font-size:12px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:8px; margin:16px 0; }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:8px 14px; color:var(--muted); }}
.stat span {{ display:block; font-size:22px; font-weight:600; color:var(--fg); }}
.table-wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; background:var(--card); }}
th, td {{ border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }}
tr.detail td {{ border-bottom:2px solid var(--line); padding-top:0; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.bar {{ display:inline-block; width:60px; height:8px; background:var(--line); border-radius:4px; vertical-align:middle; }}
.bar span {{ display:block; height:100%; background:var(--accent); border-radius:4px; }}
.cols {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:16px; }}
ul {{ margin:0; padding-left:18px; }} summary {{ cursor:pointer; color:var(--accent); }}
</style></head><body><main>
<h1>Resume Screening Report</h1>
<p class=muted>Ranked by total score (100 + penalties). Expand "Why this score" for the evidence behind every point. Run took {s.duration_s}s.</p>
<div class=stats>{stats}</div>
<h2>Ranked candidates</h2>
<div class=table-wrap><table><tr><th>#</th><th>Candidate</th><th>Total</th>{headers}<th>Penalty</th></tr>{ranked}</table></div>
<h2>Rejected ({s.rejected})</h2>
<div class=table-wrap><table><tr><th>Candidate</th><th>Reasons</th><th>Matched skills</th></tr>{rejected}</table></div>
<h2>Failed / duplicate files ({s.failed + s.duplicates})</h2>
<div class=table-wrap><table><tr><th>File</th><th>Status</th><th>Error</th></tr>{failed or '<tr><td colspan=3 class=muted>None</td></tr>'}</table></div>
</main></body></html>
""", encoding="utf-8")

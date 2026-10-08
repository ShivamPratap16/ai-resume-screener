import re
from pathlib import Path

from .keywords import ACTION_VERBS, AI_CODING_TOOL_CUES, AI_QUALIFYING_GROUPS, NOT_GENUINE_CUES, TERMS, Term
from .models import LEVEL_RANK, Block, Evidence, EvidenceLevel, ParsedResume

SECTION_ALIASES = {
    "skills": [
        "skills", "technical skills", "tech stack", "technologies", "tools & technologies",
        "tools and technologies", "core competencies", "programming languages", "skills & tools",
        "technical expertise", "skill set", "skills summary", "key skills",
    ],
    "projects": [
        "projects", "personal projects", "academic projects", "key projects", "side projects",
        "selected projects", "project work", "project experience", "notable projects",
        "open source", "open source contributions", "things i've built", "what i've built",
    ],
    "experience": [
        "experience", "work experience", "professional experience", "internships", "internship",
        "internship experience", "employment", "work history", "industry experience",
        "relevant experience", "employment history",
    ],
    "education": ["education", "academics", "academic background", "qualifications"],
    "summary": ["summary", "objective", "profile", "about", "about me", "professional summary", "career objective"],
    "other": [
        "achievements", "certifications", "publications", "awards", "extracurricular",
        "extracurricular activities", "hobbies", "interests", "positions of responsibility",
        "leadership", "languages", "activities", "honors", "volunteering", "references",
        "languages known", "contact", "get in touch", "coursework", "relevant coursework",
    ],
}
_HEADING_LOOKUP = {alias: section for section, aliases in SECTION_ALIASES.items() for alias in aliases}
WORK_SECTIONS = ("experience", "projects")

# Includes the Unicode private-use range: symbol-font bullets from Word/LaTeX exports land there.
BULLET_RE = re.compile(r"^\s*[•●▪◦‣∙·■□➢➤►✓✔❖◆\ue000-\uf8ff\-\*–—»>]\s*")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")
GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))", re.IGNORECASE)
GITHUB_RESERVED = {"features", "topics", "about", "orgs", "settings", "marketplace", "explore", "sponsors", "login"}
DATE_RE = re.compile(r"\b(?:19|20)\d{2}\b|\bpresent\b", re.IGNORECASE)
STACK_LABEL_RE = re.compile(r"^\s*(?:tech(?:nologies|nology)?(?:\s*stack)?|stack|tools|built with|skills used|languages)\s*[:\-–]\s*", re.IGNORECASE)
MONTHS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
DATE_ONLY_RE = re.compile(
    rf"^[\s()\[\]\d/.,–—-]*(?:(?:{MONTHS}|present|current|to|till|now|\d{{1,4}})[\s()\[\]/.,–—-]*)+$", re.IGNORECASE
)
LABEL_RE = re.compile(r"^\s*[A-Za-z /&]{2,30}:\s*")


def parse_resume(path: Path, text: str, file_hash: str) -> ParsedResume:
    lines = _join_lone_bullets([line for line in map(_clean, text.splitlines()) if line])
    sections = split_sections(lines)
    has_sections = any(key != "header" for key in sections)
    return ParsedResume(
        file=path.name,
        file_hash=file_hash,
        text="\n".join(lines),
        name=extract_name(text.splitlines(), path),
        email=_first(EMAIL_RE, text),
        phone=_first(PHONE_RE, text),
        github_usernames=extract_github_usernames(text),
        sections=sections,
        blocks=split_blocks(sections),
        evidence=collect_evidence(sections, has_sections),
    )


def _clean(line: str) -> str:
    line = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", line).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", line).strip()


def _join_lone_bullets(lines: list[str]) -> list[str]:
    """Some PDFs put the bullet glyph on its own line; attach it to the text that follows."""
    joined, pending = [], False
    for line in lines:
        if BULLET_RE.fullmatch(line):
            pending = True
            continue
        joined.append(f"• {line}" if pending else line)
        pending = False
    return joined


def _first(pattern: re.Pattern, text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def heading_of(line: str) -> tuple[str | None, str]:
    """Return (section, inline_remainder) if the line is a section heading."""
    head, _, rest = line.partition(":")
    for candidate, remainder in ((line, ""), (head, rest.strip())):
        key = re.sub(r"[^a-z&' ]", "", candidate.lower()).strip()
        # "Certifications & Professional Development" -> "certifications"
        first = re.split(r"\s(?:&|and)\s", key)[0].strip()
        for k in (key, first):
            if k in _HEADING_LOOKUP and len(candidate) <= 45:
                return _HEADING_LOOKUP[k], remainder
    return None, ""


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in lines:
        section, remainder = heading_of(BULLET_RE.sub("", line))
        if section:
            current = section
            sections.setdefault(current, [])
            if remainder:
                sections[current].append(remainder)
        else:
            sections[current].append(line)
    return sections


NAME_STOPWORDS = {
    "resume", "curriculum", "vitae", "linkedin", "github", "leetcode", "email", "mobile", "phone",
    "portfolio", "career", "aspiration", "contact", "profile", "summary", "engineer", "developer",
}


def _name_candidates(raw_lines: list[str]):
    lines = [line.strip() for line in raw_lines if line.strip()][:8]
    for i, line in enumerate(lines):
        yield from re.split(r"\s{3,}|\s[|•·—–]\s", line)
        # Some templates put first and last name on separate lines.
        if i + 1 < len(lines) and len(line.split()) == 1 and len(lines[i + 1].split()) == 1:
            yield f"{line} {lines[i + 1]}"


def extract_name(raw_lines: list[str], path: Path) -> str:
    """First short run of capitalised words near the top; headers often share a line with contact columns."""
    for chunk in _name_candidates(raw_lines):
        words = _clean(chunk).split()
        if (
            2 <= len(words) <= 4
            and all(re.fullmatch(r"[A-Z][A-Za-z.'-]*", w) for w in words)
            and not NAME_STOPWORDS.intersection(w.lower().strip(".") for w in words)
            and not heading_of(" ".join(words))[0]
        ):
            return " ".join(w.capitalize() if w.isupper() and w.isalpha() and len(w) > 2 else w for w in words)
    return re.sub(r"[_\-]+", " ", path.stem).strip().title()


def extract_github_usernames(text: str) -> list[str]:
    usernames: list[str] = []
    for match in GITHUB_RE.finditer(text):
        username = match.group(1).rstrip("-")
        if username.lower() not in GITHUB_RESERVED and username.lower() not in map(str.lower, usernames):
            usernames.append(username)
    return usernames


def extract_github_username(text: str) -> str | None:
    usernames = extract_github_usernames(text)
    return usernames[0] if usernames else None


def is_list_line(line: str) -> bool:
    line = BULLET_RE.sub("", line)
    body = STACK_LABEL_RE.sub("", line)
    labelled = body != line or bool(LABEL_RE.match(line))
    body = LABEL_RE.sub("", body)
    items = [item.strip() for item in re.split(r"[,|;•/]", body) if item.strip()]
    if ACTION_VERBS.search(body) and not labelled:
        return False
    if labelled and len(items) >= 1:
        return True
    return len(items) >= 3 and sum(len(i.split()) for i in items) / len(items) <= 3


def is_block_title(line: str, after_bullet: bool = False, after_sentence: bool = False) -> bool:
    if BULLET_RE.match(line) or LABEL_RE.match(line) or line[:1].islower():
        return False
    words = line.split()
    if "|" in line or " — " in line or " – " in line or DATE_RE.search(line):
        return len(words) <= 18
    # Right after a bullet, a short fragment is far more likely a wrapped continuation.
    if after_bullet and len(words) < 2:
        return False
    capitalised = sum(1 for w in words if w[:1].isupper() or not w[:1].isalpha())
    # After a finished sentence a capitalised line is rarely a continuation, so allow longer titles.
    max_words = 12 if after_sentence else 8
    return len(words) <= max_words and capitalised / len(words) >= 0.6 and not line.endswith(".")


def split_blocks(sections: dict[str, list[str]]) -> list[Block]:
    blocks: list[Block] = []
    for section in WORK_SECTIONS:
        current: Block | None = None
        in_bullet = False
        for line in sections.get(section, []):
            if current is not None and current.lines and current.lines[-1].endswith((",", "&", "+", "/")):
                current.lines[-1] += " " + line
            elif current is not None and current.lines and DATE_ONLY_RE.match(line) and is_block_title(current.lines[-1], after_sentence=True):
                # The role line was read as the end of the previous entry; the date line shows it starts a new one.
                role = current.lines.pop()
                if current.lines:
                    current = Block(section=section, title=f"{role} | {line}")
                    blocks.append(current)
                else:
                    current.title += f" | {role} | {line}"
                in_bullet = False
            elif current is not None and not current.lines and is_block_title(line):
                # Role / company / date / location stacked on separate lines form one entry header.
                current.title += " | " + line
            elif current is None or is_block_title(
                line, after_bullet=in_bullet, after_sentence=bool(current.lines) and current.lines[-1].endswith(".")
            ):
                current = Block(section=section, title=BULLET_RE.sub("", line))
                blocks.append(current)
                in_bullet = False
            elif BULLET_RE.match(line) or not in_bullet or not current.lines:
                current.lines.append(BULLET_RE.sub("", line))
                in_bullet = bool(BULLET_RE.match(line))
            else:
                current.lines[-1] += " " + line
    return blocks


STACK_IN_PARENS_RE = re.compile(r"\s*\([^)]*,[^)]*\)")
LOCATION_RE = re.compile(r"^(?:remote|on-?site|hybrid|[A-Z][a-z]+,\s*[A-Z][a-z]+)$", re.IGNORECASE)
LINK_LABEL_RE = re.compile(r"^\[?(github|live|live demo|demo|link|code|website|source)\]?$", re.IGNORECASE)


def clip(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _name_part(text: str) -> str:
    """'SmartATS: Developed an AI-powered screener ...' -> 'SmartATS'; short 'Project 1: Travel Agent' is kept whole."""
    text = STACK_IN_PARENS_RE.sub("", text)
    head, sep, tail = text.partition(":")
    if sep and len(head.split()) <= 6 and len(tail.split()) > 8:
        return head.strip()
    return text.strip(" :")


def entry_name(block: Block) -> str:
    """'Role | Jun 2025 - Present | Company | City' -> 'Role — Company'; drops dates, links and stack lists."""
    parts = [_name_part(p) for p in re.split(r"\s*\|\s*|\s[—–]\s", block.title)]
    keep = [
        p for p in parts
        if p and not DATE_RE.search(p) and not LINK_LABEL_RE.match(p) and not LOCATION_RE.match(p) and not is_list_line(p)
    ]
    if not keep and block.lines:
        keep = [_name_part(block.lines[0])]
    if not keep:
        return f"{block.section.title()} entry ({clip(block.title, 40)})"
    return clip(" — ".join(keep[:2]), 90)


def match_terms(text: str) -> list[Term]:
    return [term for term in TERMS if term.pattern.search(text)]


def _level_for(section: str, line: str, has_sections: bool) -> EvidenceLevel:
    if section == "skills":
        return EvidenceLevel.LISTED
    if section in WORK_SECTIONS:
        return EvidenceLevel.STACK if is_list_line(line) else EvidenceLevel.APPLIED
    # Resumes without recognisable headings: trust sentences that describe work.
    if not has_sections and not is_list_line(line) and ACTION_VERBS.search(line):
        return EvidenceLevel.APPLIED
    return EvidenceLevel.LISTED


def collect_evidence(sections: dict[str, list[str]], has_sections: bool) -> dict[str, Evidence]:
    evidence: dict[str, Evidence] = {}
    for section, lines in sections.items():
        for line in lines:
            if NOT_GENUINE_CUES.search(line):
                continue
            level = _level_for(section, line, has_sections)
            coding_tool_line = bool(AI_CODING_TOOL_CUES.search(line))
            for term in match_terms(line):
                if coding_tool_line and AI_QUALIFYING_GROUPS.intersection(term.groups):
                    continue
                existing = evidence.get(term.name)
                if existing is None or LEVEL_RANK[level] > LEVEL_RANK[existing.level]:
                    evidence[term.name] = Evidence(
                        term=term.name, groups=list(term.groups), level=level, snippet=BULLET_RE.sub("", line)[:200]
                    )
    return evidence

from screener.models import EvidenceLevel
from screener.parser import split_blocks, split_sections

from conftest import STRONG_AGENTIC, make_resume


def test_extracts_contact_details_and_github():
    resume = make_resume(STRONG_AGENTIC)
    assert resume.name == "Asha Rao"
    assert resume.email == "asha.rao@example.com"
    assert resume.github_username == "asha-rao-dev"


def test_section_aliases_are_recognised():
    sections = split_sections(["Jane Doe", "Tech Stack", "Python", "Things I've Built", "Bot", "Internships", "Intern"])
    assert sections["skills"] == ["Python"]
    assert sections["projects"] == ["Bot"]
    assert sections["experience"] == ["Intern"]


def test_inline_heading_keeps_its_content():
    assert split_sections(["SKILLS: Python, Flask"])["skills"] == ["Python, Flask"]


def test_evidence_level_depends_on_where_keyword_appears():
    resume = make_resume(STRONG_AGENTIC)
    assert resume.evidence["LangGraph"].level == EvidenceLevel.APPLIED
    assert resume.evidence["GCP"].level == EvidenceLevel.APPLIED
    skills_only = make_resume("Jane Doe\nSKILLS\nPython, LangChain, Docker\n")
    assert skills_only.evidence["LangChain"].level == EvidenceLevel.LISTED


def test_project_tech_stack_line_is_stack_level():
    resume = make_resume("Jane Doe\nPROJECTS\nBot\nTech: Python, LangChain, FAISS\n- Answers questions\n")
    assert resume.evidence["FAISS"].level == EvidenceLevel.STACK


def test_wrapped_bullet_continuation_is_not_a_new_project():
    blocks = split_blocks({"projects": [
        "Support Copilot | Python",
        "• Built an agent with tool calling against order and refund",
        "APIs",
        "• Added caching",
    ]})
    assert len(blocks) == 1
    assert blocks[0].lines[0].endswith("refund APIs")


def test_aspirational_mentions_are_not_evidence():
    resume = make_resume("Jane Doe\nSUMMARY\nCurrently learning Python for backend work.\nSKILLS\nReact\n")
    assert "Python" not in resume.evidence


def test_java_is_not_matched_inside_javascript():
    assert "Java" not in make_resume("Jane Doe\nSKILLS\nJavaScript, TypeScript\n").evidence


def test_bulleted_tools_label_line_is_stack_level():
    resume = make_resume("Jane Doe\nPROJECTS\nResearch Agent\n• Tools Used: Python LangGraph ChromaDB FastAPI\n• Answers questions\n")
    assert resume.evidence["LangGraph"].level == EvidenceLevel.STACK

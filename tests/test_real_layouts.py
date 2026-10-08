"""Regressions found while running the provided 50-resume dataset."""
from pathlib import Path

from screener.eligibility import check_eligibility
from screener.models import Block
from screener.parser import entry_name, extract_name, heading_of, split_blocks
from screener.scoring import analyse_ai_blocks

from conftest import make_resume


def test_ai_coding_assistants_are_not_ai_project_evidence():
    text = """
    Asha Verma
    SKILLS
    Python, Java, Node.js
    EXPERIENCE
    QA Intern | 2025
    - Automated SAP test workflows using Claude Code, Cursor and Playwright
    - Automated backend workflows using AI tools (Cursor, LLMs)
    """
    result = check_eligibility(make_resume(text))
    assert not result.eligible


def test_generic_async_is_not_python_evidence():
    text = """
    Rohit Sen
    PROJECTS
    ResumeAI | Node.js, React, Redis, OpenAI API
    - Designed an async job queue using BullMQ and Redis
    """
    assert check_eligibility(make_resume(text)).rejection_reasons == ["No evidence of Python stack"]


def test_hugging_face_for_cv_model_is_not_llm_evidence():
    text = """
    Dev Malhotra
    PROJECTS
    Plant Classifier | Python, TensorFlow
    - Deployed the final CNN model on Hugging Face for real-time image classification
    """
    assert not check_eligibility(make_resume(text)).eligible


def test_open_weight_llms_count_as_ai_evidence():
    text = """
    Leena Joseph
    PROJECTS
    AutoEval | Python, Django, FastAPI
    - Integrated LLaMA for automated evaluation and personalized feedback generation
    """
    assert check_eligibility(make_resume(text)).eligible


def test_stacked_role_company_date_lines_form_one_entry():
    blocks = split_blocks({"experience": [
        "Software Engineer Intern", "June 2025 - Present", "AI Assistant", "Pune",
        "– Built an automated agent QA framework with LLM-to-LLM test modes",
        "Python Developer Intern", "Dec 2024", "– Built a Flask notification service",
    ]})
    assert [b.title for b in blocks] == [
        "Software Engineer Intern | June 2025 - Present | AI Assistant | Pune",
        "Python Developer Intern | Dec 2024",
    ]


def test_labelled_lines_and_comma_wraps_stay_inside_the_project():
    blocks = split_blocks({"experience": [
        "Project 1: Multi-Agent Travel Planner — LangGraph",
        "◆ Agentic Travel Planning System",
        "Role: GenAI Developer",
        "Technology Stack: Python, LangGraph, Docker,",
        "AWS EKS",
        "• Designed an agentic planner with LangGraph checkpointers",
    ]})
    assert len(blocks) == 1 and len(blocks[0].lines) == 2


def test_names_from_multi_column_and_split_headers():
    path = Path("candidate_99.pdf")
    assert extract_name(["Kunal Desai                       Email: v@example.com"], path) == "Kunal Desai"
    assert extract_name(["Meghana", "Rao", "+91 90000 00000"], path) == "Meghana Rao"
    assert extract_name(["Motivated MCA graduate with skills", "contribute to innovative projects."], path) == "Candidate 99"


def test_compound_headings_are_recognised():
    assert heading_of("CERTIFICATIONS & PROFESSIONAL DEVELOPMENT")[0] == "other"


def test_long_role_line_after_finished_bullet_starts_new_entry():
    blocks = split_blocks({"experience": [
        "Software Engineer Intern | Jan 2025 – Jun 2025",
        "• Built dashboards to track p95 latency for product stakeholders.",
        "AI & Cloud Computing Intern, Brightpath Technology Pvt Ltd",
        "Nov 2025 – Mar 2026",
        "• Engineered a multi-agent RAG platform with LangGraph",
    ]})
    assert blocks[1].title == "AI & Cloud Computing Intern, Brightpath Technology Pvt Ltd | Nov 2025 – Mar 2026"


def test_research_without_llm_api_is_not_a_thin_wrapper(cfg):
    text = """
    Sana Qureshi
    PROJECTS
    Plagiarism Detection for LLMs through Watermarking, Dissertation 2024
    - Enhanced an AI content detection system using watermarking for LLMs, improving detection accuracy by 40%.
    """
    assert not any(b.thin_wrapper for b in analyse_ai_blocks(make_resume(text), cfg))


def test_llm_chatbot_bolted_onto_app_is_a_thin_wrapper(cfg):
    text = """
    Tarun Bhatt
    PROJECTS
    AI Car Rental Platform
    - Built a MERN car rental platform with real-time booking and token-based authentication for 50+ vehicles.
    - Added an LLM-powered chatbot to assist users with booking questions.
    """
    assert all(b.thin_wrapper for b in analyse_ai_blocks(make_resume(text), cfg))


def test_entry_name_drops_dates_locations_and_links():
    block = Block(section="experience", title="Acme HR – Hyderabad, India | SDE-1 | 07/2025 – 04/2026")
    assert entry_name(block) == "Acme HR — SDE-1"
    assert entry_name(Block(section="projects", title="AI Research Copilot (LangGraph) | GitHub")) == "AI Research Copilot (LangGraph)"


def test_bullet_glyph_on_its_own_line_is_attached_to_next_line():
    resume = make_resume("Jane Doe\nPROJECTS\nTelemetry RAG | Python\n●\nBuilt automated telemetry ingestion pipelines — no custom agents\n")
    assert len(resume.blocks) == 1 and resume.blocks[0].lines[0].startswith("Built automated")


def test_zero_width_characters_are_removed():
    resume = make_resume("Jane Doe\nEXPERIENCE\nAI Engineer\u200b | Northwind Labs\n- Built an agent\n")
    assert resume.blocks[0].title == "AI Engineer | Northwind Labs"


def test_company_role_and_date_on_separate_lines_stay_one_entry():
    blocks = split_blocks({"experience": [
        "Contoso | Hyderabad, India",
        "Software Engineering Intern (Python, FastAPI, React, TypeScript, Docker, GCP)",
        "Oct 2025 to Apr 2026",
        "• Designed prompt architectures for a multi-agent document-generation system",
    ]})
    assert len(blocks) == 1
    assert entry_name(blocks[0]) == "Contoso — Software Engineering Intern"


def test_ui_state_is_not_agent_state(cfg):
    text = """
    Neel Kapoor
    EXPERIENCE
    Frontend Developer Intern | 2025
    - Built AI-powered learning features with agentic chat for homework queries using OpenAI
    - Implemented custom caching for auth state, wallet balances, and notifications
    """
    caps = analyse_ai_blocks(make_resume(text), cfg)[0].capabilities
    assert "state/memory" not in caps


def test_agent_state_phrasings_count(cfg):
    for line in [
        "Orchestrated agents on a LangGraph StateGraph with a supervisor",
        "Implemented stateful conversation management using LangGraph checkpointers",
        "Built session-based conversational memory for an LLM assistant",
        "Used Redis-backed state management to preserve API responses across agent steps",
    ]:
        resume = make_resume(f"Jane Doe\nPROJECTS\nAgent | Python, LangChain\n- {line}\n")
        assert "state/memory" in analyse_ai_blocks(resume, cfg)[0].capabilities, line

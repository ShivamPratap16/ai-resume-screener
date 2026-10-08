from screener.eligibility import check_eligibility

from conftest import JAVA_REACT_ONLY, SKILLS_ONLY_AI, STRONG_AGENTIC, THIN_WRAPPER, make_resume


def test_python_and_agentic_project_is_eligible():
    result = check_eligibility(make_resume(STRONG_AGENTIC))
    assert result.eligible
    assert result.python_evidence and result.ai_evidence


def test_java_react_only_profile_is_rejected_for_both_reasons():
    result = check_eligibility(make_resume(JAVA_REACT_ONLY))
    assert not result.eligible
    assert result.rejection_reasons == ["No evidence of Python stack", "No AI/agentic project evidence"]


def test_javascript_alongside_python_and_ai_is_not_rejected():
    text = STRONG_AGENTIC + "\nOTHER\nAlso comfortable with React, Next.js and Java.\n"
    assert check_eligibility(make_resume(text)).eligible


def test_ai_project_without_python_is_rejected():
    text = """
    Kabir Shah
    SKILLS
    TypeScript, Next.js, LangChain.js
    PROJECTS
    Code Reviewer | Next.js, LangChain.js
    - Built agents with tool calling to review pull requests
    """
    assert check_eligibility(make_resume(text)).rejection_reasons == ["No evidence of Python stack"]


def test_python_only_as_learning_goal_is_rejected():
    text = """
    Meera Joshi
    SUMMARY
    TypeScript developer. Currently learning Python.
    PROJECTS
    Code Reviewer | Next.js, LangChain.js
    - Built agents with tool calling to review pull requests
    """
    result = check_eligibility(make_resume(text))
    assert not result.eligible
    assert "being learned" in result.rejection_reasons[0]


def test_python_backend_without_ai_is_rejected():
    text = """
    Priya Reddy
    SKILLS
    Python, Django, PostgreSQL
    PROJECTS
    Inventory API | Python, Django
    - Developed REST APIs for stock tracking
    """
    assert check_eligibility(make_resume(text)).rejection_reasons == ["No AI/agentic project evidence"]


def test_classical_ml_alone_does_not_count_as_ai_evidence():
    text = """
    Arjun Rao
    SKILLS
    Python, scikit-learn, pandas, PyTorch
    PROJECTS
    Plant Classifier | PyTorch
    - Trained a ResNet CNN on 50k leaf images
    """
    result = check_eligibility(make_resume(text))
    assert not result.eligible
    assert "classical ML" in result.rejection_reasons[0]


def test_generic_llm_buzzword_in_skills_is_not_enough():
    assert not check_eligibility(make_resume("Jane Doe\nSKILLS\nPython, LLMs, AI, Machine Learning\n")).eligible


def test_named_framework_in_skills_passes_the_minimum_bar():
    assert check_eligibility(make_resume(SKILLS_ONLY_AI)).eligible


def test_thin_wrapper_passes_eligibility_and_is_handled_by_scoring():
    assert check_eligibility(make_resume(THIN_WRAPPER)).eligible

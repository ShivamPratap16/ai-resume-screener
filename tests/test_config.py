import pytest

from screener import scoring
from screener.config import ScoringConfig
from screener.keywords import AI_QUALIFYING_GROUPS, ENGINEERING_GROUPS, KNOWN_GROUPS, TERMS, _t


def test_unknown_keyword_group_fails_at_definition():
    with pytest.raises(ValueError, match="bakend"):
        _t("Typo", "python bakend", r"\btypo\b")


def test_every_group_referenced_by_scoring_exists():
    referenced = set(AI_QUALIFYING_GROUPS) | set(ENGINEERING_GROUPS) | scoring.HIDDEN_SKILL_GROUPS
    referenced |= {g for groups in scoring.AI_CAPABILITIES.values() for g in groups}
    assert referenced <= KNOWN_GROUPS, referenced - KNOWN_GROUPS


def test_every_term_referenced_by_scoring_exists():
    names = {t.name for t in TERMS}
    referenced = set().union(*scoring.PYTHON_BACKEND_ITEMS.values(), *scoring.CLOUD_ITEMS.values(),
                             *scoring.OTHER_CLOUD_ITEMS.values(), scoring.FRONTEND_TERMS)
    assert referenced <= names, referenced - names


def test_config_points_cover_every_scoring_label():
    cfg = ScoringConfig()
    assert cfg.ai_capability_points.keys() == scoring.AI_CAPABILITIES.keys()
    assert cfg.python_backend_points.keys() == scoring.PYTHON_BACKEND_ITEMS.keys()
    assert cfg.cloud_points.keys() == scoring.CLOUD_ITEMS.keys() | scoring.OTHER_CLOUD_ITEMS.keys()


def test_ai_points_must_add_up_to_category_weight():
    with pytest.raises(ValueError, match="add up to"):
        ScoringConfig(ai_capability_points={"agent orchestration": 7})

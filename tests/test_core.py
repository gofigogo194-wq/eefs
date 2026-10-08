import pytest

from media_omega.models import CreativePlan, Decision
from media_omega.policy import Policy, verify


def approved_plan(**changes):
    values = dict(
        opportunity_id="o",
        platform="youtube",
        format="short",
        title="demo",
        original=True,
        rights_confirmed=True,
        estimated_cost=1.0,
    )
    values.update(changes)
    return CreativePlan(**values)


def test_plan_defaults_fail_closed_on_rights_and_originality():
    result = verify(CreativePlan("o", "youtube", "short", "demo"))
    assert result.decision is Decision.BLOCK
    assert "CONTENT_NOT_ORIGINAL" in result.reasons
    assert "RIGHTS_NOT_CONFIRMED" in result.reasons


def test_policy_fails_closed_on_rights():
    result = verify(approved_plan(rights_confirmed=False))
    assert result.decision is Decision.BLOCK
    assert "RIGHTS_NOT_CONFIRMED" in result.reasons


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("opportunity_id", "OPPORTUNITY_ID_REQUIRED"),
        ("platform", "PLATFORM_REQUIRED"),
        ("format", "FORMAT_REQUIRED"),
        ("title", "TITLE_REQUIRED"),
    ],
)
def test_policy_rejects_missing_plan_identity(field, reason):
    result = verify(approved_plan(**{field: ""}))
    assert result.decision is Decision.BLOCK
    assert reason in result.reasons


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), -1.0, 26.0])
def test_policy_rejects_invalid_or_excessive_cost(cost):
    result = verify(approved_plan(estimated_cost=cost))
    assert result.decision is Decision.BLOCK
    assert "BUDGET_POLICY_FAILED" in result.reasons


def test_policy_configuration_is_validated():
    with pytest.raises(ValueError):
        verify(approved_plan(), Policy(max_cost=float("inf")))
    with pytest.raises(ValueError):
        verify(approved_plan(), Policy(allowed_platforms=()))




@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"original": "yes"}, "CONTENT_NOT_ORIGINAL"),
        ({"rights_confirmed": 1}, "RIGHTS_NOT_CONFIRMED"),
        ({"estimated_cost": True}, "BUDGET_POLICY_FAILED"),
        ({"platform": None}, "PLATFORM_REQUIRED"),
        ({"metadata": []}, "METADATA_MUST_BE_OBJECT"),
        ({"id": ""}, "PLAN_ID_REQUIRED"),
    ],
)
def test_policy_rejects_wrong_runtime_types(changes, reason):
    result = verify(approved_plan(**changes))
    assert result.decision is Decision.BLOCK
    assert reason in result.reasons

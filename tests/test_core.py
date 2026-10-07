from media_omega.memory import DecisionJournal
from media_omega.models import CreativePlan, Decision
from media_omega.orchestrator import Orchestrator
from media_omega.policy import verify


def test_policy_fails_closed_on_rights():
    plan = CreativePlan("o", "youtube", "short", "demo", rights_confirmed=False)
    result = verify(plan)
    assert result.decision is Decision.BLOCK
    assert "RIGHTS_NOT_CONFIRMED" in result.reasons


def test_dry_run_never_claims_published(tmp_path):
    journal = DecisionJournal(tmp_path / "test.db")
    engine = Orchestrator(journal)
    plan = CreativePlan("o", "youtube", "short", "demo")
    receipt = engine.dry_run_publish(plan)
    assert receipt["dry_run"] is True
    assert receipt["published"] is False
    assert [x["event_type"] for x in journal.read_all()] == [
        "POLICY_DECISION",
        "DRY_RUN_PUBLICATION",
    ]

from media_omega.memory import DecisionJournal
from media_omega.models import CreativePlan, Decision, Opportunity
from media_omega.orchestrator import Orchestrator
from media_omega.policy import verify
from media_omega.scoring import score


def opp(topic="x", outlier=0.8, risk=0.1):
    return Opportunity("fixture", topic, outlier, 0.7, 0.6, 0.7, 0.5, 0.2, risk, ("fixture:1",))


def test_score_is_deterministic():
    a = opp()
    assert score(a).score == score(a).score


def test_score_rejects_bad_normalization():
    bad = opp(outlier=1.1)
    try:
        score(bad)
        assert False
    except ValueError:
        pass


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
    assert [x["event_type"] for x in journal.read_all()] == ["POLICY_DECISION", "DRY_RUN_PUBLICATION"]


def test_choose_records_ranking(tmp_path):
    journal = DecisionJournal(tmp_path / "test.db")
    engine = Orchestrator(journal)
    winner = engine.choose([opp("weak", 0.2), opp("strong", 0.9)])
    assert winner.opportunity.topic == "strong"
    assert journal.read_all()[0]["event_type"] == "RANKED"

from media_omega.intelligence import OpportunityCandidate
from media_omega.ranking import opportunity_score, rank_opportunities


def candidate(cid, outlier, acceleration, confidence, evidence=10):
    return OpportunityCandidate(
        cid, "youtube", outlier, acceleration, confidence, evidence, ()
    )


def test_ranking_prefers_strong_evidence_gated_signal():
    weak = candidate("weak", 20, 10, 0.1)
    strong = candidate("strong", 5, 4, 1.0)
    ranked = rank_opportunities([weak, strong])
    assert [x.content_id for x in ranked] == ["strong", "weak"]
    assert [x.rank for x in ranked] == [1, 2]


def test_score_never_rewards_negative_signal():
    c = candidate("x", -5, -2, 1.0)
    assert opportunity_score(c) == 0.0


def test_ranking_is_deterministic_on_tie():
    a = candidate("a", 2, 2, 0.5, evidence=5)
    b = candidate("b", 2, 2, 0.5, evidence=5)
    assert [x.content_id for x in rank_opportunities([b, a])] == ["a", "b"]

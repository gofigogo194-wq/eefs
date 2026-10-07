import pytest

from media_omega.scout import ScoutPolicy, ScoutTopic, choose_queries


def test_scout_balances_exploration_and_exploitation():
    known = [
        ScoutTopic("ambient sleep", prior_score=0.8),
        ScoutTopic("gaming news", prior_score=0.3),
        ScoutTopic("ai tools", prior_score=0.7),
    ]
    result = choose_queries(
        known,
        ["robotics", "travel hacks", "new music"],
        ScoutPolicy(query_budget=5, exploration_fraction=0.4),
    )
    assert len(result.queries) == 5
    assert result.explore_count == 2
    assert result.exploit_count == 3
    assert "ambient sleep" in result.queries


def test_scout_is_deterministic():
    args = (
        [ScoutTopic("a"), ScoutTopic("b")],
        ["x", "y", "z"],
        ScoutPolicy(query_budget=3, exploration_fraction=2/3),
    )
    assert choose_queries(*args) == choose_queries(*args)


def test_scout_uses_observed_success_without_discarding_prior():
    strong = ScoutTopic("strong", prior_score=0.5, observations=20, successes=18)
    weak = ScoutTopic("weak", prior_score=0.9, observations=20, successes=1)
    result = choose_queries([weak, strong], [], ScoutPolicy(query_budget=1, exploration_fraction=0))
    assert result.queries == ("strong",)


def test_scout_rejects_impossible_history():
    with pytest.raises(ValueError):
        choose_queries(
            [ScoutTopic("bad", observations=2, successes=3)],
            [],
            ScoutPolicy(query_budget=1, exploration_fraction=0),
        )


def test_scout_enforces_query_budget():
    with pytest.raises(ValueError):
        ScoutPolicy(query_budget=21).validate()

import importlib.util

from media_omega.orchestrator import Orchestrator


def test_duplicate_intelligence_brains_are_physically_retired():
    for module in (
        "media_omega.intelligence",
        "media_omega.evaluation",
        "media_omega.ranking",
        "media_omega.scoring",
    ):
        assert importlib.util.find_spec(module) is None


def test_orchestrator_exposes_only_canonical_live_selector():
    assert hasattr(Orchestrator, "choose_intelligence")
    assert not hasattr(Orchestrator, "choose")

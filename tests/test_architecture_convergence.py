import importlib.util

from media_omega.observations import ContentObservation
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


def test_legacy_outlier_and_relative_performance_brain_is_retired():
    import media_omega.observations as observations

    assert not hasattr(observations, "detect_outlier")
    assert not hasattr(observations, "OutlierSignal")
    assert not hasattr(ContentObservation, "relative_performance")


def test_duplicate_scout_cycle_module_is_retired():
    assert importlib.util.find_spec("media_omega.scout_cycle") is None


def test_duplicate_baseline_collection_pipeline_is_retired():
    assert importlib.util.find_spec("media_omega.baseline_collection") is None


def test_stale_youtube_observation_adapter_is_retired():
    import media_omega.youtube as youtube

    assert not hasattr(youtube, "YouTubeDataSource")

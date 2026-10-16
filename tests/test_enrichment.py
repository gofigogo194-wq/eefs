import pytest

from media_omega.discovery import DiscoveryItem
from media_omega.enrichment import enrich_statistics
from media_omega.memory import DecisionJournal


def item(i, creator="c"):
    return DiscoveryItem(
        "youtube", i, creator, f"title {i}",
        "2026-10-07T00:00:00+00:00",
        f"api://youtube/search/{i}",
    )


class FakeStats:
    def __init__(self, missing=None):
        self.calls = []
        self.missing = set(missing or [])

    def video_statistics(self, ids):
        self.calls.append(list(ids))
        return {i: 1000 + n for n, i in enumerate(ids) if i not in self.missing}


def test_enrichment_creates_auditable_observations(tmp_path):
    journal = DecisionJournal(tmp_path / "e.db")
    transport = FakeStats()
    observations, result = enrich_statistics(
        [item("a"), item("b")],
        transport,
        journal,
        "2026-10-07T01:00:00+00:00",
    )
    assert result.requested == 2
    assert result.enriched == 2
    assert result.missing == 0
    assert observations[0].creator_baseline_views == 0.0
    events = journal.read_all()
    assert [x["event_type"] for x in events].count("EVIDENCE") == 2
    assert events[-1]["event_type"] == "STATISTICS_ENRICHMENT"


def test_enrichment_deduplicates_and_tracks_missing(tmp_path):
    transport = FakeStats(missing={"b"})
    observations, result = enrich_statistics(
        [item("a"), item("a"), item("b")],
        transport,
        DecisionJournal(tmp_path / "e.db"),
        observed_at="2026-10-07T01:00:00+00:00",
    )
    assert result.requested == 2
    assert result.enriched == 1
    assert result.missing == 1
    assert [x.content_id for x in observations] == ["a"]


def test_enrichment_batches_youtube_limit(tmp_path):
    transport = FakeStats()
    items = [item(str(i)) for i in range(101)]
    observations, result = enrich_statistics(
        items,
        transport,
        DecisionJournal(tmp_path / "e.db"),
        observed_at="2026-10-07T01:00:00+00:00",
    )
    assert [len(call) for call in transport.calls] == [50, 50, 1]
    assert result.enriched == 101


def test_legacy_creator_baseline_field_is_never_fabricated(tmp_path):
    observations, result = enrich_statistics(
        [item("a")],
        FakeStats(),
        DecisionJournal(tmp_path / "e.db"),
        observed_at="2026-10-07T01:00:00+00:00",
    )
    assert result.enriched == 1
    assert observations[0].creator_baseline_views == 0.0


def test_enrichment_does_not_coerce_string_views_from_adapter(tmp_path):
    class BadStats:
        def video_statistics(self, ids):
            return {ids[0]: "1000"}

    with pytest.raises(ValueError, match="views must"):
        enrich_statistics(
            [item("a")],
            BadStats(),
            DecisionJournal(tmp_path / "e.db"),
            observed_at="2026-10-07T01:00:00+00:00",
        )

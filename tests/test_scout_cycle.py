from media_omega.discovery import DiscoveryPolicy
from media_omega.memory import DecisionJournal
from media_omega.scout import ScoutPolicy, ScoutTopic
from media_omega.scout_cycle import run_scout_cycle


class FakeTransport:
    def __init__(self):
        self.calls = []

    def discover_videos(self, query):
        self.calls.append(query)
        return [{
            "content_id": f"id-{query}",
            "creator_id": "creator",
            "title": f"Video about {query}",
            "published_at": "2026-10-07T00:00:00Z",
            "evidence_ref": f"api://youtube/search/id-{query}",
        }]


def test_cycle_wires_scout_to_discovery_and_journal(tmp_path):
    journal = DecisionJournal(tmp_path / "cycle.db")
    transport = FakeTransport()
    result = run_scout_cycle(
        transport,
        journal,
        [ScoutTopic("ambient", prior_score=0.9), ScoutTopic("ai", prior_score=0.8)],
        ["robotics"],
        ScoutPolicy(query_budget=2, exploration_fraction=0.5),
        DiscoveryPolicy(max_candidates=10),
    )
    assert result.mode == "read-only"
    assert len(result.queries) == 2
    assert result.discovered_count == 2
    assert result.selected_count == 2
    assert transport.calls == list(result.queries)
    event_types = [event["event_type"] for event in journal.read_all()]
    assert event_types[0] == "SCOUT_DECISION"
    assert event_types.count("DISCOVERY_QUERY") == 2
    assert event_types[-1] == "SCOUT_CYCLE_RESULT"


def test_cycle_deduplicates_same_video_across_queries(tmp_path):
    class DuplicateTransport:
        def discover_videos(self, query):
            return [{
                "content_id": "same",
                "creator_id": "creator",
                "title": "Same emerging video",
                "published_at": "2026-10-07T00:00:00Z",
                "evidence_ref": "api://youtube/search/same",
            }]

    result = run_scout_cycle(
        DuplicateTransport(),
        DecisionJournal(tmp_path / "cycle.db"),
        [ScoutTopic("one"), ScoutTopic("two")],
        [],
        ScoutPolicy(query_budget=2, exploration_fraction=0),
    )
    assert result.discovered_count == 2
    assert result.selected_count == 1
    assert result.selected_ids == ("same",)

import pytest

from media_omega.memory import DecisionJournal


def test_journal_rejects_empty_event_type(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    with pytest.raises(ValueError, match="event_type"):
        journal.append("   ", {"x": 1})
    assert journal.read_all() == []


def test_journal_rejects_non_finite_payload(tmp_path):
    journal = DecisionJournal(tmp_path / "journal.db")
    with pytest.raises(ValueError):
        journal.append("METRIC", {"value": float("inf")})
    assert journal.read_all() == []

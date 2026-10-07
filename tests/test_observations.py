import pytest

from media_omega.observations import ContentObservation


def make(**changes):
    values = dict(
        platform="youtube", content_id="video", creator_id="creator",
        published_at="2026-10-07T00:00:00+00:00",
        observed_at="2026-10-07T01:00:00+00:00",
        views=100, creator_baseline_views=1000,
        evidence_ref="fixture://video",
    )
    values.update(changes)
    return ContentObservation(**values)


@pytest.mark.parametrize("field", ["platform", "content_id", "creator_id"])
def test_identity_fields_are_required(field):
    observation = make(**{field: ""})
    with pytest.raises(ValueError):
        observation.validate()


def test_legacy_creator_baseline_field_is_storage_only():
    observation = make(creator_baseline_views=0)
    observation.validate()
    assert not hasattr(observation, "relative_performance")


def test_sub_minute_content_age_fails_closed_instead_of_clamping_rate():
    observation = make(
        published_at="2026-10-07T00:59:30+00:00",
        observed_at="2026-10-07T01:00:00+00:00",
    )
    with pytest.raises(ValueError, match="age is too short"):
        _ = observation.views_per_hour

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


def test_unknown_creator_baseline_fails_closed():
    with pytest.raises(ValueError, match="baseline is unknown"):
        _ = make(creator_baseline_views=0).relative_performance

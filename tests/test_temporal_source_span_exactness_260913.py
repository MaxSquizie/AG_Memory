from datetime import datetime, timezone

from ah.temporal import TemporalAnchorContext, TemporalNormalizer


def test_unanchored_source_recognition_does_not_swallow_non_temporal_prefix() -> None:
    normalizer = TemporalNormalizer()
    empty = TemporalAnchorContext()

    assert normalizer.normalize("Я вчера", empty) is None
    assert normalizer.normalize("вчера я", empty) is None

    exact = normalizer.normalize("вчера", empty)
    assert exact is not None
    assert exact.relative
    assert not exact.resolved


def test_exact_relative_time_with_clock_remains_a_source_expression() -> None:
    normalizer = TemporalNormalizer()
    candidate = normalizer.normalize("вчера в 10:00", TemporalAnchorContext())

    assert candidate is not None
    assert candidate.relative
    assert not candidate.resolved


def test_real_turn_anchor_still_resolves_exact_relative_day() -> None:
    normalizer = TemporalNormalizer()
    anchor = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
    candidate = normalizer.normalize(
        "вчера",
        TemporalAnchorContext(source_timestamp=anchor),
    )

    assert candidate is not None and candidate.resolved
    assert candidate.value is not None
    assert candidate.value.start == "2026-09-12"


def test_absolute_date_source_recognition_is_unchanged() -> None:
    normalizer = TemporalNormalizer()
    dotted = normalizer.normalize("12.09.2026", TemporalAnchorContext())
    iso = normalizer.normalize("2026-09-12", TemporalAnchorContext())

    assert dotted is not None and dotted.resolved
    assert iso is not None and iso.resolved
    assert dotted.value is not None and iso.value is not None
    assert dotted.value.canonical_key == iso.value.canonical_key

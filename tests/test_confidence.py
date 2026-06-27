from mvo.confidence import ConfidenceEngine, ParseEvidence
from mvo.models import ConfidenceLevel


def test_high_confidence_for_explicit_artist_title_pair() -> None:
    confidence = ConfidenceEngine().score(
        ParseEvidence(has_separator=True, has_artist=True, has_title=True)
    )

    assert confidence.score == 0.9
    assert confidence.level is ConfidenceLevel.HIGH
    assert confidence.reasons == (
        "explicit artist/title separator",
        "artist candidate found",
        "title candidate found",
    )


def test_score_is_bounded_at_one() -> None:
    confidence = ConfidenceEngine().score(
        ParseEvidence(
            has_separator=True,
            has_artist=True,
            has_title=True,
            has_feature=True,
            has_version=True,
        )
    )

    assert confidence.score == 1.0

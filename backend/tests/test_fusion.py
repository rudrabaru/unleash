"""
Tests for the evidence fusion engine under the interim policy (D-51): must-pass checks fail closed,
only visual liveness and the visual challenge's score carry weight, deepfake / replay / voice /
lip sync are report-only (no weight, no veto), and a missing weighted signal caps the verdict.
"""
import pytest

from app import fusion
from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus

REPORT_ONLY_DETAILS = {"voice_authenticity_score": 0.0, "av_alignment_score": 0.0}


def _result(score, passed=True, reason="ok", details=None):
    return DetectorResult(score=score, passed=passed, reason=reason, error=None, details=details)


def _signals(liveness=1.0, challenge=1.0, deepfake=0.9, replay=0.9, audio_details=None):
    """A recording that passed both must-pass checks; the arguments are the scores of the other signals."""
    return {
        "visual_liveness": _result(liveness) if liveness is not None else None,
        "visual_challenge": _result(challenge, passed=True),
        "audio_pipeline": _result(None, passed=True, details=audio_details),
        "deepfake": _result(deepfake) if deepfake is not None else None,
        "replay": _result(replay) if replay is not None else None,
    }


# --- must-pass checks ---------------------------------------------------------------------------

def test_a_failed_visual_challenge_is_failed_whatever_the_scores():
    signals = _signals()
    signals["visual_challenge"] = _result(0.9, passed=False, reason="no_return")

    result = fusion.evaluate(signals)

    assert result.status == VerificationStatus.FAILED and result.confidence is None
    assert result.reason == "Visual challenge compliance failed: no_return"


def test_a_failed_audio_check_is_failed_whatever_the_scores():
    signals = _signals()
    signals["audio_pipeline"] = _result(None, passed=False, reason="wrong words")

    result = fusion.evaluate(signals)

    assert result.status == VerificationStatus.FAILED and result.confidence is None
    assert result.reason == "Audio must-pass check failed: wrong words"


@pytest.mark.parametrize("missing", ["visual_challenge", "audio_pipeline"])
def test_a_must_pass_check_that_produced_no_result_fails_closed(missing):
    signals = _signals()
    signals[missing] = None

    result = fusion.evaluate(signals)

    assert result.status == VerificationStatus.FAILED and "no result" in result.reason


# --- report-only signals cannot change the verdict ---------------------------------------------

@pytest.mark.parametrize("deepfake, replay", [(0.0, 0.0), (0.2, 0.3), (1.0, 1.0), (None, None)])
def test_deepfake_and_replay_change_neither_the_score_nor_the_verdict(deepfake, replay):
    """There is no joint veto any more: the old veto case (deepfake 0.2, replay 0.3) is a normal VERIFIED."""
    result = fusion.evaluate(_signals(deepfake=deepfake, replay=replay))

    assert result.status == VerificationStatus.VERIFIED and result.confidence == 1.0


def test_voice_and_lip_sync_scores_in_the_audio_details_are_not_read():
    best = fusion.evaluate(_signals(audio_details={"voice_authenticity_score": 1.0, "av_alignment_score": 1.0}))
    worst = fusion.evaluate(_signals(audio_details=REPORT_ONLY_DETAILS))

    assert best == worst and best.status == VerificationStatus.VERIFIED


def test_the_reported_signals_are_exactly_the_ones_with_no_weight():
    assert set(fusion.SIGNAL_WEIGHTS) == {"visual_liveness", "visual_challenge"}
    assert set(fusion.REPORT_ONLY_SIGNALS) == {"deepfake", "replay", "voice_authenticity", "av_alignment"}
    assert not set(fusion.SIGNAL_WEIGHTS) & set(fusion.REPORT_ONLY_SIGNALS)


# --- the weighted score and its bands ----------------------------------------------------------

@pytest.mark.parametrize("liveness, challenge, expected, status", [
    (1.0, 1.0, 1.0, VerificationStatus.VERIFIED),
    (0.86, 1.0, (0.20 * 0.86 + 0.25) / 0.45, VerificationStatus.VERIFIED),     # a typical genuine take: 0.938
    (0.50, 1.0, (0.20 * 0.50 + 0.25) / 0.45, VerificationStatus.SUSPICIOUS),   # 0.778: just under the line
    (0.0, 1.0, 0.25 / 0.45, VerificationStatus.SUSPICIOUS),                    # 0.556: just over the lower line
    (0.2, 0.7, (0.20 * 0.2 + 0.25 * 0.7) / 0.45, VerificationStatus.FAILED),   # 0.478
])
def test_the_bands_are_exact(liveness, challenge, expected, status):
    result = fusion.evaluate(_signals(liveness=liveness, challenge=challenge))

    assert result.confidence == pytest.approx(expected, abs=1e-4)
    assert result.status == status


def test_the_two_weights_keep_their_ratio_of_four_to_five():
    assert fusion.SIGNAL_WEIGHTS["visual_liveness"] / fusion.SIGNAL_WEIGHTS["visual_challenge"] == pytest.approx(0.8)


# --- minimum coverage --------------------------------------------------------------------------

def test_a_missing_liveness_score_caps_the_verdict_at_suspicious():
    capped = fusion.evaluate(_signals(liveness=None, challenge=1.0))

    assert capped.status == VerificationStatus.SUSPICIOUS
    assert capped.confidence == 1.0  # the score is still reported, the verdict is what is capped
    assert "Capped at SUSPICIOUS" in capped.reason and "visual_liveness" in capped.reason


def test_a_liveness_that_errored_counts_as_missing_not_as_zero():
    signals = _signals()
    signals["visual_liveness"] = DetectorResult(score=None, passed=False, reason="no landmarks", error="boom")

    result = fusion.evaluate(signals)

    assert result.confidence == 1.0 and result.status == VerificationStatus.SUSPICIOUS


def test_the_cap_never_raises_a_low_score_or_turns_a_suspicious_one_into_failed():
    low = fusion.evaluate(_signals(liveness=None, challenge=0.3))  # 0.3 alone
    middling = fusion.evaluate(_signals(liveness=None, challenge=0.7))

    assert low.status == VerificationStatus.FAILED
    assert middling.status == VerificationStatus.SUSPICIOUS and "Capped" not in middling.reason


def test_no_usable_scores_at_all_fails_gracefully():
    signals = _signals(liveness=None)
    signals["visual_challenge"] = _result(None, passed=True)

    result = fusion.evaluate(signals)

    assert result.status == VerificationStatus.FAILED and result.confidence is None
    assert "no usable signal scores" in result.reason

"""
Tests for the evidence fusion engine: hard gates, joint veto, null-score
redistribution, and threshold bands (docs/unleash_project_plan.md Section 6).
"""
from app import fusion
from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus


def _result(score, passed=True, reason="ok"):
    return DetectorResult(score=score, passed=passed, reason=reason, error=None)


def test_visual_challenge_hard_gate_fails_regardless_of_score():
    signals = {
        "visual_challenge": _result(0.9, passed=False),
        "visual_liveness": _result(0.9),
        "deepfake": _result(0.9),
        "replay": _result(0.9),
        "audio_pipeline": _result(0.9, passed=True),
    }
    result = fusion.evaluate(signals)
    assert result.status == VerificationStatus.FAILED
    assert result.confidence is None


def test_audio_hard_gate_fails_regardless_of_score():
    signals = {
        "visual_challenge": _result(0.9, passed=True),
        "audio_pipeline": _result(0.9, passed=False),
    }
    result = fusion.evaluate(signals)
    assert result.status == VerificationStatus.FAILED


def test_joint_veto_fires_when_both_deepfake_and_replay_low():
    signals = {
        "visual_challenge": _result(0.9, passed=True),
        "audio_pipeline": _result(0.9, passed=True),
        "deepfake": _result(0.2),
        "replay": _result(0.3),
    }
    result = fusion.evaluate(signals)
    assert result.status == VerificationStatus.FAILED


def test_joint_veto_does_not_fire_if_only_one_signal_low():
    signals = {
        "visual_challenge": _result(0.9, passed=True),
        "audio_pipeline": _result(0.9, passed=True),
        "deepfake": _result(0.2),
        "replay": _result(0.9),
    }
    result = fusion.evaluate(signals)
    assert result.status != VerificationStatus.FAILED or "veto" not in result.reason.lower()


def test_null_scores_are_redistributed_not_treated_as_zero():
    signals = {
        "visual_challenge": _result(1.0, passed=True),
        "audio_pipeline": _result(1.0, passed=True),
        "visual_liveness": None,
        "deepfake": None,
        "replay": None,
    }
    result = fusion.evaluate(signals)
    # Only visual_challenge (weight 0.25) has a score; if null were treated as 0
    # the weighted average would collapse toward ~0.25 instead of 1.0.
    assert result.confidence == 1.0
    assert result.status == VerificationStatus.VERIFIED


def test_thresholds_verified_suspicious_failed():
    base = {
        "visual_challenge": _result(1.0, passed=True),
        "audio_pipeline": _result(1.0, passed=True),
    }

    verified = fusion.evaluate({**base, "deepfake": _result(0.9), "replay": _result(0.9)})
    assert verified.status == VerificationStatus.VERIFIED

    suspicious = fusion.evaluate({**base, "deepfake": _result(0.3), "visual_challenge": _result(0.3, passed=True)})
    assert suspicious.status in (VerificationStatus.SUSPICIOUS, VerificationStatus.FAILED)

    failed = fusion.evaluate({
        "visual_challenge": _result(0.1, passed=True),
        "audio_pipeline": _result(1.0, passed=True),
        "deepfake": _result(0.1),
    })
    assert failed.status == VerificationStatus.FAILED


def test_no_usable_signals_fails_gracefully():
    signals = {"visual_challenge": None, "audio_pipeline": None}
    result = fusion.evaluate(signals)
    assert result.status == VerificationStatus.FAILED
    assert result.confidence is None

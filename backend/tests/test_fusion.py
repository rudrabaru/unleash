"""
Tests for the evidence fusion engine: hard gates, joint veto, null-score
redistribution, and threshold bands (docs/unleash_project_plan.md Section 6).
"""
from app import fusion
from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus


<<<<<<< HEAD
def _result(score, passed=True, reason="ok"):
    return DetectorResult(score=score, passed=passed, reason=reason, error=None)
=======
def _result(score, passed=True, reason="ok", details=None):
    return DetectorResult(score=score, passed=passed, reason=reason, error=None, details=details)
>>>>>>> origin/feature/deepfake-detection


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
<<<<<<< HEAD
=======


def test_av_alignment_fallback_from_audio_pipeline_details():
    """
    Regression test:
    When there is no top-level signals['av_alignment'], but audio_pipeline.details
    contains a valid av_alignment_score, fusion must retrieve and use that score
    with its intended 10% weight rather than silently ignoring/redistributing it.
    """
    # 5 detectors as returned by orchestrator (no top-level 'av_alignment' or 'voice_authenticity')
    # Weights: visual_liveness=0.20, visual_challenge=0.25, deepfake=0.20, replay=0.15,
    # voice_authenticity=0.10, av_alignment=0.10.
    # Scores: all other 5 signals = 0.80 (0.80 * 0.90 = 0.72)
    # AV alignment = 0.30 (0.30 * 0.10 = 0.03)
    # Total expected score = 0.72 + 0.03 = 0.7500 (SUSPICIOUS, < 0.80)
    # If AV alignment is silently dropped, score would be 0.72 / 0.90 = 0.8000 (VERIFIED, >= 0.80)
    signals = {
        "visual_liveness": _result(0.80),
        "visual_challenge": _result(0.80, passed=True),
        "deepfake": _result(0.80),
        "replay": _result(0.80),
        "audio_pipeline": _result(
            score=0.55,
            passed=True,
            details={
                "voice_authenticity_score": 0.80,
                "av_alignment_score": 0.30,
            },
        ),
    }

    # Verify precondition: no top-level av_alignment signal
    assert "av_alignment" not in signals
    assert signals.get("av_alignment") is None

    result = fusion.evaluate(signals)

    # If the bug exists, result.confidence == 0.80 and status == VERIFIED
    # With the fix, result.confidence == 0.75 and status == SUSPICIOUS
    assert result.confidence == 0.75
    assert result.status == VerificationStatus.SUSPICIOUS

    # Also verify that passing av_alignment as a top-level signal produces identical result
    signals_with_top_level = dict(signals)
    signals_with_top_level["av_alignment"] = _result(0.30)
    result_top_level = fusion.evaluate(signals_with_top_level)
    assert result.confidence == result_top_level.confidence
    assert result.status == result_top_level.status


def test_av_alignment_fallback_absent_or_null_redistributes_proportionally():
    """
    Ensure proportional redistribution still functions properly when
    av_alignment_score is None or absent in audio_pipeline.details.
    """
    signals_with_null = {
        "visual_challenge": _result(1.0, passed=True),
        "audio_pipeline": _result(
            score=1.0,
            passed=True,
            details={
                "voice_authenticity_score": 1.0,
                "av_alignment_score": None,
            },
        ),
    }
    result = fusion.evaluate(signals_with_null)
    # Only visual_challenge (0.25) and voice_authenticity (0.10) are present, both 1.0.
    # Null AV alignment and other missing signals are redistributed proportionally.
    assert result.confidence == 1.0
    assert result.status == VerificationStatus.VERIFIED


def test_av_alignment_top_level_takes_precedence_over_details():
    """
    If signals['av_alignment'] is explicitly provided at the top level,
    it should take precedence over audio_pipeline.details['av_alignment_score'].
    """
    signals = {
        "visual_challenge": _result(1.0, passed=True),
        "av_alignment": _result(0.90),
        "audio_pipeline": _result(
            score=1.0,
            passed=True,
            details={
                "voice_authenticity_score": 1.0,
                "av_alignment_score": 0.10,
            },
        ),
    }
    # visual_challenge: 0.25 * 1.0 = 0.25
    # voice_authenticity: 0.10 * 1.0 = 0.10
    # av_alignment: 0.10 * 0.90 = 0.09 (top-level 0.90 used, not 0.10)
    # total_weight = 0.45
    # numerator = 0.44
    # score = 0.44 / 0.45 = 0.9778
    result = fusion.evaluate(signals)
    assert result.confidence == round(0.44 / 0.45, 4)


def test_av_alignment_fallback_handles_zero_score_correctly():
    """
    av_alignment_score = 0.0 is a valid score (not None) and must contribute 0.0
    with 10% weight rather than being treated as falsy/missing.
    """
    signals = {
        "visual_challenge": _result(1.0, passed=True),
        "audio_pipeline": _result(
            score=1.0,
            passed=True,
            details={
                "voice_authenticity_score": 1.0,
                "av_alignment_score": 0.0,
            },
        ),
    }
    # visual_challenge: 0.25 * 1.0 = 0.25
    # voice_authenticity: 0.10 * 1.0 = 0.10
    # av_alignment: 0.10 * 0.0 = 0.00
    # total_weight = 0.45
    # numerator = 0.35
    # score = 0.35 / 0.45 = 0.7778
    result = fusion.evaluate(signals)
    assert result.confidence == round(0.35 / 0.45, 4)


>>>>>>> origin/feature/deepfake-detection

"""
Tests for the evidence fusion engine: must-pass checks, joint veto, null-score
redistribution, and threshold bands.
"""
from app import fusion
from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus


def _result(score, passed=True, reason="ok", details=None):
    return DetectorResult(score=score, passed=passed, reason=reason, error=None, details=details)


def test_visual_challenge_must_pass_check_fails_regardless_of_score():
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


def test_audio_must_pass_check_fails_regardless_of_score():
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


def test_replay_score_none_excludes_weight_and_matches_absent():
    """
    a) replay_score = None
    - No exception raised.
    - Replay weight (0.15) is excluded from weighted scoring.
    - Remaining active weights are renormalized proportionally.
    - Result matches the equivalent case where replay signal is completely absent.
    """
    base_signals = {
        "visual_challenge": _result(0.80, passed=True),
        "visual_liveness": _result(0.80),
        "deepfake": _result(0.80),
        "audio_pipeline": _result(
            score=0.80,
            passed=True,
            details={"voice_authenticity_score": 0.80, "av_alignment_score": 0.80},
        ),
    }

    signals_replay_none = dict(base_signals)
    signals_replay_none["replay"] = _result(score=None)

    signals_replay_absent = dict(base_signals)

    res_none = fusion.evaluate(signals_replay_none)
    res_absent = fusion.evaluate(signals_replay_absent)

    assert res_none.status == res_absent.status == VerificationStatus.VERIFIED
    assert res_none.confidence == res_absent.confidence == 0.80


def test_stage3_and_deepfake_none_exclude_weights_and_match_absent():
    """
    b) voice-authenticity/deepfake score = None
    - No exception raised.
    - Score None excludes the signal's weight.
    - Remaining active weights are renormalized proportionally.
    - Result matches the equivalent case where the signal is completely absent.
    """
    # 1. Deepfake with score=None vs absent
    base = {
        "visual_challenge": _result(0.90, passed=True),
        "visual_liveness": _result(0.90),
        "replay": _result(0.90),
    }
    signals_df_none = dict(base)
    signals_df_none["deepfake"] = _result(score=None)
    signals_df_absent = dict(base)

    res_df_none = fusion.evaluate(signals_df_none)
    res_df_absent = fusion.evaluate(signals_df_absent)

    assert res_df_none.status == res_df_absent.status == VerificationStatus.VERIFIED
    assert res_df_none.confidence == res_df_absent.confidence == 0.90

    # 2. voice authenticity in audio_pipeline.details with score=None vs absent
    base_audio = {
        "visual_challenge": _result(1.0, passed=True),
        "audio_pipeline": _result(
            score=1.0,
            passed=True,
            details={"voice_authenticity_score": None},
        ),
    }
    base_audio_absent = {
        "visual_challenge": _result(1.0, passed=True),
        "audio_pipeline": _result(
            score=1.0,
            passed=True,
            details={},
        ),
    }
    res_va_none = fusion.evaluate(base_audio)
    res_va_absent = fusion.evaluate(base_audio_absent)

    assert res_va_none.status == res_va_absent.status == VerificationStatus.VERIFIED
    assert res_va_none.confidence == res_va_absent.confidence == 1.0


def test_must_pass_check_behavior_with_none_score():
    """
    c) Must-pass check involving a None score
    Current production behavior:
    Must-pass checks depend only on the boolean `.passed` fields (audio_pipeline.passed
    and visual_challenge.passed), not on numeric scores.
    If a must-pass check fails (passed=False), fusion immediately fails closed
    (status=FAILED, confidence=None) even if replay, deepfake, or voice-authenticity scores are None.
    Conversely, if passed=True, a None score does not fail the must-pass check.
    """
    # Audio must-pass check fails even when replay score is None
    signals_audio_failed = {
        "visual_challenge": _result(1.0, passed=True),
        "audio_pipeline": _result(score=None, passed=False, reason="Speech too short"),
        "replay": _result(score=None),
        "deepfake": _result(score=None),
    }
    res_audio_failed = fusion.evaluate(signals_audio_failed)
    assert res_audio_failed.status == VerificationStatus.FAILED
    assert res_audio_failed.confidence is None
    assert "Audio must-pass check failed" in res_audio_failed.reason

    # Visual challenge must-pass check fails even when deepfake score is None
    signals_visual_failed = {
        "visual_challenge": _result(score=0.9, passed=False, reason="Wrong head turn"),
        "audio_pipeline": _result(score=1.0, passed=True),
        "deepfake": _result(score=None),
    }
    res_visual_failed = fusion.evaluate(signals_visual_failed)
    assert res_visual_failed.status == VerificationStatus.FAILED
    assert res_visual_failed.confidence is None
    assert "Visual challenge compliance failed" in res_visual_failed.reason


def test_joint_veto_behavior_with_none_inputs():
    """
    d) Joint veto with None inputs vs present inputs below thresholds
    Current production behavior:
    The joint veto requires BOTH deepfake.score and replay.score to be non-None
    and below their respective thresholds (deepfake < 0.3, replay < 0.4).
    If either input (or both) has score=None, the joint veto does NOT fire.
    If both are present and below thresholds, the joint veto DOES fire.
    """
    base = {
        "visual_challenge": _result(1.0, passed=True),
        "audio_pipeline": _result(1.0, passed=True),
    }

    # Case 1: deepfake is low (0.2 < 0.3), but replay is None -> does NOT fire veto
    sig_one_none_1 = {**base, "deepfake": _result(0.2), "replay": _result(score=None)}
    res_one_none_1 = fusion.evaluate(sig_one_none_1)
    assert "joint veto" not in res_one_none_1.reason.lower()

    # Case 2: replay is low (0.3 < 0.4), but deepfake is None -> does NOT fire veto
    sig_one_none_2 = {**base, "deepfake": _result(score=None), "replay": _result(0.3)}
    res_one_none_2 = fusion.evaluate(sig_one_none_2)
    assert "joint veto" not in res_one_none_2.reason.lower()

    # Case 3: both inputs have score=None -> does NOT fire veto
    sig_both_none = {**base, "deepfake": _result(score=None), "replay": _result(score=None)}
    res_both_none = fusion.evaluate(sig_both_none)
    assert "joint veto" not in res_both_none.reason.lower()

    # Case 4: both inputs present and below thresholds -> DOES fire veto
    sig_veto_fire = {**base, "deepfake": _result(0.2), "replay": _result(0.3)}
    res_veto_fire = fusion.evaluate(sig_veto_fire)
    assert res_veto_fire.status == VerificationStatus.FAILED
    assert res_veto_fire.confidence is None
    assert "joint veto" in res_veto_fire.reason.lower()


def test_simultaneous_null_replay_stage3_and_av_no_division_by_zero():
    """
    e) replay=None + voice-check=None + AV=None simultaneously
    - No exception raised.
    - No division-by-zero.
    - Remaining active weights (visual_liveness 0.20, visual_challenge 0.25, deepfake 0.20)
      sum to 0.65 and are renormalized correctly.
    """
    signals = {
        "visual_challenge": _result(0.80, passed=True),   # 0.25 * 0.80 = 0.20
        "visual_liveness": _result(0.60),                 # 0.20 * 0.60 = 0.12
        "deepfake": _result(0.70),                        # 0.20 * 0.70 = 0.14
        "replay": _result(score=None),                     # excluded
        "audio_pipeline": _result(                         # voice and lip-sync scores excluded
            score=1.0,
            passed=True,
            details={
                "voice_authenticity_score": None,
                "av_alignment_score": None,
            },
        ),
    }
    # Active weights: 0.25 + 0.20 + 0.20 = 0.65
    # Numerator: 0.20 + 0.12 + 0.14 = 0.46
    # Weighted average: 0.46 / 0.65 = 0.707692... -> round(..., 4) = 0.7077
    res = fusion.evaluate(signals)
    assert res.confidence == round(0.46 / 0.65, 4)
    assert res.status == VerificationStatus.SUSPICIOUS  # 0.55 <= 0.7077 < 0.80


def test_valid_zero_scores_treated_as_present_not_none():
    """
    f) Valid 0.0 values:
    - replay score of 0.0 must be treated as PRESENT (not None/missing).
    - voice-authenticity/deepfake score of 0.0 must be treated as PRESENT (not None/missing).
    - They contribute 0.0 to the numerator and their weight to the denominator.
    """
    # 1. replay=0.0 vs replay=None
    sig_replay_zero = {
        "visual_challenge": _result(1.0, passed=True),  # weight 0.25
        "replay": _result(score=0.0),                   # weight 0.15
    }
    # Numerator: 0.25 * 1.0 + 0.15 * 0.0 = 0.25
    # Denominator: 0.25 + 0.15 = 0.40
    # Score: 0.25 / 0.40 = 0.625
    res_replay_zero = fusion.evaluate(sig_replay_zero)
    assert res_replay_zero.confidence == 0.625

    sig_replay_none = {
        "visual_challenge": _result(1.0, passed=True),
        "replay": _result(score=None),
    }
    res_replay_none = fusion.evaluate(sig_replay_none)
    assert res_replay_none.confidence == 1.0
    assert res_replay_zero.confidence != res_replay_none.confidence

    # 2. deepfake=0.0 vs deepfake=None
    sig_df_zero = {
        "visual_challenge": _result(1.0, passed=True),  # weight 0.25
        "deepfake": _result(score=0.0),                 # weight 0.20
    }
    # Numerator: 0.25 * 1.0 + 0.20 * 0.0 = 0.25
    # Denominator: 0.25 + 0.20 = 0.45
    # Score: 0.25 / 0.45 = 0.5556
    res_df_zero = fusion.evaluate(sig_df_zero)
    assert res_df_zero.confidence == round(0.25 / 0.45, 4)

    # 3. voice authenticity in details = 0.0 vs None
    sig_va_zero = {
        "visual_challenge": _result(1.0, passed=True),  # weight 0.25
        "audio_pipeline": _result(
            score=1.0,
            passed=True,
            details={"voice_authenticity_score": 0.0},  # weight 0.10
        ),
    }
    # Numerator: 0.25 * 1.0 + 0.10 * 0.0 = 0.25
    # Denominator: 0.25 + 0.10 = 0.35
    # Score: 0.25 / 0.35 = 0.7143
    res_va_zero = fusion.evaluate(sig_va_zero)
    assert res_va_zero.confidence == round(0.25 / 0.35, 4)




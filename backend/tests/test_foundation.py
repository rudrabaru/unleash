import sys
import os
import time

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas.detector import DetectorResult
from app.schemas.session import VisualChallengeType, VerificationStatus
from app.core.security import generate_challenge_token, verify_challenge_token


def test_detector_schema_valid():
    result = DetectorResult(
        score=0.85,
        passed=True,
        reason="Natural motion detected",
        error=None,
        details={"fps": 30}
    )
    assert result.score == 0.85
    assert result.passed is True
    assert result.reason == "Natural motion detected"
    assert result.error is None


def test_detector_schema_bounds():
    # Verify Pydantic bounds checking
    try:
        DetectorResult(score=1.5, passed=True, reason="Invalid")
        assert False, "Should fail validation for score > 1.0"
    except Exception:
        pass


def test_hmac_token_lifecycle():
    secret = "test_secret_key_12345"
    session_id = "test-session-uuid"
    visual = "TURN_HEAD_LEFT"
    verbal = "742"

    token, expires_at = generate_challenge_token(
        session_id=session_id,
        visual_challenge=visual,
        verbal_challenge=verbal,
        secret_key=secret,
        expiry_seconds=60
    )

    # 1. Valid token check
    is_valid, err = verify_challenge_token(token, session_id, secret)
    assert is_valid is True, f"Failed valid token check: {err}"

    # 2. Tampered token check
    tampered = token[:-4] + "abcd"
    is_valid, err = verify_challenge_token(tampered, session_id, secret)
    assert is_valid is False
    assert "HMAC verification failed" in err

    # 3. Session mismatch check
    is_valid, err = verify_challenge_token(token, "wrong-session-uuid", secret)
    assert is_valid is False
    assert "mismatch" in err

    # 4. Expired token check
    expired_token, _ = generate_challenge_token(
        session_id=session_id,
        visual_challenge=visual,
        verbal_challenge=verbal,
        secret_key=secret,
        expires_at=int(time.time()) - 10
    )
    is_valid, err = verify_challenge_token(expired_token, session_id, secret)
    assert is_valid is False
    assert "expired" in err


if __name__ == "__main__":
    test_detector_schema_valid()
    test_detector_schema_bounds()
    test_hmac_token_lifecycle()
    print("ALL PHASE 0 FOUNDATION TESTS PASSED SUCCESSFULLY!")

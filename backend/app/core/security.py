import hashlib
import hmac
import time
from typing import Optional, Tuple


def generate_challenge_token(
    session_id: str,
    visual_challenge: str,
    verbal_challenge: str,
    secret_key: str,
    expires_at: Optional[int] = None,
    expiry_seconds: int = 120,
) -> Tuple[str, int]:
    """
    Generate an HMAC-SHA256 signed token for a session challenge.
    Returns: (token_str, expires_at_timestamp)
    """
    if expires_at is None:
        expires_at = int(time.time()) + expiry_seconds

    # Construct the canonical payload to sign
    payload = f"{session_id}:{visual_challenge}:{verbal_challenge}:{expires_at}"
    
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    token = f"{payload}:{signature}"
    return token, expires_at


def verify_challenge_token(
    token: str,
    expected_session_id: str,
    secret_key: str,
) -> Tuple[bool, Optional[str]]:
    """
    Verify the validity, expiration, and signature of an HMAC challenge token.
    Returns: (is_valid: bool, error_reason: Optional[str])
    """
    try:
        parts = token.split(":")
        if len(parts) != 5:
            return False, "Malformed token structure"

        session_id, visual, verbal, expires_at_str, signature = parts
        
        # Verify session match
        if session_id != expected_session_id:
            return False, "Session ID mismatch in token"

        # Check expiration
        expires_at = int(expires_at_str)
        current_time = int(time.time())
        if current_time > expires_at:
            return False, f"Token expired (expired at {expires_at}, current {current_time})"

        # Verify signature
        payload = f"{session_id}:{visual}:{verbal}:{expires_at}"
        expected_sig = hmac.new(
            secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return False, "Invalid signature: HMAC verification failed"

        return True, None
    except Exception as e:
        return False, f"Token verification error: {str(e)}"

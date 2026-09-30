try:
    from app.modules.audio import process_audio_pipeline
except ImportError:
    process_audio_pipeline = None

try:
    from app.modules.visual import detect_visual_liveness, verify_challenge_compliance
except ImportError:
    detect_visual_liveness = None
    verify_challenge_compliance = None

try:
    from app.modules.antispoof import detect_deepfake, detect_replay_attack
except ImportError:
    detect_deepfake = None
    detect_replay_attack = None

__all__ = [
    "process_audio_pipeline",
    "detect_visual_liveness",
    "verify_challenge_compliance",
    "detect_deepfake",
    "detect_replay_attack",
]

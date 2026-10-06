"""Audio format every stage works in. Kept free of heavy imports so any module can use it."""

TARGET_SAMPLE_RATE = 16000  # Hz; every extracted WAV is forced to this regardless of the recording
TARGET_CHANNELS = 1  # mono

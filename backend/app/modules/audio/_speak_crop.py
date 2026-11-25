"""
Cut the part of the recording where the phrase is spoken out of the extracted audio.

With the protocol windows (app/protocol.py) the speech and phrase checks listen to the Speak window
only (widened a little on both sides), not to the whole recording. Speech outside it, such as
reading the words aloud during Read or a second attempt after Act, then counts for nothing, and the
recognizer has about 6 s to transcribe instead of 13 s.

Three clocks meet here. The windows are offsets from the start of the recording; the lip series and
the audio track's start time are on the container clock; the extracted WAV starts at its own first
sample. The crop converts between them once, here.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import soundfile as sf

from app.modules.audio._io import read_wav_numpy
from app.protocol import PhaseWindows


@dataclass(frozen=True)
class SpeakCrop:
    wav_start: float  # seconds into the extracted WAV where the crop begins
    wav_end: float
    container_start: float  # the same moments on the container clock (the lip series' clock)
    container_end: float

    @property
    def seconds(self) -> float:
        return self.wav_end - self.wav_start


def plan_speak_crop(phases: PhaseWindows, recording_start: Optional[float], audio_start: float) -> SpeakCrop:
    """
    Where the Speak window lies in the extracted WAV. `recording_start` is the zero of the
    recording's clock on the container clock (None counts as 0); `audio_start` is when the audio
    track starts on the container clock, which the extracted WAV does not keep.
    """
    window_start, window_end = phases.speech_window()
    origin = recording_start or 0.0
    container_start, container_end = origin + window_start, origin + window_end
    wav_start = max(0.0, container_start - audio_start)
    wav_end = max(wav_start, container_end - audio_start)
    return SpeakCrop(wav_start=wav_start, wav_end=wav_end, container_start=container_start, container_end=container_end)


def write_speak_crop(wav_path: Path, crop: SpeakCrop, out_path: Path) -> Path:
    """Write the cropped samples as a new 16-bit WAV at the same sample rate (an empty crop gives an empty file)."""
    audio, sample_rate, _ = read_wav_numpy(wav_path)
    first, last = int(crop.wav_start * sample_rate), int(crop.wav_end * sample_rate)
    sf.write(str(out_path), audio[first:last], sample_rate, subtype="PCM_16")
    return out_path

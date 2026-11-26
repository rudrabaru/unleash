"""
Open an uploaded recording only as the kind of file it should be.

FFmpeg (behind both PyAV and the ffmpeg/ffprobe commands) guesses a file's format from its
contents and can follow references inside it: a "recording" that is really an HLS playlist or a
similar index can make it open network addresses or other local files. An upload is therefore
opened with two allow-lists:

  * demuxers: only Matroska/WebM (what browsers record) and the MP4/QuickTime family (what phones
    record; several of the sample clips are MP4 files named .webm), whatever the file is called;
  * protocols: only local files, so nothing inside the file can reach the network.

The 16 kHz WAV the audio pipeline writes for itself is opened the same way with the WAV demuxer.
"""
from pathlib import Path
from typing import Dict, List, Sequence, Union

import av

# Demuxer names as FFmpeg reports them ("matroska,webm" and "mov,mp4,m4a,3gp,3g2,mj2").
UPLOAD_DEMUXERS: Sequence[str] = ("matroska", "webm", "mov", "mp4", "m4a", "3gp", "3g2", "mj2")
WAV_DEMUXERS: Sequence[str] = ("wav",)
LOCAL_FILES_ONLY = "file"


def av_options(demuxers: Sequence[str] = UPLOAD_DEMUXERS) -> Dict[str, str]:
    """Format options for `av.open` that enforce both allow-lists."""
    return {"format_whitelist": ",".join(demuxers), "protocol_whitelist": LOCAL_FILES_ONLY}


def open_media(path: Union[str, Path], demuxers: Sequence[str] = UPLOAD_DEMUXERS):
    """`av.open` for reading, refusing any other container format or protocol (raises like `av.open`)."""
    return av.open(str(path), options=av_options(demuxers))


def ffmpeg_input_args(demuxers: Sequence[str] = UPLOAD_DEMUXERS) -> List[str]:
    """Input options for ffmpeg/ffprobe; they must come before the input file on the command line."""
    return ["-protocol_whitelist", LOCAL_FILES_ONLY, "-format_whitelist", ",".join(demuxers)]

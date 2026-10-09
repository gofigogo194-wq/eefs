from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess

from .models import Decision, GateResult


def inspect_video(path: str, *, executable: str = "ffprobe", timeout: float = 20.0) -> tuple[GateResult, dict]:
    """Read actual media properties through ffprobe, never through filename/MIME claims.

    A failed/missing probe blocks; it is never treated as an optional warning.
    The returned report is suitable for a journal evidence payload.
    """
    if not isinstance(path, str) or not path.strip():
        return GateResult(Decision.BLOCK, ("VIDEO_PATH_REQUIRED",)), {}
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 120:
        raise ValueError("invalid probe timeout")
    source = Path(path).expanduser()
    try:
        if not source.is_file():
            return GateResult(Decision.BLOCK, ("VIDEO_NOT_FOUND",)), {}
        command = [
            executable, "-v", "error", "-show_entries",
            "format=format_name,duration:stream=codec_type,codec_name,width,height",
            "-of", "json", str(source),
        ]
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return GateResult(Decision.BLOCK, ("FFPROBE_UNAVAILABLE",)), {}
    except subprocess.TimeoutExpired:
        return GateResult(Decision.BLOCK, ("FFPROBE_TIMEOUT",)), {}
    except (OSError, UnicodeError):
        return GateResult(Decision.BLOCK, ("FFPROBE_EXECUTION_FAILED",)), {}
    if proc.returncode != 0:
        return GateResult(Decision.BLOCK, ("FFPROBE_REJECTED_FILE",)), {}
    try:
        raw = json.loads(proc.stdout)
        streams = raw["streams"]
        fmt = raw["format"]
        if not isinstance(streams, list) or not isinstance(fmt, dict):
            raise ValueError("invalid media payload")
        duration = float(fmt["duration"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid duration")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return GateResult(Decision.BLOCK, ("FFPROBE_INVALID_RESPONSE",)), {}
    videos = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"]
    audios = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"]
    if len(videos) != 1:
        return GateResult(Decision.BLOCK, ("VIDEO_STREAM_COUNT_INVALID",)), {}
    video = videos[0]
    if video.get("codec_name") not in {"h264", "hevc", "av1", "vp9"}:
        return GateResult(Decision.BLOCK, ("VIDEO_CODEC_UNSUPPORTED",)), {}
    width, height = video.get("width"), video.get("height")
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 144 or x > 8192 for x in (width, height)):
        return GateResult(Decision.BLOCK, ("VIDEO_DIMENSIONS_INVALID",)), {}
    if len(audios) > 1 or any(
        audio.get("codec_name") not in {"aac", "opus", "mp3", "vorbis"}
        for audio in audios
    ):
        return GateResult(Decision.BLOCK, ("AUDIO_LAYOUT_UNSUPPORTED",)), {}
    report = {
        "version": "video_probe.v1",
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "video_codec": video["codec_name"],
        "audio_codec": audios[0]["codec_name"] if audios else None,
        "audio_present": bool(audios),
        "format_name": str(fmt.get("format_name", "")),
    }
    return GateResult(Decision.ACCEPT, ("VIDEO_PROBE_PASS",)), report

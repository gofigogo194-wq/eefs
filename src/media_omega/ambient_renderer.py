"""Local FFmpeg ambient-video assembly. No publisher or network access."""
from __future__ import annotations

from pathlib import Path
import json
import math
import subprocess

from .media_probe import inspect_video, decode_video
from .models import Decision


def render_ambient_loop(source_video: str, source_audio: str, output_mp4: str,
                        *, duration_seconds: float, ffmpeg: str = "ffmpeg",
                        audio_crossfade_seconds: float = 0.0) -> str:
    """Loop a user-supplied video and audio to one exact-duration MP4.

    The seamlessness of loop boundaries depends on matching source endpoints;
    this renderer makes no unsupported seamlessness claim.
    """
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)) or not math.isfinite(duration_seconds) or not 0.5 <= duration_seconds <= 18000:
        raise ValueError("duration must be between 0.5 seconds and 5 hours")
    if (isinstance(audio_crossfade_seconds, bool)
            or not isinstance(audio_crossfade_seconds, (int, float))
            or not math.isfinite(audio_crossfade_seconds)
            or not 0 <= audio_crossfade_seconds <= 1):
        raise ValueError("audio crossfade must be between 0 and 1 seconds")
    video = Path(source_video).resolve()
    audio = Path(source_audio).resolve()
    output = Path(output_mp4).resolve()
    if not video.is_file() or not audio.is_file():
        raise ValueError("source media missing")
    if output in (video, audio):
        raise ValueError("output must not overwrite source media")
    if output.suffix.lower() != ".mp4":
        raise ValueError("output must be MP4")
    if output.exists():
        raise ValueError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.stem + ".partial.mp4")
    if temp.exists():
        raise ValueError("partial output already exists; inspect or remove it")
    audio_loop = temp.with_name(temp.stem + ".audio-loop.wav")
    if audio_loop.exists():
        raise ValueError("prepared audio loop already exists")
    if audio_crossfade_seconds:
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(audio),
        ], capture_output=True, text=True, timeout=20, check=False)
        if probe.returncode != 0:
            raise RuntimeError("audio duration preflight failed")
        try:
            length = float(json.loads(probe.stdout)["format"]["duration"])
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("invalid audio duration") from None
        overlap = float(audio_crossfade_seconds)
        if not math.isfinite(length) or length <= overlap * 3:
            raise ValueError("audio must be longer than three crossfade intervals")
        # Rotate the loop at the overlap point. Its end is an equal-power
        # crossfade between the original tail and head. Repetition joins at
        # the same original waveform position, not at an abrupt reset.
        filt = (
            f"[0:a]atrim=start={overlap}:end={length-overlap},asetpts=PTS-STARTPTS[mid];"
            f"[0:a]atrim=start={length-overlap}:end={length},asetpts=PTS-STARTPTS[tail];"
            f"[0:a]atrim=start=0:end={overlap},asetpts=PTS-STARTPTS[head];"
            f"[tail][head]acrossfade=d={overlap}:c1=qsin:c2=qsin[fade];"
            f"[mid][fade]concat=n=2:v=0:a=1[out]"
        )
        try:
            subprocess.run([
                ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror",
                "-i", str(audio), "-filter_complex", filt,
                "-map", "[out]", "-c:a", "pcm_s16le", "-y", str(audio_loop),
            ], check=True, capture_output=True, timeout=120)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if audio_loop.exists():
                audio_loop.unlink()
            raise RuntimeError("audio crossfade preparation failed") from None
    command = [
        ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror",
        "-stream_loop", "-1", "-i", str(video),
        "-stream_loop", "-1", "-i", str(audio_loop if audio_crossfade_seconds else audio),
        "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration_seconds),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart", "-y", str(temp),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True,
                       timeout=max(60, int(duration_seconds * 3)))
        gate, report = inspect_video(str(temp))
        if gate.decision is not Decision.ACCEPT:
            raise RuntimeError("rendered media metadata rejected")
        if abs(report["duration_seconds"] - duration_seconds) > 0.35:
            raise RuntimeError("rendered duration does not match")
        if not report["audio_present"]:
            raise RuntimeError("rendered audio missing")
        if decode_video(str(temp), timeout=min(180, max(60, duration_seconds * 2))).decision is not Decision.ACCEPT:
            raise RuntimeError("rendered media full decode rejected")
        temp.replace(output)
        return str(output)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("ambient video render failed") from None
    finally:
        if temp.exists():
            temp.unlink()
        if audio_loop.exists():
            audio_loop.unlink()

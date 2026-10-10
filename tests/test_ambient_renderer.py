import shutil
import subprocess

import pytest

from media_omega.ambient_renderer import render_ambient_loop
from media_omega.media_probe import inspect_video, decode_video
from media_omega.models import Decision


def test_rejects_missing_sources_and_bad_duration(tmp_path):
    with pytest.raises(ValueError, match="duration"):
        render_ambient_loop("missing", "missing", str(tmp_path / "out.mp4"), duration_seconds=-1)
    with pytest.raises(ValueError, match="source"):
        render_ambient_loop("missing", "missing", str(tmp_path / "out.mp4"), duration_seconds=2)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="real ffmpeg and ffprobe required")
def test_actual_loop_render_has_audio_correct_duration_and_replay_protection(tmp_path):
    video = tmp_path / "clip.mp4"
    audio = tmp_path / "music.m4a"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-nostdin", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=8",
        "-t", "1", "-c:v", "mpeg4", "-y", str(video),
    ], check=True, capture_output=True, timeout=40)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-nostdin", "-v", "error",
        "-f", "lavfi", "-i", "sine=frequency=400:sample_rate=44100",
        "-t", "1", "-c:a", "aac", "-y", str(audio),
    ], check=True, capture_output=True, timeout=40)
    output = tmp_path / "result.mp4"
    result = render_ambient_loop(str(video), str(audio), str(output), duration_seconds=2.5)
    assert result == str(output.resolve())
    gate, report = inspect_video(result)
    assert gate.decision is Decision.ACCEPT
    assert report["audio_present"]
    assert abs(report["duration_seconds"] - 2.5) < 0.35
    assert decode_video(result).decision is Decision.ACCEPT
    with pytest.raises(ValueError, match="already exists"):
        render_ambient_loop(str(video), str(audio), str(output), duration_seconds=2.5)

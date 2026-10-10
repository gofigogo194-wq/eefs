from pathlib import Path
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
    result = render_ambient_loop(str(video), str(audio), str(output), duration_seconds=2.5, audio_crossfade_seconds=0.15, video_crossfade_seconds=0.15)
    assert result == str(output.resolve())
    gate, report = inspect_video(result)
    assert gate.decision is Decision.ACCEPT
    assert report["audio_present"]
    assert abs(report["duration_seconds"] - 2.5) < 0.35
    assert decode_video(result).decision is Decision.ACCEPT
    with pytest.raises(ValueError, match="already exists"):
        render_ambient_loop(str(video), str(audio), str(output), duration_seconds=2.5)


def test_crossfade_validation_rejects_bad_overlap(tmp_path):
    with pytest.raises(ValueError, match="audio crossfade"):
        render_ambient_loop("none", "none", str(tmp_path / "out.mp4"), duration_seconds=2, audio_crossfade_seconds=-0.1)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="real ffmpeg and ffprobe required")
def test_crossfade_rejects_too_short_audio(tmp_path):
    video = tmp_path / "clip.mp4"
    audio = tmp_path / "short.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=size=320x240:rate=5",
                    "-t", "1", "-c:v", "mpeg4", "-y", str(video)],
                   check=True, capture_output=True, timeout=30)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=500",
                    "-t", "0.2", "-y", str(audio)], check=True, capture_output=True, timeout=30)
    with pytest.raises(ValueError, match="three crossfade"):
        render_ambient_loop(str(video), str(audio), str(tmp_path / "result.mp4"),
                            duration_seconds=1, audio_crossfade_seconds=0.1)


def test_video_crossfade_validation(tmp_path):
    with pytest.raises(ValueError, match="video crossfade"):
        render_ambient_loop("none", "none", str(tmp_path / "out.mp4"),
                            duration_seconds=2, video_crossfade_seconds=float("nan"))


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="real ffmpeg and ffprobe required")
def test_visual_crossfade_rejects_undersized_source(tmp_path):
    video = tmp_path / "tiny.mp4"
    audio = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=160x160:rate=24", "-t", "0.20",
                    "-c:v", "mpeg4", "-y", str(video)],
                   check=True, capture_output=True, timeout=30)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=400", "-t", "1", "-y", str(audio)],
                   check=True, capture_output=True, timeout=30)
    with pytest.raises(ValueError, match="three crossfade"):
        render_ambient_loop(str(video), str(audio), str(tmp_path / "result.mp4"),
                            duration_seconds=1, video_crossfade_seconds=0.10)


def test_segment_loop_validation_rejects_bad_period(tmp_path):
    for value in (0, -1, float("nan"), 301, True):
        with pytest.raises(ValueError, match="loop segment"):
            render_ambient_loop("none", "none", str(tmp_path / "out.mp4"),
                                duration_seconds=2, video_crossfade_seconds=0.5,
                                video_loop_segment_seconds=value)
    with pytest.raises(ValueError, match="video crossfade required"):
        render_ambient_loop("none", "none", str(tmp_path / "out.mp4"),
                            duration_seconds=2, video_loop_segment_seconds=5)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="real FFmpeg required")
def test_short_segment_loops_without_processing_whole_source(tmp_path):
    video = tmp_path / "six_seconds.mp4"
    audio = tmp_path / "one_second.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=160x160:rate=24", "-t", "6",
                    "-c:v", "mpeg4", "-y", str(video)],
                   check=True, capture_output=True, timeout=40)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=450", "-t", "1", "-y", str(audio)],
                   check=True, capture_output=True, timeout=30)
    result = render_ambient_loop(str(video), str(audio), str(tmp_path / "created.mp4"),
                                 duration_seconds=7,
                                 video_crossfade_seconds=0.7,
                                 video_loop_segment_seconds=3)
    assert Path(result).exists()
    gate, report = inspect_video(result)
    assert gate.decision is Decision.ACCEPT
    assert abs(report["duration_seconds"] - 7) < 0.35

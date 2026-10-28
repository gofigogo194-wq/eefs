import shutil
import subprocess

import pytest

from media_omega.media_probe import inspect_video, decode_video
from media_omega.models import Decision


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="system ffmpeg and ffprobe required for actual media integration test",
)
def test_actual_generated_mp4_decodes_and_truncated_copy_fails(tmp_path):
    genuine = tmp_path / "original.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=5",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "1.0", "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac",
            "-movflags", "+faststart", str(genuine),
        ],
        check=True, capture_output=True, timeout=40,
    )
    assert genuine.stat().st_size > 0
    # Inspect with the real tool. MPEG4 Part 2 is outside the deliberately
    # narrow supported-codecs allowlist, so upgrade to a real H.264 file.
    h264 = tmp_path / "supported.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-y",
            "-i", str(genuine), "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "copy", str(h264),
        ],
        check=True, capture_output=True, timeout=40,
    )
    gate, report = inspect_video(str(h264))
    assert gate.decision is Decision.ACCEPT
    assert report["video_codec"] == "h264"
    assert report["audio_present"] is True
    assert report["duration_seconds"] > 0
    assert decode_video(str(h264)).decision is Decision.ACCEPT

    # Keep the fast-start header and most of the data, truncate the payload.
    broken = tmp_path / "truncated.mp4"
    data = h264.read_bytes()
    broken.write_bytes(data[:max(1, len(data) // 2)])
    assert decode_video(str(broken)).decision is Decision.BLOCK


def test_decoder_fails_closed_on_invalid_bytes(tmp_path):
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not an mp4")
    result = decode_video(str(invalid))
    assert result.decision is Decision.BLOCK
    assert result.reasons[0] in {"FFMPEG_UNAVAILABLE", "VIDEO_DECODE_FAILED"}

import json
from types import SimpleNamespace

import pytest

from media_omega.media_probe import inspect_video
from media_omega.models import Decision


def payload(codec="h264", audio="aac", duration="12.5"):
    streams = [{"codec_type": "video", "codec_name": codec, "width": 1920, "height": 1080}]
    if audio is not None:
        streams.append({"codec_type": "audio", "codec_name": audio})
    return json.dumps({
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": duration},
        "streams": streams,
    })


def test_probe_accepts_valid_metadata(tmp_path, monkeypatch):
    path = tmp_path / "movie.mp4"
    path.write_bytes(b"file")
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=payload())
    monkeypatch.setattr("media_omega.media_probe.subprocess.run", runner)
    gate, report = inspect_video(str(path))
    assert gate.decision is Decision.ACCEPT
    assert report["video_codec"] == "h264"
    assert report["audio_present"] is True
    assert calls[0][-1] == str(path)


@pytest.mark.parametrize("case,response", [
    ("no_streams", json.dumps({"format": {"duration": "3"}, "streams": []})),
    ("zero_duration", payload(duration="0")),
    ("nan_duration", payload(duration="nan")),
    ("bad_codec", payload(codec="unknown")),
    ("bad_audio", payload(audio="bad")),
    ("bad_json", "{not json"),
    ("missing_format", json.dumps({"streams": []})),
])
def test_probe_blocks_invalid_media(tmp_path, monkeypatch, case, response):
    path = tmp_path / "movie.mp4"
    path.write_bytes(b"file")
    monkeypatch.setattr(
        "media_omega.media_probe.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=response),
    )
    gate, report = inspect_video(str(path))
    assert gate.decision is Decision.BLOCK, case
    assert report == {}


def test_probe_missing_binary_is_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / "movie.mp4"
    path.write_bytes(b"file")
    def absent(*args, **kwargs):
        raise FileNotFoundError("ffprobe")
    monkeypatch.setattr("media_omega.media_probe.subprocess.run", absent)
    gate, _ = inspect_video(str(path))
    assert gate.reasons == ("FFPROBE_UNAVAILABLE",)


def test_probe_timeout_is_fail_closed(tmp_path, monkeypatch):
    import subprocess
    path = tmp_path / "movie.mp4"
    path.write_bytes(b"file")
    def timed(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=20)
    monkeypatch.setattr("media_omega.media_probe.subprocess.run", timed)
    gate, _ = inspect_video(str(path))
    assert gate.reasons == ("FFPROBE_TIMEOUT",)


def test_probe_missing_file_is_fail_closed(tmp_path):
    gate, _ = inspect_video(str(tmp_path / "missing.mp4"))
    assert gate.reasons == ("VIDEO_NOT_FOUND",)

"""One-shot PRIVATE YouTube resumable upload with bounded memory and durable evidence.

Every attempt remains locked across restarts. A 308 acknowledgment for a known,
contiguous chunk is part of the *same* attempt, never a second video insertion.
After an uncertain response there is deliberately no automatic recovery write.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import json
import os
import tempfile

from .youtube_api_readonly import YouTubeReadOnlyAPI


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PrivateUpload:
    ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    MAX_PILOT_BYTES = 100 * 1024 * 1024
    CHUNK_BYTES = 4 * 1024 * 1024  # Multiple of YouTube's 256 KiB alignment.

    def __init__(self, state_dir: str, *, opener=None):
        self.state_dir = Path(state_dir)
        self.opener = opener if opener is not None else build_opener(_NoRedirect())

    @staticmethod
    def _fingerprint(path: Path) -> tuple:
        stat = path.stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

    @staticmethod
    def _digest_file(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _session_url(location: str) -> str:
        if not isinstance(location, str):
            raise RuntimeError("invalid resumable upload session")
        url = urlsplit(location)
        if (url.scheme != "https" or url.netloc != "www.googleapis.com"
                or not url.path.startswith("/upload/youtube/v3/videos")
                or url.fragment or not url.query):
            raise RuntimeError("invalid resumable upload session")
        return location

    @staticmethod
    def _store_marker(marker: Path, record: dict) -> None:
        """Atomic overwrite after initial exclusive-create; never stores credentials."""
        temp = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=marker.parent,
                prefix=marker.stem + "-", suffix=".tmp", delete=False,
            ) as stream:
                temp = Path(stream.name)
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, marker)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)

    @staticmethod
    def _remote_channel_check(api: YouTubeReadOnlyAPI, channel_id: str) -> None:
        if api.get_authenticated_channel().get("id") != channel_id:
            raise RuntimeError("authenticated YouTube channel mismatch")

    def upload_once(self, path: str, *, access_token: str, channel_id: str,
                    title: str, rights_confirmed: bool, preflight,
                    description: str = "") -> dict:
        """Upload a verified local MP4 to the authenticated channel, PRIVATE.

        Only authenticated videos.list readback yields REMOTE_CONFIRMED_PRIVATE.
        Every unexpected network outcome leaves a durable locked marker.
        """
        if rights_confirmed is not True or not callable(preflight):
            raise ValueError("rights and media preflight required")
        if not all(isinstance(x, str) and x.strip() for x in
                   (path, access_token, channel_id, title)):
            raise ValueError("file, authorized channel, token, title required")
        if not isinstance(description, str) or len(title) > 100 or len(description) > 5000:
            raise ValueError("YouTube metadata exceeds maximum length")
        file = Path(path).resolve(strict=True)
        if file.suffix.lower() != ".mp4" or not file.is_file():
            raise ValueError("valid MP4 file required")
        before = self._fingerprint(file)
        size = before[2]
        if size <= 0 or size > self.MAX_PILOT_BYTES:
            raise ValueError("pilot upload requires a nonempty MP4 of at most 100 MiB")
        if preflight(str(file)) is not True:
            raise ValueError("MP4 preflight did not pass")

        # Caller approval alone cannot bypass complete on-disk media validation.
        from .media_probe import inspect_video, decode_video
        from .models import Decision
        gate, report = inspect_video(str(file))
        if gate.decision is not Decision.ACCEPT or not report.get("audio_present"):
            raise ValueError("MP4 inspection rejected source")
        if decode_video(str(file), timeout=180).decision is not Decision.ACCEPT:
            raise ValueError("MP4 full decode rejected source")
        if self._fingerprint(file) != before:
            raise ValueError("MP4 changed during preflight")
        digest = self._digest_file(file)
        if self._fingerprint(file) != before:
            raise ValueError("MP4 changed during digest verification")

        # Authenticated read BEFORE a write catches a changed YouTube identity.
        api = YouTubeReadOnlyAPI(access_token, opener=self.opener)
        self._remote_channel_check(api, channel_id)

        job = sha256((channel_id + "\0" + digest).encode("utf-8")).hexdigest()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        marker = self.state_dir / (job + ".json")
        record = {"state": "REMOTE_UNKNOWN", "sha256": digest,
                  "channel_id": channel_id, "title": title,
                  "size_bytes": size, "video_id": ""}
        # Exclusive create BEFORE any remote write; a crashed job stays locked.
        try:
            with marker.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            raise RuntimeError("Upload already attempted: manual reconciliation required") from None

        try:
            metadata = {"snippet": {"title": title, "description": description,
                                    "categoryId": "10"},
                        "status": {"privacyStatus": "private"}}
            init = Request(self.ENDPOINT, data=json.dumps(metadata).encode("utf-8"),
                           headers={"Authorization": "Bearer " + access_token,
                                    "Content-Type": "application/json; charset=UTF-8",
                                    "X-Upload-Content-Type": "video/mp4",
                                    "X-Upload-Content-Length": str(size)},
                           method="POST")
            with self.opener.open(init, timeout=30) as response:
                if response.getcode() != 200:
                    raise RuntimeError("unexpected session creation status")
                session_url = self._session_url(response.headers.get("Location", ""))

            uploaded = sha256()
            with file.open("rb") as stream:
                offset = 0
                while offset < size:
                    if self._fingerprint(file) != before:
                        raise RuntimeError("MP4 changed before a chunk was sent")
                    piece = stream.read(min(self.CHUNK_BYTES, size - offset))
                    if not piece:
                        raise RuntimeError("MP4 truncated during upload")
                    end = offset + len(piece) - 1
                    uploaded.update(piece)
                    request = Request(session_url, data=piece, method="PUT", headers={
                        "Authorization": "Bearer " + access_token,
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(piece)),
                        "Content-Range": f"bytes {offset}-{end}/{size}",
                    })
                    try:
                        with self.opener.open(request, timeout=180) as response:
                            code = response.getcode()
                            response_headers = response.headers
                            payload_bytes = response.read(65537) if code in (200, 201) else b""
                    except HTTPError as exc:
                        if exc.code != 308:
                            raise
                        code, response_headers, payload_bytes = 308, exc.headers, b""
                    if end < size - 1:
                        if code != 308 or response_headers.get("Range") != f"bytes=0-{end}":
                            raise RuntimeError("noncontiguous upload acknowledgment")
                        offset = end + 1
                        continue
                    if code not in (200, 201) or len(payload_bytes) > 65536:
                        raise RuntimeError("final upload response unconfirmed")
                    try:
                        payload = json.loads(payload_bytes)
                    except (ValueError, UnicodeError):
                        raise RuntimeError("invalid final upload response") from None
                    break

            if self._fingerprint(file) != before or uploaded.hexdigest() != digest:
                raise RuntimeError("transmitted MP4 differs from preflight digest")
            if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not payload["id"]:
                raise RuntimeError("upload response missing video ID")
            video_id = payload["id"]
            snippet, status = payload.get("snippet"), payload.get("status")
            if (not isinstance(snippet, dict) or snippet.get("channelId") != channel_id
                    or not isinstance(status, dict) or status.get("privacyStatus") != "private"):
                raise RuntimeError("upload response channel/privacy mismatch")

            # Store the ID before any readback for later manual reconciliation.
            record["video_id"] = video_id
            self._store_marker(marker, record)
            self._remote_channel_check(api, channel_id)
            video = api.get_video(video_id)
            if (not isinstance(video, dict) or video.get("id") != video_id
                    or video.get("channel_id") != channel_id
                    or video.get("privacy_status") != "private"):
                raise RuntimeError("authenticated private video readback unconfirmed")
            record["state"] = "REMOTE_CONFIRMED_PRIVATE"
            self._store_marker(marker, record)
            return {"video_id": video_id, "state": "REMOTE_CONFIRMED_PRIVATE",
                    "url": "https://www.youtube.com/watch?v=" + video_id,
                    "channel_id": channel_id}
        except Exception:
            # No tokens, session URLs, or server bodies leak into the UI.
            raise RuntimeError("YouTube upload outcome unknown; do not retry automatically") from None

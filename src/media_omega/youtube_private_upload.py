"""One-shot private YouTube resumable upload. No automatic retries or public posts."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PrivateUpload:
    ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"

    def __init__(self, state_dir: str, *, opener=None):
        self.state_dir = Path(state_dir)
        self.opener = opener if opener is not None else build_opener(_NoRedirect())

    def upload_once(self, path: str, *, access_token: str, channel_id: str,
                    title: str, rights_confirmed: bool, preflight,
                    description: str = "") -> dict:
        """Single upload attempt; never retries indeterminate remote writes.

        preflight(path) must independently verify full MP4 decode and account
        binding before this method. This boundary validates a fresh digest.
        """
        if rights_confirmed is not True or not callable(preflight):
            raise ValueError("rights and media preflight required")
        if not all(isinstance(x, str) and x.strip() for x in
                   (path, access_token, channel_id, title)):
            raise ValueError("file, authorized channel, token, title required")
        file = Path(path).resolve(strict=True)
        if file.suffix.lower() != ".mp4" or not file.is_file() or file.stat().st_size <= 0:
            raise ValueError("valid MP4 file required")
        if file.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("pilot upload limited to 100 MiB; no network attempt")
        if len(title) > 100 or len(description) > 5000:
            raise ValueError("YouTube metadata exceeds maximum length")
        checked = preflight(str(file))
        if checked is not True:
            raise ValueError("MP4 preflight did not pass")
        original = file.read_bytes()
        digest = sha256(original).hexdigest()
        job = sha256((channel_id + "\0" + digest).encode()).hexdigest()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        marker = self.state_dir / (job + ".json")
        # Exclusive create BEFORE any remote write. Crash implies UNKNOWN.
        try:
            with marker.open("x", encoding="utf-8") as stream:
                json.dump({"state": "REMOTE_UNKNOWN", "sha256": digest,
                           "channel_id": channel_id, "title": title}, stream)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            raise RuntimeError("Upload already attempted: manual reconciliation required") from None
        metadata = {"snippet": {"title": title, "description": description,
                                 "categoryId": "10"},
                    "status": {"privacyStatus": "private"}}
        request = Request(self.ENDPOINT, data=json.dumps(metadata).encode("utf-8"),
                          headers={"Authorization": "Bearer " + access_token,
                                   "Content-Type": "application/json; charset=UTF-8",
                                   "X-Upload-Content-Type": "video/mp4",
                                   "X-Upload-Content-Length": str(len(original))},
                          method="POST")
        try:
            with self.opener.open(request, timeout=30) as response:
                session_url = response.headers.get("Location", "")
                if not isinstance(session_url, str) or not session_url.startswith(
                        "https://www.googleapis.com/upload/youtube/v3/"):
                    raise RuntimeError("Unexpected YouTube resumable session location")
            if sha256(file.read_bytes()).hexdigest() != digest:
                raise RuntimeError("MP4 changed before upload")
            upload = Request(session_url, data=original, method="PUT", headers={
                "Authorization": "Bearer " + access_token,
                "Content-Type": "video/mp4", "Content-Length": str(len(original))})
            with self.opener.open(upload, timeout=180) as response:
                payload = json.loads(response.read(65537))
            if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
                raise RuntimeError("Upload returned no video identifier")
            if payload.get("status", {}).get("privacyStatus") != "private":
                raise RuntimeError("YouTube private status unconfirmed")
            if payload.get("snippet", {}).get("channelId") != channel_id:
                raise RuntimeError("YouTube channel binding unconfirmed")
            # Remote readback is still required to finalize, so keep UNKNOWN.
            return {"video_id": payload["id"], "state": "REMOTE_UNKNOWN",
                    "reason": "Upload response received; authenticated readback pending"}
        except (HTTPError, URLError, OSError, TimeoutError, ValueError, RuntimeError):
            raise RuntimeError("YouTube upload outcome unknown; do not retry automatically") from None

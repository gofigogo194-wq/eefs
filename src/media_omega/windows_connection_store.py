"""Version-stable Windows user-profile storage, protected by user-scoped DPAPI.

Nothing secret is written to the repository, executable folder, or plaintext
configuration. OAuth access tokens are intentionally never persisted.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class WindowsDPAPI:
    """Protect for the current Windows logon user, never LOCAL_MACHINE."""

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("Windows secure storage is unavailable")
        self._crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._crypt.CryptProtectData.argtypes = [
            ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
        ]
        self._crypt.CryptProtectData.restype = wintypes.BOOL
        self._crypt.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
        ]
        self._crypt.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel.LocalFree.restype = ctypes.c_void_p

    def _call(self, data: bytes, *, decrypt: bool) -> bytes:
        if not isinstance(data, bytes) or not data:
            raise ValueError("nonempty protected payload required")
        source = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        input_blob = _Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
        output_blob = _Blob()
        if decrypt:
            ok = self._crypt.CryptUnprotectData(
                ctypes.byref(input_blob), None, None, None, None,
                0x01, ctypes.byref(output_blob),
            )
        else:
            ok = self._crypt.CryptProtectData(
                ctypes.byref(input_blob), "MEDIA OMEGA YouTube connection",
                None, None, None, 0x01, ctypes.byref(output_blob),
            )
        if not ok:
            raise RuntimeError("Windows could not protect or unlock saved connection")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            self._kernel.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))

    def protect(self, raw: bytes) -> bytes:
        return self._call(raw, decrypt=False)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return self._call(ciphertext, decrypt=True)


class WindowsConnectionStore:
    """Same profile across extracted EXE versions, not across Windows accounts."""

    KEYS = ("client_id", "client_secret", "channel_id", "api_key", "refresh_token")
    VERSION = 1

    def __init__(self, *, path: Path | None = None, protector=None):
        location = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        self.path = Path(path) if path is not None else (
            Path(location) / "MEDIA_OMEGA" / "youtube_connection.v1.dpapi"
        )
        self._protector = protector if protector is not None else WindowsDPAPI()

    @classmethod
    def _validated(cls, profile: dict) -> dict:
        if not isinstance(profile, dict) or not set(profile).issubset(cls.KEYS):
            raise ValueError("invalid saved connection fields")
        clean = {}
        for key in cls.KEYS:
            value = profile.get(key, "")
            if not isinstance(value, str) or len(value) > 8192:
                raise ValueError("invalid saved connection value")
            clean[key] = value
        if clean["refresh_token"] and (not clean["client_id"] or not clean["channel_id"]):
            raise ValueError("refresh token without channel binding")
        return clean

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            ciphertext = self.path.read_bytes()
            if len(ciphertext) > 128 * 1024:
                raise ValueError("encrypted connection file is too large")
            data = json.loads(self._protector.unprotect(ciphertext))
            if not isinstance(data, dict) or data.get("version") != self.VERSION:
                raise ValueError("unknown connection version")
            return self._validated(data.get("profile"))
        except (OSError, ValueError, UnicodeError, RuntimeError) as exc:
            raise RuntimeError("Saved connection cannot be opened; it was not changed") from None

    def save(self, profile: dict) -> None:
        clean = self._validated(profile)
        raw = json.dumps({"version": self.VERSION, "profile": clean},
                         ensure_ascii=False, sort_keys=True).encode("utf-8")
        encrypted = self._protector.protect(raw)
        if not isinstance(encrypted, bytes) or not encrypted:
            raise RuntimeError("Windows secure storage failed")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.path.parent, prefix="conn-",
                suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def forget(self) -> None:
        self.path.unlink(missing_ok=True)

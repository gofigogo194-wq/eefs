"""Single-use local OAuth callback receiver with an OS-assigned free loopback port.

The receiver is bound ONLY to 127.0.0.1. It validates a cryptographic
OAuth state before returning a callback to the in-memory exchange session.
No callback URLs, authorization codes, cookies or credentials are logged.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Full, Queue
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from .youtube_oauth_readonly import validate_callback_state


class _LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class LoopbackOAuthReceiver:
    """Reserve an available port, accept one matching callback and shut down."""

    MAX_REQUEST_TARGET = 8192

    def __init__(self):
        self._callbacks: Queue[str] = Queue(maxsize=1)
        self._expected_state: str | None = None
        self._claimed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            # Suppress BaseHTTPRequestHandler access logs, which otherwise
            # disclose the one-time Google authorization code in the URL.
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                if len(self.path) > owner.MAX_REQUEST_TARGET:
                    self._respond(414, b"Invalid authorization response.")
                    return
                parsed = urlsplit(self.path)
                if parsed.path != "/" or parsed.fragment:
                    self._respond(404, b"Not found.")
                    return
                params = parse_qs(parsed.query, keep_blank_values=True)
                states = params.get("state", [])
                if (owner._expected_state is None or len(states) != 1 or
                        not validate_callback_state(owner._expected_state, states[0])):
                    self._respond(400, b"Authorization state mismatch. Return to MEDIA OMEGA.")
                    return
                if owner._claimed:
                    self._respond(409, b"Authorization already received.")
                    return
                # A matching-state callback is a single-use attempt. The
                # exchange layer still validates origin, issuer, scope and code.
                try:
                    owner._callbacks.put_nowait(owner.redirect_uri + "?" + parsed.query)
                except Full:
                    self._respond(409, b"Authorization already received.")
                    return
                owner._claimed = True
                self._respond(200,
                              b"MEDIA OMEGA received Google authorization. "
                              b"Return to the MEDIA OMEGA application.")

            def _respond(self, status: int, body: bytes):
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Pragma", "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        # Port=0 is allocated by Windows/Linux kernel; never assumes 8765
        # belongs to us. Binding reserves the exact port until completion.
        self._server = _LocalHTTPServer(("127.0.0.1", 0), Handler)
        self.redirect_uri = f"http://127.0.0.1:{self._server.server_port}/"
        self._thread: Thread | None = None

    def start(self, expected_state: str) -> None:
        if self._thread is not None or not isinstance(expected_state, str) or not expected_state:
            raise ValueError("invalid or repeated OAuth receiver start")
        self._expected_state = expected_state
        self._thread = Thread(target=self._server.serve_forever,
                              kwargs={"poll_interval": 0.05},
                              name="MEDIA-OMEGA-OAuth-loopback", daemon=True)
        self._thread.start()

    def take_callback(self) -> str | None:
        try:
            return self._callbacks.get_nowait()
        except Empty:
            return None

    def close(self) -> None:
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=2)
            self._thread = None
        self._server.server_close()

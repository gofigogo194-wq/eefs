"""Windows desktop: YouTube discovery, licensed MP4 creation and opt-in PRIVATE upload.

Run: python -m media_omega.desktop
No public publishing or downloading others' videos. Secrets use Windows DPAPI.
"""
from __future__ import annotations

import json
from dataclasses import replace
import webbrowser
import os
import sys
from time import time
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from .ambient_renderer import render_ambient_loop
from .youtube_api_readonly import YouTubeReadOnlyAPI
from .youtube_connection import UploadConnectionSession, renew_saved_upload_connection
from .youtube_private_upload import PrivateUpload
from .windows_connection_store import WindowsConnectionStore
from .youtube_loopback import LoopbackOAuthReceiver


def find_popular(region: str, count: int, api_key: str = "") -> list[dict]:
    token = os.environ.get("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN", "")
    key = api_key.strip() or os.environ.get("MEDIA_OMEGA_YOUTUBE_API_KEY", "")
    if not token and not key:
        raise ValueError("Enter a YouTube API key to search public popular videos")
    return YouTubeReadOnlyAPI(token, api_key=key).get_popular_videos(region_code=region, max_results=count)



def find_topic(query: str, region: str, count: int, api_key: str = "",
               recent_days: int | None = None) -> list[dict]:
    token = os.environ.get("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN", "")
    key = api_key.strip() or os.environ.get("MEDIA_OMEGA_YOUTUBE_API_KEY", "")
    if not token and not key:
        raise ValueError("Enter a YouTube API key to search videos")
    return YouTubeReadOnlyAPI(token, api_key=key).search_topic_videos(
        query, region_code=region, max_results=count, recent_days=recent_days)



def format_topic_results(data: list[dict]) -> str:
    """Plain-text video listings with real line breaks, never literal backslash-n."""
    lines = []
    for i, item in enumerate(data, 1):
        lines.append(
            f'{i}. {item["title"]} — {item["views"]} views\n'
            f'Channel: {item["channel_title"]} | Published: {item["published_at"]}'
            f' | Duration: {item["duration_iso"]}\n'
            f'{item["url"]}\nRights: NOT VERIFIED'
        )
    return "\n\n".join(lines) or "No videos found"


def create_local_video(video: str, audio: str, output: str, duration: float,
                       rights_confirmed: bool, loop_seconds: float = 5.0) -> str:
    if not rights_confirmed:
        raise ValueError("Confirm that you have rights to the video and audio")
    return render_ambient_loop(video, audio, output, duration_seconds=duration,
                               video_crossfade_seconds=0.7,
                               video_loop_segment_seconds=loop_seconds,
                               audio_crossfade_seconds=0.15)


def main() -> int:
    # PyInstaller onedir deployment carries media tools beside the exe.
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        os.environ["PATH"] = str(executable_dir) + os.pathsep + os.environ.get("PATH", "")
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    root = tk.Tk()
    root.title("MEDIA Ω — Video Workshop")
    root.geometry("940x910")
    root.minsize(630, 510)

    # Stable Windows-user profile, never beside the EXE or in the ZIP.
    store = None
    saved = {}
    saved_error = False
    try:
        store = WindowsConnectionStore()
        saved = store.load() or {}
    except RuntimeError:
        saved_error = True

    region = tk.StringVar(value="TH")
    count = tk.StringVar(value="10")
    api_key = tk.StringVar(value=saved.get("api_key", ""))
    oauth_client = tk.StringVar(value=saved.get("client_id", ""))
    oauth_secret = tk.StringVar(value=saved.get("client_secret", ""))
    channel_id = tk.StringVar(value=saved.get("channel_id", ""))
    oauth_session = [None]
    oauth_listener = [None]
    oauth_started_at = [0.0]
    verified_account = [None]
    session_credentials = [None]
    oauth_pending_credentials = [None]
    upload_file = tk.StringVar()
    upload_title = tk.StringVar(value="Relaxing Nature Sounds — Private Test")
    upload_description = tk.StringVar(value="Private pilot upload — RELAX SABAI MUSIK")
    topic = tk.StringVar(value="relaxing nature sounds")
    freshness = tk.StringVar(value="Any")
    video = tk.StringVar()
    audio = tk.StringVar()
    output = tk.StringVar()
    duration = tk.StringVar(value="60")
    loop_seconds = tk.StringVar(value="5")
    rights = tk.BooleanVar(value=False)
    status = tk.StringVar(value=(
        "Stored connection cannot be unlocked; old data has not been changed."
        if saved_error else
        "Saved Google settings loaded; verifying saved channel."
        if saved.get("refresh_token") else
        "Saved fields restored; Google reconnect needed."
        if saved else "Ready. PRIVATE upload is manual only."
    ))
    work: Queue = Queue()
    active = [False]

    # Status stays visible at the window bottom even when content needs scrolling.
    status_bar = ttk.Label(root, textvariable=status, padding=(12, 7), wraplength=880)
    status_bar.pack(side="bottom", fill="x")
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="MEDIA Ω — Find & Create", font=("Segoe UI", 17, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Popular videos are references only. Use your own or licensed media for rendering.").pack(anchor="w", pady=(4, 14))
    top = ttk.LabelFrame(frame, text="1. Popular YouTube videos (read only)", padding=10)
    top.pack(fill="x")
    row = ttk.Frame(top)
    row.pack(fill="x")
    ttk.Label(row, text="Region").pack(side="left")
    ttk.Entry(row, textvariable=region, width=5).pack(side="left", padx=6)
    ttk.Label(row, text="Count").pack(side="left")
    ttk.Entry(row, textvariable=count, width=5).pack(side="left", padx=6)
    search_btn = ttk.Button(row, text="Find popular videos")
    search_btn.pack(side="left", padx=8)
    key_row = ttk.Frame(top)
    key_row.pack(fill="x", pady=(8, 0))
    ttk.Label(key_row, text="YouTube API key").pack(side="left")
    ttk.Entry(key_row, textvariable=api_key, show="*", width=46).pack(side="left", padx=6, fill="x", expand=True)
    ttk.Label(key_row, text="Saved with Windows encryption").pack(side="left")
    topic_row = ttk.Frame(top)
    topic_row.pack(fill="x", pady=(7, 0))
    ttk.Label(topic_row, text="Topic").pack(side="left")
    ttk.Entry(topic_row, textvariable=topic, width=40).pack(side="left", padx=6, fill="x", expand=True)
    ttk.Label(topic_row, text="Published").pack(side="left", padx=(8, 0))
    ttk.Combobox(topic_row, textvariable=freshness, values=("Any", "7 days", "30 days", "90 days"), state="readonly", width=8).pack(side="left", padx=5)
    topic_btn = ttk.Button(topic_row, text="Find by topic (100 quota units)")
    topic_btn.pack(side="left")
    results = tk.Text(top, height=10, wrap="word", state="disabled")
    results.pack(fill="both", expand=True, pady=(8, 0))
    ttk.Label(top, text="Reuse rights are NOT verified. This list does not download videos.").pack(anchor="w")

    account = ttk.LabelFrame(frame, text="YouTube account — verify before private upload", padding=10)
    account.pack(fill="x", pady=(10, 0))
    account_row = ttk.Frame(account)
    account_row.pack(fill="x")
    ttk.Label(account_row, text="OAuth client ID").pack(side="left")
    ttk.Entry(account_row, textvariable=oauth_client, width=32).pack(side="left", padx=5)
    ttk.Label(account_row, text="Expected channel ID").pack(side="left")
    ttk.Entry(account_row, textvariable=channel_id, width=22).pack(side="left", padx=5)
    secret_row = ttk.Frame(account)
    secret_row.pack(fill="x", pady=(4, 0))
    ttk.Label(secret_row, text="Desktop client secret").pack(side="left")
    ttk.Entry(secret_row, textvariable=oauth_secret, show="*", width=35).pack(side="left", padx=5)
    ttk.Label(secret_row, text="Encrypted in Windows when saved").pack(side="left")
    save_btn = ttk.Button(account, text="Save connection settings")
    save_btn.pack(anchor="w", pady=(4, 0))
    forget_btn = ttk.Button(account, text="Disconnect and forget saved account")
    forget_btn.pack(anchor="w", pady=(4, 0))
    connect_btn = ttk.Button(account, text="1. Open Google authorization")
    connect_btn.pack(anchor="w", pady=(6, 0))
    finish_btn = ttk.Button(account, text="Cancel Google authorization")
    finish_btn.pack(anchor="w", pady=(4, 0))

    bottom = ttk.LabelFrame(frame, text="2. Create local MP4 from licensed sources", padding=10)
    bottom.pack(fill="x", pady=(12, 0))

    def file_row(name: str, variable, chooser):
        line = ttk.Frame(bottom)
        line.pack(fill="x", pady=3)
        ttk.Label(line, text=name, width=11).pack(side="left")
        ttk.Entry(line, textvariable=variable).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(line, text="Browse", command=chooser).pack(side="left")

    file_row("Video", video, lambda: video.set(filedialog.askopenfilename(title="Choose source video") or video.get()))
    file_row("Music", audio, lambda: audio.set(filedialog.askopenfilename(title="Choose licensed audio") or audio.get()))
    file_row("Output MP4", output, lambda: output.set(filedialog.asksaveasfilename(title="Choose output MP4", defaultextension=".mp4", filetypes=[("MP4", "*.mp4")]) or output.get()))
    line = ttk.Frame(bottom)
    line.pack(fill="x", pady=8)
    ttk.Label(line, text="Seconds").pack(side="left")
    ttk.Entry(line, textvariable=duration, width=10).pack(side="left", padx=8)
    ttk.Label(line, text="Loop clip (s)").pack(side="left", padx=(10, 0))
    ttk.Entry(line, textvariable=loop_seconds, width=8).pack(side="left", padx=6)
    ttk.Checkbutton(bottom, text="I have permission to use BOTH the video and music", variable=rights).pack(anchor="w")
    render_btn = ttk.Button(bottom, text="Create MP4")
    render_btn.pack(anchor="w", pady=(8, 0))

    upload_area = ttk.LabelFrame(frame, text="3. First private YouTube upload (manual only, max 100 MiB)", padding=10)
    upload_area.pack(fill="x", pady=(10, 0))
    file_line = ttk.Frame(upload_area)
    file_line.pack(fill="x")
    ttk.Label(file_line, text="Verified MP4").pack(side="left")
    ttk.Entry(file_line, textvariable=upload_file).pack(side="left", fill="x", expand=True, padx=6)
    ttk.Button(file_line, text="Browse", command=lambda: upload_file.set(
        filedialog.askopenfilename(title="Choose MP4 for private upload", filetypes=[("MP4", "*.mp4")])
        or upload_file.get())).pack(side="left")
    title_line = ttk.Frame(upload_area)
    title_line.pack(fill="x", pady=(6, 0))
    ttk.Label(title_line, text="Video title").pack(side="left")
    ttk.Entry(title_line, textvariable=upload_title).pack(side="left", fill="x", expand=True, padx=6)
    description_line = ttk.Frame(upload_area)
    description_line.pack(fill="x", pady=(6, 0))
    ttk.Label(description_line, text="Description").pack(side="left")
    ttk.Entry(description_line, textvariable=upload_description).pack(
        side="left", fill="x", expand=True, padx=6)
    upload_btn = ttk.Button(upload_area, text="Upload PRIVATE once (no automatic retry)")
    upload_btn.pack(anchor="w", pady=(6, 0))
    check_btn = ttk.Button(upload_area, text="Check previous upload (read only)")
    check_btn.pack(anchor="w", pady=(4, 0))

    ttk.Label(frame, textvariable=status, wraplength=740).pack(anchor="w", pady=(12, 0))
    ttk.Label(frame, text="Manual PRIVATE upload only. Public publication is disabled.", foreground="#666").pack(anchor="w")

    def run_task(task, success):
        if active[0]:
            return
        active[0] = True
        search_btn.configure(state="disabled")
        topic_btn.configure(state="disabled")
        render_btn.configure(state="disabled")
        upload_btn.configure(state="disabled")
        check_btn.configure(state="disabled")
        save_btn.configure(state="disabled")
        forget_btn.configure(state="disabled")
        status.set("Working...")

        def worker():
            try:
                work.put((success, task(), None))
            except Exception as exc:
                # Never print HTTP exception details: URLs can contain API credentials.
                oauth_safe_errors = {
                    "OAuth exchange failed or outcome uncertain",
                    "invalid OAuth token response",
                    "OAuth access token missing",
                    "invalid token lifetime",
                    "unexpected OAuth scopes",
                    "OAuth token response too large",
                    "OAuth code exchange already attempted",
                    "channel verification failed: EXPECTED_CHANNEL_REQUIRED",
                    "channel verification failed: AUTHENTICATED_CHANNEL_READ_FAILED",
                    "channel verification failed: AUTHENTICATED_CHANNEL_MISMATCH",
                    "Upload already attempted: manual reconciliation required",
                    "YouTube upload outcome unknown; do not retry automatically",
                    "YouTube readback failed; do not retry upload",
                    "Private readback inconclusive; do not retry upload",
                    "Stored Google connection requires reauthorization",
                    "Saved YouTube channel verification failed",
                    "Google refresh access token missing",
                    "Google refresh scope does not match upload permission",
                    "Google session expired; reconnect before upload",
                }
                if isinstance(exc, ValueError):
                    message = str(exc)
                elif isinstance(exc, RuntimeError) and (str(exc) in oauth_safe_errors or str(exc).startswith("Google token exchange rejected: HTTP ") or str(exc) == "Google token endpoint unreachable or timed out"):
                    message = str(exc)
                else:
                    message = "API or media operation failed (" + type(exc).__name__ + ")"
                work.put((success, None, message))

        Thread(target=worker, daemon=True).start()

    def show_results(data):
        lines = [f'{i}. {x["title"]} — {x["views"]} views\n{x["url"]}\nRights: NOT VERIFIED\n'
                 for i, x in enumerate(data, 1)]
        results.configure(state="normal")
        results.delete("1.0", "end")
        results.insert("1.0", "\n".join(lines) or "No videos returned")
        results.configure(state="disabled")
        status.set(f"Found {len(data)} popular videos. No files downloaded.")

    def show_render(path):
        status.set("MP4 created and verified: " + str(path))
        messagebox.showinfo("MEDIA Ω", "MP4 created. Review it before any publication.")

    def start_find():
        try:
            n = int(count.get())
            code = region.get().strip().upper()
        except ValueError:
            status.set("Invalid count")
            return
        run_task(lambda: find_popular(code, n, api_key.get()), show_results)

    def start_topic():
        try:
            n = int(count.get())
        except ValueError:
            status.set("Invalid count")
            return
        days = {"Any": None, "7 days": 7, "30 days": 30, "90 days": 90}.get(freshness.get())
        run_task(lambda: find_topic(topic.get(), region.get().strip().upper(),
                                    n, api_key.get(), days), show_topic_results)

    def show_topic_results(data):
        results.configure(state="normal")
        results.delete("1.0", "end")
        results.insert("1.0", format_topic_results(data))
        results.configure(state="disabled")
        status.set(f"Found {len(data)} videos by topic (relevance order, NOT a trending rank).")

    def start_render():
        try:
            seconds = float(duration.get())
            loop = float(loop_seconds.get())
        except ValueError:
            status.set("Invalid duration")
            return
        if not rights.get():
            status.set("Confirm rights to both inputs before rendering")
            return
        args = (video.get(), audio.get(), output.get(), seconds, bool(rights.get()), loop)
        run_task(lambda: create_local_video(*args), show_render)

    def current_settings(*, refresh_token=""):
        return {
            "client_id": oauth_client.get().strip(),
            "client_secret": oauth_secret.get().strip(),
            "channel_id": channel_id.get().strip(),
            "api_key": api_key.get().strip(),
            "refresh_token": refresh_token,
        }

    def save_current_settings():
        if store is None:
            status.set("Secure Windows storage is not available")
            return
        try:
            old = store.load() or {}
            fresh = current_settings()
            # Never associate a refresh grant with edited client or channel identity.
            if all(fresh[k] == old.get(k, "") for k in
                   ("client_id", "client_secret", "channel_id")):
                fresh["refresh_token"] = old.get("refresh_token", "")
            store.save(fresh)
            credentials = session_credentials[0]
            if credentials and any(fresh[k] != credentials.get(k, "") for k in
                                   ("client_id", "client_secret", "channel_id")):
                verified_account[0] = None
                session_credentials[0] = None
            status.set("Google connection settings saved securely for future versions.")
        except (RuntimeError, ValueError):
            status.set("Could not securely save settings. Existing connection was not overwritten.")

    def forget_connection():
        if not messagebox.askyesno("MEDIA Ω — Disconnect",
                                   "Forget saved local Google connection and API settings?"):
            return
        if store is None:
            status.set("Secure Windows storage is not available")
            return
        try:
            store.forget()
        except OSError:
            status.set("Could not remove the saved local connection")
            return
        verified_account[0] = None
        session_credentials[0] = None
        oauth_session[0] = None
        oauth_pending_credentials[0] = None
        for variable in (oauth_client, oauth_secret, channel_id, api_key):
            variable.set("")
        status.set("Disconnected locally. Google account permissions may still be granted.")

    def cancel_google_connection(*, silent=False):
        receiver = oauth_listener[0]
        oauth_listener[0] = None
        oauth_session[0] = None
        oauth_pending_credentials[0] = None
        oauth_started_at[0] = 0.0
        if receiver is not None:
            receiver.close()
        if not silent:
            status.set("Google authorization cancelled. Saved connection is untouched.")

    def start_google_connection():
        if active[0]:
            status.set("Finish current operation before connecting Google.")
            return
        cancel_google_connection(silent=True)
        receiver = None
        try:
            details = current_settings()
            if not details["client_id"].endswith(".apps.googleusercontent.com"):
                raise ValueError("OAuth Client ID must end with .apps.googleusercontent.com")
            if not (details["channel_id"].startswith("UC")
                    and len(details["channel_id"]) == 24):
                raise ValueError("Expected Channel ID must be a 24-character UC... channel identifier")
            receiver = LoopbackOAuthReceiver()
            session = UploadConnectionSession(
                details["client_id"], receiver.redirect_uri,
                details["channel_id"], client_secret=details["client_secret"],
            )
            receiver.start(session.authorization.state)
            oauth_pending_credentials[0] = details
            oauth_session[0] = session
            oauth_listener[0] = receiver
            oauth_started_at[0] = time()
            verified_account[0] = None
            if not webbrowser.open(session.authorization_url):
                cancel_google_connection(silent=True)
                status.set("Default browser did not open. Set a default browser and try again.")
                return
            status.set(
                "Google opened. Authorize the correct channel; "
                "MEDIA OMEGA receives the callback automatically on port " +
                receiver.redirect_uri.split(":")[-1].strip("/")
            )
        except (OSError, ValueError, RuntimeError) as exc:
            cancel_google_connection(silent=True)
            if isinstance(exc, ValueError):
                status.set(str(exc))
            else:
                status.set("Cannot start local Google authorization receiver. Try again.")

    def finish_google_connection(callback: str):
        session = oauth_session[0]
        details = oauth_pending_credentials[0]
        if session is None or details is None:
            status.set("Google authorization session is no longer active")
            return
        oauth_session[0] = None
        oauth_pending_credentials[0] = None
        oauth_started_at[0] = 0.0

        def connected(result):
            verified_account[0] = result
            session_credentials[0] = details
            persistence = "Connection is valid for this session only."
            if store is not None:
                try:
                    previous = store.load() or {}
                    # Reuse only a refresh grant bound to this exact client and channel.
                    refresh = result.refresh_token
                    if not refresh and all(details[k] == previous.get(k, "") for k in
                                           ("client_id", "client_secret", "channel_id")):
                        refresh = previous.get("refresh_token", "")
                    store.save({**details, "refresh_token": refresh})
                    verified_account[0] = replace(result, refresh_token=refresh)
                    if refresh:
                        persistence = "Saved securely; future restarts can reconnect automatically."
                    else:
                        persistence = "Settings saved; Google supplied no offline token, so reconnect later."
                except (RuntimeError, ValueError):
                    persistence = "Secure save failed; connection works only for this session."
            status.set("Verified channel " + result.channel_id + ". " + persistence)
            messagebox.showinfo("MEDIA Ω — YouTube", "YouTube channel verified.\n" + persistence)

        run_task(lambda: session.complete(callback), connected)

    def fresh_upload_access_token():
        account = verified_account[0]
        creds = session_credentials[0]
        if account is None or not account.authorized or account.mode != "UPLOAD":
            raise RuntimeError("Google session expired; reconnect before upload")
        if account.refresh_token:
            if not creds or creds["channel_id"] != account.channel_id:
                raise RuntimeError("Google session expired; reconnect before upload")
            renewed = renew_saved_upload_connection(
                creds["client_id"], creds["client_secret"], account.channel_id,
                account.refresh_token,
            )
            if store is not None and renewed.refresh_token != account.refresh_token:
                store.save({**creds, "refresh_token": renewed.refresh_token})
            verified_account[0] = renewed
            return renewed.access_token
        if time() + 60 >= account.expires_at:
            raise RuntimeError("Google session expired; reconnect before upload")
        return account.access_token

    def start_private_upload():
        account = verified_account[0]
        if account is None or not account.authorized or account.mode != "UPLOAD":
            status.set("Connect and verify the YouTube channel first")
            return
        details = session_credentials[0]
        if (channel_id.get().strip() != account.channel_id or details is None or
                oauth_client.get().strip() != details["client_id"] or
                oauth_secret.get().strip() != details["client_secret"]):
            status.set("Google connection fields changed. Verify the channel again.")
            return
        file_path = upload_file.get().strip()
        title_value = upload_title.get().strip()
        if not rights.get():
            status.set("Confirm rights to BOTH original video and audio before upload")
            return
        if not messagebox.askyesno(
            "MEDIA Ω — PRIVATE upload",
            "Send ONE video to the verified channel as PRIVATE?\n"
            "An uncertain result blocks retries to avoid duplicates.\n"
            "No public publication will occur.",
        ):
            return
        def upload_done(result):
            status.set("PRIVATE upload verified through YouTube API: " + result["url"])
            messagebox.showinfo("MEDIA Ω — Private verified",
                                "Uploaded PRIVATE and confirmed for your channel:\n" +
                                result["url"])
        publisher = PrivateUpload(str(Path.home() / ".media_omega" / "upload_attempts"))
        run_task(lambda: publisher.upload_once(
            file_path, access_token=fresh_upload_access_token(), channel_id=account.channel_id,
            title=title_value, description=upload_description.get(),
            rights_confirmed=bool(rights.get()),
            preflight=lambda path: True,
        ), upload_done)

    def check_existing_private_upload():
        account = verified_account[0]
        if account is None or not account.authorized or account.mode != "UPLOAD":
            status.set("Connect and verify the YouTube channel first")
            return
        details = session_credentials[0]
        if (channel_id.get().strip() != account.channel_id or details is None or
                oauth_client.get().strip() != details["client_id"] or
                oauth_secret.get().strip() != details["client_secret"]):
            status.set("Google connection fields changed. Verify the channel again.")
            return
        file_path = upload_file.get().strip()
        def checked(result):
            if result["state"] == "REMOTE_CONFIRMED_PRIVATE":
                status.set("Private YouTube video confirmed: " + result["url"])
                messagebox.showinfo("MEDIA Ω", "PRIVATE confirmed: " + result["url"])
            else:
                status.set(result["reason"])
                messagebox.showwarning("MEDIA Ω — check only", result["reason"])
        verifier = PrivateUpload(str(Path.home() / ".media_omega" / "upload_attempts"))
        run_task(lambda: verifier.reconcile_existing(
            file_path, access_token=fresh_upload_access_token(), channel_id=account.channel_id,
        ), checked)

    search_btn.configure(command=start_find)
    topic_btn.configure(command=start_topic)
    render_btn.configure(command=start_render)
    connect_btn.configure(command=start_google_connection)
    save_btn.configure(command=save_current_settings)
    forget_btn.configure(command=forget_connection)
    finish_btn.configure(command=cancel_google_connection)
    upload_btn.configure(command=start_private_upload)
    check_btn.configure(command=check_existing_private_upload)

    def poll():
        receiver = oauth_listener[0]
        if receiver is not None:
            if time() - oauth_started_at[0] > 600:
                cancel_google_connection(silent=True)
                status.set("Google authorization timed out. Click Open Google authorization again.")
            elif not active[0]:
                callback_url = receiver.take_callback()
                if callback_url is not None:
                    oauth_listener[0] = None
                    receiver.close()
                    finish_google_connection(callback_url)
        try:
            callback, data, error = work.get_nowait()
        except Empty:
            pass
        else:
            active[0] = False
            search_btn.configure(state="normal")
            topic_btn.configure(state="normal")
            render_btn.configure(state="normal")
            upload_btn.configure(state="normal")
            check_btn.configure(state="normal")
            save_btn.configure(state="normal")
            forget_btn.configure(state="normal")
            if error:
                status.set("Operation failed: " + error)
            else:
                callback(data)
        root.after(150, poll)

    root.after(150, poll)

    def close_application():
        cancel_google_connection(silent=True)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_application)

    # No automatic remote write: refresh token and authenticated channel GET only.
    if saved.get("refresh_token") and not saved_error:
        def restored(result):
            verified_account[0] = result
            session_credentials[0] = saved
            if store is not None and result.refresh_token != saved["refresh_token"]:
                try:
                    store.save({**saved, "refresh_token": result.refresh_token})
                except (ValueError, RuntimeError):
                    status.set("Channel verified, but rotated credentials could not be saved.")
                    return
            status.set("Saved YouTube channel verified: " + result.channel_id)
        def restore_on_start():
            run_task(lambda: renew_saved_upload_connection(
                saved["client_id"], saved["client_secret"], saved["channel_id"],
                saved["refresh_token"],
            ), restored)
        root.after(100, restore_on_start)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

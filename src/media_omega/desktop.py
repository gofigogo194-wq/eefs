"""Minimal desktop UI for popular-video discovery and licensed local MP4 rendering.

Run: python -m media_omega.desktop
No publishing, downloading, credential entry or background persistence.
"""
from __future__ import annotations

import json
import webbrowser
import os
import sys
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from .ambient_renderer import render_ambient_loop
from .youtube_api_readonly import YouTubeReadOnlyAPI
from .youtube_connection import UploadConnectionSession


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
    root.geometry("920x840")
    root.minsize(630, 510)

    region = tk.StringVar(value="TH")
    count = tk.StringVar(value="10")
    api_key = tk.StringVar()
    oauth_client = tk.StringVar()
    channel_id = tk.StringVar()
    oauth_session = [None]
    topic = tk.StringVar(value="relaxing nature sounds")
    freshness = tk.StringVar(value="Any")
    video = tk.StringVar()
    audio = tk.StringVar()
    output = tk.StringVar()
    duration = tk.StringVar(value="60")
    loop_seconds = tk.StringVar(value="5")
    rights = tk.BooleanVar(value=False)
    status = tk.StringVar(value="Ready. No uploads are enabled.")
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
    ttk.Label(key_row, text="Session only; not saved").pack(side="left")
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

    account = ttk.LabelFrame(frame, text="YouTube account (private upload preparation; no upload)", padding=10)
    account.pack(fill="x", pady=(10, 0))
    account_row = ttk.Frame(account)
    account_row.pack(fill="x")
    ttk.Label(account_row, text="OAuth client ID").pack(side="left")
    ttk.Entry(account_row, textvariable=oauth_client, width=32).pack(side="left", padx=5)
    ttk.Label(account_row, text="Expected channel ID").pack(side="left")
    ttk.Entry(account_row, textvariable=channel_id, width=22).pack(side="left", padx=5)
    connect_btn = ttk.Button(account, text="1. Open Google authorization")
    connect_btn.pack(anchor="w", pady=(6, 0))
    finish_btn = ttk.Button(account, text="2. Verify browser callback URL")
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

    ttk.Label(frame, textvariable=status, wraplength=740).pack(anchor="w", pady=(12, 0))
    ttk.Label(frame, text="Local draft only. No upload or publication.", foreground="#666").pack(anchor="w")

    def run_task(task, success):
        if active[0]:
            return
        active[0] = True
        search_btn.configure(state="disabled")
        topic_btn.configure(state="disabled")
        render_btn.configure(state="disabled")
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

    def start_google_connection():
        try:
            session = UploadConnectionSession(
                oauth_client.get().strip(), "http://127.0.0.1:8765/",
                channel_id.get().strip(),
            )
            oauth_session[0] = session
            webbrowser.open(session.authorization_url)
            status.set("Google opened. After consent copy browser callback URL and click Verify.")
        except (ValueError, RuntimeError):
            status.set("Google connection setup failed. Check client ID and channel ID.")

    def finish_google_connection():
        session = oauth_session[0]
        if session is None:
            status.set("First open Google authorization")
            return
        callback = simpledialog.askstring(
            "YouTube OAuth", "Paste the full localhost callback URL from your browser:",
            parent=root,
        )
        if not callback:
            return
        oauth_session[0] = None
        def connected(result):
            status.set("Verified channel " + result.channel_id + " (upload scope). No upload performed.")
            messagebox.showinfo("MEDIA Ω — YouTube", "YouTube channel verified. No upload performed.")
        run_task(lambda: session.complete(callback), connected)

    search_btn.configure(command=start_find)
    topic_btn.configure(command=start_topic)
    render_btn.configure(command=start_render)
    connect_btn.configure(command=start_google_connection)
    finish_btn.configure(command=finish_google_connection)

    def poll():
        try:
            callback, data, error = work.get_nowait()
        except Empty:
            pass
        else:
            active[0] = False
            search_btn.configure(state="normal")
            topic_btn.configure(state="normal")
            render_btn.configure(state="normal")
            if error:
                status.set("Operation failed: " + error)
            else:
                callback(data)
        root.after(150, poll)

    root.after(150, poll)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

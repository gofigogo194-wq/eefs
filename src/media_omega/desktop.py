"""Minimal desktop UI for popular-video discovery and licensed local MP4 rendering.

Run: python -m media_omega.desktop
No publishing, downloading, credential entry or background persistence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from .ambient_renderer import render_ambient_loop
from .youtube_api_readonly import YouTubeReadOnlyAPI


def find_popular(region: str, count: int) -> list[dict]:
    token = os.environ.get("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN", "")
    if not token:
        raise ValueError("Read-only YouTube token is not set; popular search unavailable")
    return YouTubeReadOnlyAPI(token).get_popular_videos(region_code=region, max_results=count)


def create_local_video(video: str, audio: str, output: str, duration: float,
                       rights_confirmed: bool) -> str:
    if not rights_confirmed:
        raise ValueError("Confirm that you have rights to the video and audio")
    return render_ambient_loop(video, audio, output, duration_seconds=duration,
                               video_crossfade_seconds=0.15,
                               audio_crossfade_seconds=0.15)


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("MEDIA Ω — Video Workshop")
    root.geometry("800x640")
    root.minsize(630, 510)

    region = tk.StringVar(value="TH")
    count = tk.StringVar(value="10")
    video = tk.StringVar()
    audio = tk.StringVar()
    output = tk.StringVar()
    duration = tk.StringVar(value="60")
    rights = tk.BooleanVar(value=False)
    status = tk.StringVar(value="Ready. No uploads are enabled.")
    work: Queue = Queue()
    active = [False]

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
    results = tk.Text(top, height=10, wrap="word", state="disabled")
    results.pack(fill="both", expand=True, pady=(8, 0))
    ttk.Label(top, text="Reuse rights are NOT verified. This list does not download videos.").pack(anchor="w")

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
        render_btn.configure(state="disabled")
        status.set("Working...")

        def worker():
            try:
                work.put((success, task(), None))
            except Exception as exc:
                # Never print exception details: HTTP errors may include URL data.
                work.put((success, None, type(exc).__name__))

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
        run_task(lambda: find_popular(code, n), show_results)

    def start_render():
        try:
            seconds = float(duration.get())
        except ValueError:
            status.set("Invalid duration")
            return
        if not rights.get():
            status.set("Confirm rights to both inputs before rendering")
            return
        args = (video.get(), audio.get(), output.get(), seconds, bool(rights.get()))
        run_task(lambda: create_local_video(*args), show_render)

    search_btn.configure(command=start_find)
    render_btn.configure(command=start_render)

    def poll():
        try:
            callback, data, error = work.get_nowait()
        except Empty:
            pass
        else:
            active[0] = False
            search_btn.configure(state="normal")
            render_btn.configure(state="normal")
            if error:
                status.set("Operation failed (" + error + "). Check inputs and FFmpeg configuration.")
            else:
                callback(data)
        root.after(150, poll)

    root.after(150, poll)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

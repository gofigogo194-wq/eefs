from __future__ import annotations

import argparse
import json
import sys

from .youtube_http import YouTubeHTTPTransport


def _youtube_probe(video_id: str) -> int:
    transport = YouTubeHTTPTransport()
    stats = transport.video_statistics([video_id])
    if video_id not in stats:
        print(json.dumps({"ok": False, "reason": "VIDEO_NOT_RETURNED", "video_id": video_id}))
        return 2
    print(json.dumps({
        "ok": True,
        "mode": "read-only",
        "video_id": video_id,
        "views": stats[video_id],
    }))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="media-omega")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("youtube-probe", help="perform one read-only YouTube API probe")
    probe.add_argument("--video-id", required=True)

    args = parser.parse_args(argv)
    if args.command == "youtube-probe":
        return _youtube_probe(args.video_id)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

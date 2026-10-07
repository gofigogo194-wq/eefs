from __future__ import annotations

import argparse
import json
import sys

from .youtube_http import YouTubeHTTPTransport
from .memory import DecisionJournal
from .snapshots import SnapshotStore
from .scout import ScoutPolicy, ScoutTopic
from .discovery import DiscoveryPolicy
from .runtime import run_readonly_cycle


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


def _scout(queries: list[str], state_dir: str) -> int:
    from pathlib import Path
    root = Path(state_dir)
    root.mkdir(parents=True, exist_ok=True)
    transport = YouTubeHTTPTransport()
    journal = DecisionJournal(root / "journal.db")
    snapshots = SnapshotStore(root / "snapshots.db")
    known = [ScoutTopic(query=q) for q in queries]
    result = run_readonly_cycle(
        transport, journal, snapshots, known, [],
        ScoutPolicy(query_budget=min(len(known), 20), exploration_fraction=0),
        DiscoveryPolicy(max_candidates=25),
    )
    print(json.dumps({
        "ok": True,
        "mode": result.mode,
        "queries": list(result.queries),
        "discovered": result.discovered,
        "selected": result.selected,
        "observations": result.observations,
        "new_snapshots": result.new_snapshots,
        "snapshot_total": snapshots.count(),
    }))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="media-omega")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("youtube-probe", help="perform one read-only YouTube API probe")
    probe.add_argument("--video-id", required=True)
    scout = sub.add_parser("scout", help="run one persistent read-only YouTube scouting cycle")
    scout.add_argument("--query", action="append", required=True)
    scout.add_argument("--state-dir", default=".media-omega")

    args = parser.parse_args(argv)
    if args.command == "youtube-probe":
        return _youtube_probe(args.video_id)
    if args.command == "scout":
        return _scout(args.query, args.state_dir)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

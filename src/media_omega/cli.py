from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .youtube_http import YouTubeHTTPTransport
from .memory import DecisionJournal
from .snapshots import SnapshotStore
from .scout import ScoutPolicy, ScoutTopic
from .discovery import DiscoveryPolicy
from .runtime import run_readonly_cycle
from .refresh import refresh_tracked
from .intelligence_report import analyze_intelligence


def _existing_state_root(state_dir: str) -> Path:
    root = Path(state_dir)
    snapshots = root / "snapshots.db"
    journal = root / "journal.db"
    if (
        not root.is_dir()
        or not snapshots.is_file()
        or not journal.is_file()
    ):
        raise FileNotFoundError(
            f"MEDIA Ω complete state not found at {root.resolve()}"
        )
    return root


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


def _refresh(state_dir: str) -> int:
    root = _existing_state_root(state_dir)
    journal = DecisionJournal(root / "journal.db")
    snapshots = SnapshotStore(root / "snapshots.db")
    result = refresh_tracked(snapshots, YouTubeHTTPTransport(), journal)
    print(json.dumps({
        "ok": True,
        "mode": result.mode,
        "tracked": result.tracked,
        "returned": result.returned,
        "new_snapshots": result.new_snapshots,
        "missing": result.missing,
        "snapshot_total": snapshots.count(),
    }))
    return 0


def _intelligence_report(state_dir: str) -> int:
    root = _existing_state_root(state_dir)
    journal = DecisionJournal(root / "journal.db")
    snapshots = SnapshotStore(root / "snapshots.db")
    report = analyze_intelligence(snapshots, journal, YouTubeHTTPTransport())
    print(json.dumps({
        "ok": True,
        "mode": "read-only",
        "required_snapshots": report.required_snapshots,
        "ready_count": len(report.ready),
        "insufficient_snapshot_history_count": len(report.insufficient_snapshot_history),
        "insufficient_creator_history_count": len(report.insufficient_creator_history),
        "unreliable_creator_baseline_count": len(report.unreliable_creator_baseline),
        "unreliable_history_count": len(report.unreliable_history),
        "signals": [
            {
                "content_id": x.content_id,
                "creator_id": x.creator_id,
                "relative_creator_performance": x.relative_creator_performance,
                "acceleration_ratio": x.acceleration_ratio,
                "latest_velocity": x.latest_velocity,
                "baseline_confidence": x.baseline_confidence,
                "evidence_sufficiency": x.evidence_sufficiency,
                "score": x.score,
                "status": x.status,
                "peer_cohort_status": x.peer_cohort_status,
                "peer_count": x.peer_count,
                "peer_cohort_version": x.peer_cohort_version,
                "baseline_max_skew_seconds": x.baseline_max_skew_seconds,
                "version": x.version,
            } for x in report.ready
        ],
    }))
    return 0


def _popular(region: str, count: int) -> int:
    from .youtube_api_readonly import YouTubeReadOnlyAPI
    token = os.environ.get("MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN")
    if not token:
        raise ValueError("set MEDIA_OMEGA_YOUTUBE_READONLY_TOKEN for popular lookup")
    videos = YouTubeReadOnlyAPI(token).get_popular_videos(region_code=region, max_results=count)
    print(json.dumps({"ok": True, "mode": "READ_ONLY", "videos": videos}, ensure_ascii=False))
    return 0


def _render(video: str, audio: str, output: str, duration: float,
            video_fade: float, audio_fade: float, rights_confirmed: bool) -> int:
    from .ambient_renderer import render_ambient_loop
    if not rights_confirmed:
        raise ValueError("you must confirm rights to use both input files")
    rendered = render_ambient_loop(
        video, audio, output, duration_seconds=duration,
        video_crossfade_seconds=video_fade,
        audio_crossfade_seconds=audio_fade,
    )
    print(json.dumps({"ok": True, "mode": "LOCAL_RENDER", "published": False,
                      "output": rendered}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="media-omega")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("youtube-probe", help="perform one read-only YouTube API probe")
    probe.add_argument("--video-id", required=True)
    scout = sub.add_parser("scout", help="run one persistent read-only YouTube scouting cycle")
    scout.add_argument("--query", action="append", required=True)
    scout.add_argument("--state-dir", default=".media-omega")
    refresh = sub.add_parser("refresh", help="refresh statistics for previously tracked YouTube videos")
    refresh.add_argument("--state-dir", default=".media-omega")
    intelligence = sub.add_parser("intelligence", help="rank tracked videos using creator baseline and momentum evidence")
    intelligence.add_argument("--state-dir", default=".media-omega")

    popular = sub.add_parser("popular", help="list popular YouTube videos without downloading")
    popular.add_argument("--region", default="US")
    popular.add_argument("--count", type=int, default=10)
    render = sub.add_parser("render", help="render licensed local video and music as MP4")
    render.add_argument("--video", required=True)
    render.add_argument("--audio", required=True)
    render.add_argument("--output", required=True)
    render.add_argument("--duration", type=float, required=True)
    render.add_argument("--video-fade", type=float, default=0)
    render.add_argument("--audio-fade", type=float, default=0)
    render.add_argument("--rights-confirmed", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "popular":
        return _popular(args.region, args.count)
    if args.command == "render":
        return _render(args.video, args.audio, args.output, args.duration,
                       args.video_fade, args.audio_fade, args.rights_confirmed)
    if args.command == "youtube-probe":
        return _youtube_probe(args.video_id)
    if args.command == "scout":
        return _scout(args.query, args.state_dir)
    if args.command == "refresh":
        return _refresh(args.state_dir)
    if args.command == "intelligence":
        return _intelligence_report(args.state_dir)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Changelock: persistent state for a mobile app review session.

The changelock is the memory that survives a context window. It holds the phase
the review is in, the flows being investigated (with the cases run against each),
every screen discovered (with the route to reach it), the queue of screens still to
explore, and the running list of findings.

All state mutation goes through this script so the JSON stays valid and
timestamps stay honest. Run any subcommand with --help for its flags.

Usage:
    python3 changelock.py init --root reviews/plantid/android \\
        --app-name PlantID --slug plantid --platform android \\
        --package com.example.plantid --device emulator-5554
    python3 changelock.py status --root reviews/plantid/android
    python3 changelock.py next --root reviews/plantid/android
    python3 changelock.py add-flow --root ... --id scan-plant --kind core \\
        --title "Scan a plant, get species + health" \\
        --job "Point the camera at a plant and learn what it is and if it's sick"
    python3 changelock.py update-flow --root ... --id scan-plant --status done \\
        --report flows/scan-plant/README.md \\
        --case '{"id":"happy","kind":"happy","status":"done","verdict":"ok, ~4s"}'
    python3 changelock.py add-screen --root ... --id home/profile --title Profile \\
        --parent home --route '[{"action":"launch"},{"action":"tap","label":"Avatar"}]'
    python3 changelock.py update-screen --root ... --id home --status done \\
        --report report/home/README.md --screenshot screenshots/home/01-initial.png
    python3 changelock.py add-finding --root ... --type ad --screen home \\
        --summary "Bottom banner, always visible"
    python3 changelock.py render-index --root reviews/plantid/android
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 2
FILENAME = "changelock.json"

PHASES = ["research", "install", "overview", "core-flow", "explore", "synthesize",
          "done"]
SCREEN_STATUSES = ["queued", "in_progress", "done", "blocked", "skipped"]
FLOW_STATUSES = ["planned", "in_progress", "done", "blocked"]
FLOW_KINDS = ["core", "secondary"]
CASE_KINDS = ["happy", "variant", "error", "boundary", "abuse", "state"]
FINDING_TYPES = ["ad", "paywall", "iap", "crash", "blocker", "bug", "data", "note"]

SUBDIRS = ["00-overview", "flows", "report", "screenshots", "analysis"]

STATUS_ICON = {
    "done": "[x]",
    "in_progress": "[~]",
    "queued": "[ ]",
    "planned": "[ ]",
    "blocked": "[!]",
    "skipped": "[-]",
}


# --------------------------------------------------------------------------- io


def now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lock_path(root: str) -> str:
    """Return the path of the changelock file inside a review root."""
    return os.path.join(root, FILENAME)


def load(root: str) -> dict[str, Any]:
    """Load the changelock, exiting with a clear message if it is missing.

    Older schema-v1 files have no `flows` key; fill it in so a review started
    before flow tracking existed still resumes cleanly.
    """
    path = lock_path(root)
    if not os.path.exists(path):
        sys.exit(f"No changelock at {path}. Run `init` first.")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("flows", {})
    return data


def save(root: str, data: dict[str, Any]) -> None:
    """Persist the changelock, refreshing its last-updated timestamp."""
    data["session"]["last_updated"] = now()
    path = lock_path(root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> None:
    """Create the review folder tree and a fresh changelock."""
    path = lock_path(args.root)
    if os.path.exists(path) and not args.force:
        sys.exit(f"Changelock already exists at {path}. Use --force to overwrite.")

    os.makedirs(args.root, exist_ok=True)
    for sub in SUBDIRS:
        os.makedirs(os.path.join(args.root, sub), exist_ok=True)

    data = {
        "schema_version": SCHEMA_VERSION,
        "app": {
            "name": args.app_name,
            "slug": args.slug,
            "platform": args.platform,
            "package": args.package,
            "version": args.version,
            "store_url": args.store_url,
        },
        "device": {
            "id": args.device,
            "screen": {"width": args.screen_width, "height": args.screen_height},
        },
        "report_language": args.lang,
        "session": {
            "created_at": now(),
            "last_updated": now(),
            "session_count": 1,
        },
        "phase": args.phase,
        "flows": {},
        "screens": {},
        "queue": [],
        "findings": [],
    }
    save(args.root, data)
    print(f"Initialized review workspace at {args.root}")
    print(f"  app      : {args.app_name} ({args.package or 'package TBD'})")
    print(f"  platform : {args.platform}   device: {args.device or 'TBD'}")
    print(f"  phase    : {args.phase}")


def cmd_status(args: argparse.Namespace) -> None:
    """Print a human-readable progress summary of the review."""
    if not os.path.exists(lock_path(args.root)):
        print(f"No existing review at {args.root} — this is a fresh start.")
        return
    data = load(args.root)
    app, screens = data["app"], data["screens"]
    counts = {s: 0 for s in SCREEN_STATUSES}
    for scr in screens.values():
        counts[scr.get("status", "queued")] = counts.get(scr.get("status", "queued"), 0) + 1

    total = len(screens)
    done = counts["done"]
    print(f"{app['name']} ({app.get('package') or '?'}) — {app['platform']}"
          f" v{app.get('version') or '?'}")
    print(f"phase: {data['phase']}   language: {data.get('report_language', '?')}"
          f"   sessions: {data['session']['session_count']}")
    print(f"last updated: {data['session']['last_updated']}")
    print()
    flows = data["flows"]
    if flows:
        print("flows:")
        for fid, flow in sorted(flows.items(),
                                key=lambda kv: (kv[1].get("kind") != "core", kv[0])):
            icon = STATUS_ICON.get(flow.get("status", "planned"), "[?]")
            done_c, total_c, happy = flow_case_counts(flow)
            gap = "" if happy else "  <- no happy path yet"
            print(f"  {icon} {fid} ({flow.get('kind', 'secondary')})"
                  f" — {flow.get('title', '')} · {done_c}/{total_c} cases{gap}")
        open_core = [fid for fid, f in flows.items()
                     if f.get("kind") == "core" and f.get("status") != "done"]
        if open_core:
            print(f"  ! core flow unfinished: {', '.join(open_core)}."
                  " Finish it before spending more budget on screens.")
    else:
        print("flows: none registered — name the app's core flow before exploring.")
    print()

    print(f"screens: {total} total — " + ", ".join(
        f"{k} {v}" for k, v in counts.items() if v))
    if total:
        pct = int(100 * done / total)
        bar = "#" * (pct // 5) + "." * (20 - pct // 5)
        print(f"progress: [{bar}] {pct}%")
    print()

    for sid, scr in sorted(screens.items()):
        icon = STATUS_ICON.get(scr.get("status", "queued"), "[?]")
        note = f"  ({scr['note']})" if scr.get("note") else ""
        print(f"  {icon} {sid} — {scr.get('title', '')}{note}")
        if args.verbose and scr.get("signature"):
            print(f"        sig: {scr['signature']}")

    if data["queue"]:
        print()
        print("next up: " + ", ".join(data["queue"][:5])
              + (f"  (+{len(data['queue']) - 5} more)" if len(data["queue"]) > 5 else ""))
    else:
        print("\nqueue is empty.")

    if data["findings"]:
        print()
        by_type: dict[str, int] = {}
        for f in data["findings"]:
            by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        print("findings: " + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())))


def cmd_next(args: argparse.Namespace) -> None:
    """Pop the next queued screen and mark it in progress."""
    data = load(args.root)
    while data["queue"]:
        sid = data["queue"].pop(0)
        scr = data["screens"].get(sid)
        if scr is None:
            continue
        if scr.get("status") not in ("queued", "in_progress"):
            continue
        scr["status"] = "in_progress"
        save(args.root, data)
        print(json.dumps({"id": sid, **scr}, indent=2, ensure_ascii=False))
        return
    save(args.root, data)
    print(json.dumps({"id": None, "message": "queue empty"}, indent=2))


def flow_case_counts(flow: dict[str, Any]) -> tuple[int, int, bool]:
    """Return (cases done, cases total, whether a happy case has been completed).

    The happy-path flag matters more than the raw count: a flow with six error
    cases and no completed success path has no baseline to judge them against.
    """
    cases = flow.get("cases", [])
    done = sum(1 for c in cases if c.get("status") == "done")
    happy = any(c.get("kind") == "happy" and c.get("status") == "done" for c in cases)
    return done, len(cases), happy


def cmd_add_flow(args: argparse.Namespace) -> None:
    """Register a flow to investigate — the app's core loop or a secondary one."""
    data = load(args.root)
    if args.id in data["flows"] and not args.force:
        print(f"Flow '{args.id}' already known (status: "
              f"{data['flows'][args.id].get('status')}). Use --force to overwrite.")
        return

    route: list[dict[str, Any]] = []
    if args.route:
        try:
            route = json.loads(args.route)
        except json.JSONDecodeError as exc:
            sys.exit(f"--route is not valid JSON: {exc}")

    data["flows"][args.id] = {
        "title": args.title or args.id,
        "kind": args.kind,
        "job": args.job,
        "status": "planned",
        "route": route,
        "screens": args.screen or [],
        "report": None,
        "cases": [],
        "note": args.note,
        "created_at": now(),
    }
    save(args.root, data)
    print(f"Registered {args.kind} flow '{args.id}' — {data['flows'][args.id]['title']}")
    if args.kind == "core":
        print("  Run its happy path end to end with real input before the screen loop.")


def cmd_update_flow(args: argparse.Namespace) -> None:
    """Update a flow's status/report, attach screens, or record a case result.

    `--case` takes a JSON object and merges by its `id`, so the same command both
    adds a new case and updates one you already ran.
    """
    data = load(args.root)
    flow = data["flows"].get(args.id)
    if flow is None:
        sys.exit(f"Unknown flow '{args.id}'. Register it with `add-flow` first.")

    if args.status:
        flow["status"] = args.status
    if args.title:
        flow["title"] = args.title
    if args.job:
        flow["job"] = args.job
    if args.report:
        flow["report"] = args.report
    if args.note:
        flow["note"] = args.note
    for sid in args.screen or []:
        if sid not in flow["screens"]:
            flow["screens"].append(sid)

    for raw in args.case or []:
        try:
            case = json.loads(raw)
        except json.JSONDecodeError as exc:
            sys.exit(f"--case is not valid JSON: {exc}")
        if not isinstance(case, dict) or not case.get("id"):
            sys.exit("--case must be a JSON object with an 'id' field")
        if case.get("kind") and case["kind"] not in CASE_KINDS:
            sys.exit(f"case kind must be one of {', '.join(CASE_KINDS)}")
        case.setdefault("status", "done")
        case["recorded_at"] = now()
        for existing in flow["cases"]:
            if existing.get("id") == case["id"]:
                existing.update(case)
                break
        else:
            flow["cases"].append(case)

    flow["updated_at"] = now()
    save(args.root, data)
    done, total, happy = flow_case_counts(flow)
    print(f"{args.id} -> {flow['status']}  ({done}/{total} cases)")
    if flow["status"] == "done" and not happy:
        print("  Warning: no completed 'happy' case. Error cases have no baseline"
              " to be judged against — run the success path before closing this flow.")


def cmd_add_screen(args: argparse.Namespace) -> None:
    """Register a newly discovered screen and append it to the queue."""
    data = load(args.root)
    if args.id in data["screens"] and not args.force:
        print(f"Screen '{args.id}' already known (status: "
              f"{data['screens'][args.id].get('status')}). Use --force to overwrite.")
        return

    route: list[dict[str, Any]] = []
    if args.route:
        try:
            route = json.loads(args.route)
        except json.JSONDecodeError as exc:
            sys.exit(f"--route is not valid JSON: {exc}")

    data["screens"][args.id] = {
        "title": args.title or args.id.split("/")[-1],
        "parent": args.parent,
        "status": "queued",
        "route": route,
        "precondition": args.precondition,
        "signature": args.signature,
        "report": None,
        "screenshots": [],
        "note": args.note,
        "discovered_at": now(),
    }
    if args.id not in data["queue"]:
        if args.front:
            data["queue"].insert(0, args.id)
        else:
            data["queue"].append(args.id)
    save(args.root, data)
    print(f"Queued '{args.id}' (position {data['queue'].index(args.id) + 1}"
          f" of {len(data['queue'])})")


def cmd_update_screen(args: argparse.Namespace) -> None:
    """Update status, report path, screenshots, or notes on a known screen."""
    data = load(args.root)
    scr = data["screens"].get(args.id)
    if scr is None:
        sys.exit(f"Unknown screen '{args.id}'. Add it with `add-screen` first.")

    if args.status:
        scr["status"] = args.status
    if args.title:
        scr["title"] = args.title
    if args.report:
        scr["report"] = args.report
    if args.signature:
        scr["signature"] = args.signature
    if args.precondition:
        scr["precondition"] = args.precondition
    if args.note:
        scr["note"] = args.note
    if args.route:
        try:
            scr["route"] = json.loads(args.route)
        except json.JSONDecodeError as exc:
            sys.exit(f"--route is not valid JSON: {exc}")
    for shot in args.screenshot or []:
        if shot not in scr["screenshots"]:
            scr["screenshots"].append(shot)

    if scr["status"] in ("done", "blocked", "skipped") and args.id in data["queue"]:
        data["queue"].remove(args.id)
    scr["updated_at"] = now()
    save(args.root, data)
    print(f"{args.id} -> {scr['status']}"
          f"  ({len(scr['screenshots'])} screenshots, {len(data['queue'])} still queued)")


def cmd_add_finding(args: argparse.Namespace) -> None:
    """Record an ad slot, paywall, crash, or other notable finding."""
    data = load(args.root)
    data["findings"].append({
        "type": args.type,
        "screen": args.screen,
        "summary": args.summary,
        "detail": args.detail,
        "screenshot": args.screenshot,
        "recorded_at": now(),
    })
    save(args.root, data)
    count = sum(1 for f in data["findings"] if f["type"] == args.type)
    print(f"Recorded {args.type} finding on '{args.screen}' ({count} of this type so far)")


def cmd_set_phase(args: argparse.Namespace) -> None:
    """Move the review to a different phase."""
    data = load(args.root)
    old = data["phase"]
    data["phase"] = args.phase
    save(args.root, data)
    print(f"phase: {old} -> {args.phase}")


def cmd_bump_session(args: argparse.Namespace) -> None:
    """Increment the session counter when resuming a review on a new day."""
    data = load(args.root)
    data["session"]["session_count"] += 1
    save(args.root, data)
    print(f"session #{data['session']['session_count']}")


def cmd_render_index(args: argparse.Namespace) -> None:
    """Regenerate README.md from the changelock."""
    data = load(args.root)
    app = data["app"]
    screens = data["screens"]
    done = sum(1 for s in screens.values() if s.get("status") == "done")
    total = len(screens)
    pct = int(100 * done / total) if total else 0
    bar = "#" * (pct // 5) + "." * (20 - pct // 5)

    lines = [
        f"# {app['name']} — app review ({app['platform']})",
        "",
        f"> package `{app.get('package') or '?'}` · version {app.get('version') or '?'}"
        f" · device `{data['device'].get('id') or '?'}`",
        f"> phase **{data['phase']}** · session {data['session']['session_count']}"
        f" · last updated {data['session']['last_updated']}",
        "",
        f"**Progress:** `[{bar}]` {pct}% — {done}/{total} screens documented",
        "",
        "## Overview",
        "",
    ]
    for name, label in [
        ("store-listing.md", "Store listing"),
        ("landing-page.md", "Landing page"),
        ("app-map.md", "App map"),
    ]:
        if os.path.exists(os.path.join(args.root, "00-overview", name)):
            lines.append(f"- [{label}](00-overview/{name})")

    if data["flows"]:
        lines += ["", "## Flows", "",
                  "| Status | Flow | Kind | Cases | Happy path | Report |",
                  "|---|---|---|---|---|---|"]
        for fid, flow in sorted(data["flows"].items(),
                                key=lambda kv: (kv[1].get("kind") != "core", kv[0])):
            icon = STATUS_ICON.get(flow.get("status", "planned"), "[?]")
            done_c, total_c, happy = flow_case_counts(flow)
            link = f"[{flow.get('title', fid)}]({flow['report']})" if flow.get("report") \
                else flow.get("title", fid)
            lines.append(f"| {icon} | `{fid}` | {flow.get('kind', 'secondary')} |"
                         f" {done_c}/{total_c} | {'yes' if happy else '**no**'} |"
                         f" {link} |")

    lines += ["", "## Analysis", ""]
    for name, label in [
        ("feature-map.md", "Feature map"),
        ("monetization.md", "Monetization"),
        ("ux-flows.md", "UX flows"),
        ("data-and-limits.md", "Data and limits"),
    ]:
        if os.path.exists(os.path.join(args.root, "analysis", name)):
            lines.append(f"- [{label}](analysis/{name})")

    lines += ["", "## Screens", "", "| Status | Screen | Report | Shots |",
              "|---|---|---|---|"]
    for sid, scr in sorted(screens.items()):
        icon = STATUS_ICON.get(scr.get("status", "queued"), "[?]")
        indent = "&nbsp;&nbsp;" * sid.count("/")
        link = f"[{scr.get('title', sid)}]({scr['report']})" if scr.get("report") \
            else scr.get("title", sid)
        lines.append(f"| {icon} | {indent}`{sid}` | {link} | {len(scr.get('screenshots', []))} |")

    if data["queue"]:
        lines += ["", "## Remaining queue", ""]
        lines += [f"{i}. `{sid}` — {screens.get(sid, {}).get('title', '')}"
                  for i, sid in enumerate(data["queue"], 1)]
        lines += ["", f"Resume with: *\"continue the review of {app['name']}\"*"]

    if data["findings"]:
        lines += ["", "## Findings log", "", "| Type | Screen | Summary |", "|---|---|---|"]
        for f in data["findings"]:
            lines.append(f"| {f['type']} | `{f.get('screen') or '-'}` | {f['summary']} |")

    lines += ["", "---", "", "*Legend: `[x]` done · `[~]` in progress · `[ ]` queued"
              " · `[!]` blocked · `[-]` skipped (duplicate)*", ""]

    out = os.path.join(args.root, "README.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Wrote {out} ({done}/{total} screens, {len(data['findings'])} findings)")


# ------------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for all changelock subcommands."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def with_root(sp: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sp.add_argument("--root", required=True,
                        help="Review root, e.g. reviews/plantid/android")
        return sp

    sp = with_root(sub.add_parser("init", help="Create workspace and changelock"))
    sp.add_argument("--app-name", required=True)
    sp.add_argument("--slug", required=True)
    sp.add_argument("--platform", required=True, choices=["android", "ios"])
    sp.add_argument("--package", default=None, help="Package name or bundle id")
    sp.add_argument("--version", default=None)
    sp.add_argument("--store-url", default=None)
    sp.add_argument("--device", default=None)
    sp.add_argument("--screen-width", type=int, default=None)
    sp.add_argument("--screen-height", type=int, default=None)
    sp.add_argument("--lang", default="vi", help="Report language, e.g. vi or en")
    sp.add_argument("--phase", default="research", choices=PHASES)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = with_root(sub.add_parser("status", help="Show progress"))
    sp.add_argument("--verbose", action="store_true", help="Also print screen signatures")
    sp.set_defaults(func=cmd_status)

    sp = with_root(sub.add_parser("next", help="Pop the next queued screen"))
    sp.set_defaults(func=cmd_next)

    sp = with_root(sub.add_parser("add-flow", help="Register a flow to investigate"))
    sp.add_argument("--id", required=True, help="Slug, e.g. scan-plant or login")
    sp.add_argument("--kind", default="secondary", choices=FLOW_KINDS)
    sp.add_argument("--title", default=None)
    sp.add_argument("--job", default=None, help="What the flow delivers, one sentence")
    sp.add_argument("--route", default=None, help="JSON array of entry route steps")
    sp.add_argument("--screen", action="append", help="Screen id involved; repeatable")
    sp.add_argument("--note", default=None)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_add_flow)

    sp = with_root(sub.add_parser("update-flow", help="Update a flow or record a case"))
    sp.add_argument("--id", required=True)
    sp.add_argument("--status", choices=FLOW_STATUSES)
    sp.add_argument("--title", default=None)
    sp.add_argument("--job", default=None)
    sp.add_argument("--report", default=None)
    sp.add_argument("--screen", action="append", help="Screen id involved; repeatable")
    sp.add_argument("--case", action="append",
                    help='JSON object, merged by id, e.g. \'{"id":"wrong-password",'
                         '"kind":"error","observed":"...","verdict":"ok"}\'. Repeatable')
    sp.add_argument("--note", default=None)
    sp.set_defaults(func=cmd_update_flow)

    sp = with_root(sub.add_parser("add-screen", help="Queue a discovered screen"))
    sp.add_argument("--id", required=True, help="Path-like id, e.g. home/profile")
    sp.add_argument("--title", default=None)
    sp.add_argument("--parent", default=None)
    sp.add_argument("--route", default=None, help="JSON array of route steps")
    sp.add_argument("--precondition", default=None)
    sp.add_argument("--signature", default=None)
    sp.add_argument("--note", default=None)
    sp.add_argument("--front", action="store_true", help="Queue at the front")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_add_screen)

    sp = with_root(sub.add_parser("update-screen", help="Update a screen's state"))
    sp.add_argument("--id", required=True)
    sp.add_argument("--status", choices=SCREEN_STATUSES)
    sp.add_argument("--title", default=None)
    sp.add_argument("--report", default=None)
    sp.add_argument("--screenshot", action="append", help="Repeatable")
    sp.add_argument("--signature", default=None)
    sp.add_argument("--precondition", default=None)
    sp.add_argument("--route", default=None)
    sp.add_argument("--note", default=None)
    sp.set_defaults(func=cmd_update_screen)

    sp = with_root(sub.add_parser("add-finding", help="Record a finding"))
    sp.add_argument("--type", required=True, choices=FINDING_TYPES)
    sp.add_argument("--screen", default=None)
    sp.add_argument("--summary", required=True)
    sp.add_argument("--detail", default=None)
    sp.add_argument("--screenshot", default=None)
    sp.set_defaults(func=cmd_add_finding)

    sp = with_root(sub.add_parser("set-phase", help="Change the review phase"))
    sp.add_argument("--phase", required=True, choices=PHASES)
    sp.set_defaults(func=cmd_set_phase)

    sp = with_root(sub.add_parser("bump-session", help="Increment session counter"))
    sp.set_defaults(func=cmd_bump_session)

    sp = with_root(sub.add_parser("render-index", help="Regenerate README.md"))
    sp.set_defaults(func=cmd_render_index)

    return p


def main() -> None:
    """Parse arguments and dispatch to the selected subcommand."""
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

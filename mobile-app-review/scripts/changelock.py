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
    python3 changelock.py add-edge --root ... --from home --to home/scan_plant \\
        --trigger "tap `Scan`" --kind tap --spine --flow scan-plant \\
        --evidence screenshots/flows/scan-plant/01-camera.png
    python3 changelock.py render-diagram --root ... --scope app \\
        --inject analysis/ux-flows.md
    python3 changelock.py render-index --root reviews/plantid/android
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 3
FILENAME = "changelock.json"

PHASES = ["research", "install", "overview", "core-flow", "explore", "synthesize",
          "done"]
SCREEN_STATUSES = ["queued", "in_progress", "done", "blocked", "skipped"]
FLOW_STATUSES = ["planned", "in_progress", "done", "blocked"]
FLOW_KINDS = ["core", "secondary"]
CASE_KINDS = ["happy", "variant", "error", "boundary", "abuse", "state"]
FINDING_TYPES = ["ad", "paywall", "iap", "crash", "blocker", "bug", "data", "note"]

# Graph vocabulary for the user-flow diagrams. Node kinds map to Mermaid shapes so
# a reader can tell a screen from a server round-trip at a glance; edge kinds and
# statuses map to arrow styles so an untested transition can never look observed.
NODE_KINDS = ["screen", "modal", "input", "system", "decision", "gate", "store",
              "terminal", "external"]
EDGE_KINDS = ["tap", "swipe", "input", "auto", "back", "deeplink", "system"]
EDGE_STATUSES = ["observed", "inferred", "blocked"]
DIAGRAM_SCOPES = ["app", "flow", "journey"]

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
    data.setdefault("nodes", {})
    data.setdefault("edges", [])
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
        "nodes": {},
        "edges": [],
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

    edges = data.get("edges", [])
    if edges:
        obs = sum(1 for e in edges if e.get("status") == "observed")
        spine = sum(1 for e in edges if e.get("spine"))
        no_ev = sum(1 for e in edges
                    if e.get("status") == "observed" and not e.get("evidence"))
        nodes = {e.get("from") for e in edges} | {e.get("to") for e in edges}
        print()
        print(f"flow graph: {len(edges)} edges ({obs} observed, {spine} on a happy-path"
              f" spine) over {len(nodes)} nodes")
        if no_ev:
            print(f"  ! {no_ev} observed edge(s) have no evidence screenshot")
    else:
        print()
        print("flow graph: empty — record transitions with `add-edge` as you explore,"
              " or the user-flow diagram will have to be drawn from memory.")

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


# ------------------------------------------------------------------- flow graph


def cmd_add_node(args: argparse.Namespace) -> None:
    """Declare a non-screen node for the user-flow diagram.

    Screens already in the changelock are diagram nodes for free. This command is
    for the parts of a flow that are not screens and would otherwise get flattened
    into one: a server round-trip, a paywall gate, a permission dialog, a decision
    the app makes on your behalf. Keeping them as distinct nodes is what turns a
    sitemap into a flow.
    """
    data = load(args.root)
    if args.id in data["screens"]:
        sys.exit(f"'{args.id}' is already a screen; screens are nodes automatically.")
    if args.id in data["nodes"] and not args.force:
        print(f"Node '{args.id}' already declared as {data['nodes'][args.id]['kind']}."
              " Use --force to change it.")
        return
    data["nodes"][args.id] = {
        "title": args.title or args.id.split("/")[-1],
        "kind": args.kind,
        "note": args.note,
        "evidence": args.evidence or [],
        "created_at": now(),
    }
    save(args.root, data)
    print(f"Declared {args.kind} node '{args.id}' — {data['nodes'][args.id]['title']}")


def edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    """Identity of an edge: the pair it connects plus the trigger that fires it."""
    return (edge.get("from", ""), edge.get("to", ""), edge.get("trigger", ""))


def cmd_add_edge(args: argparse.Namespace) -> None:
    """Record one transition you actually watched happen.

    Do this as you go, while the screenshot is still in front of you — the diagram
    is generated from these edges, so an edge you never recorded is a line you will
    later be tempted to draw from memory, which is exactly the guesswork the
    evidence rules exist to prevent.
    """
    data = load(args.root)
    known = set(data["screens"]) | set(data["nodes"])
    for side, nid in (("--from", args.source), ("--to", args.target)):
        if nid not in known:
            print(f"note: {side} '{nid}' is not a known screen or node yet."
                  " Add it with `add-screen`/`add-node` so the diagram can label it.")

    edge = {
        "from": args.source,
        "to": args.target,
        "trigger": args.trigger,
        "kind": args.kind,
        "status": args.status,
        "spine": bool(args.spine),
        "flow": args.flow,
        "cost": args.cost,
        "condition": args.condition,
        "evidence": args.evidence or [],
        "tags": args.tag or [],
        "note": args.note,
        "recorded_at": now(),
    }
    if args.status == "observed" and not edge["evidence"]:
        print("warning: an observed edge with no --evidence cannot be audited."
              " Attach the screenshot that shows the destination.")
    for existing in data["edges"]:
        if edge_key(existing) == edge_key(edge):
            existing.update(edge)
            save(args.root, data)
            print(f"Updated edge {args.source} -> {args.target} ({args.status})")
            return
    data["edges"].append(edge)
    save(args.root, data)
    print(f"Recorded edge {args.source} -> {args.target}"
          f" via {args.kind} '{args.trigger}' ({args.status})"
          f"  [{len(data['edges'])} edges total]")


def mm_id(nid: str) -> str:
    """Turn a screen/node id into a Mermaid-safe identifier."""
    safe = "".join(ch if ch.isalnum() else "_" for ch in nid)
    return "n_" + safe.strip("_").lower()


def mm_label(text: str) -> str:
    """Quote a label so Mermaid renders punctuation instead of choking on it."""
    clean = (text or "?").replace('"', "&quot;").replace("\n", "<br/>")
    if clean.startswith("`"):
        # `"`x`"` is Mermaid's markdown-string syntax; a trigger that starts with a
        # quoted UI label would be parsed as markup instead of shown to the reader.
        clean = "&#96;" + clean[1:]
    return f'"{clean}"'


NODE_SHAPE = {
    "screen": '{id}[{label}]',
    "modal": '{id}({label})',
    "input": '{id}[/{label}/]',
    "system": '{id}[[{label}]]',
    "decision": '{id}{{{label}}}',
    "gate": '{id}{{{{{label}}}}}',
    "store": '{id}[({label})]',
    "terminal": '{id}([{label}])',
    "external": '{id}[/{label}\\]',
}

CLASS_DEFS = [
    "classDef screen fill:#eaf1fc,stroke:#3f6fbf,color:#10233d",
    "classDef modal fill:#f3f0fb,stroke:#7a5fc0,color:#22133d",
    "classDef input fill:#eef8ef,stroke:#4a9e5c,color:#123320",
    "classDef system fill:#f0f0f0,stroke:#7d7d7d,color:#1f1f1f",
    "classDef decision fill:#fdf6e3,stroke:#b79a35,color:#3a2f0b",
    "classDef gate fill:#fdeee0,stroke:#d8842d,color:#3f2610",
    "classDef store fill:#e6f6f0,stroke:#2f9c7a,color:#0d3329",
    "classDef terminal fill:#eeeeee,stroke:#555555,color:#1a1a1a",
    "classDef external fill:#f9ecf3,stroke:#b8508a,color:#3d1029",
    "classDef blocked fill:#fdecec,stroke:#c8524f,color:#3d1111,stroke-dasharray: 5 3",
]


def node_meta(data: dict[str, Any], nid: str) -> tuple[str, str, bool]:
    """Return (title, kind, is_known) for a diagram node."""
    if nid in data["nodes"]:
        node = data["nodes"][nid]
        return node.get("title") or nid, node.get("kind", "screen"), True
    if nid in data["screens"]:
        scr = data["screens"][nid]
        return scr.get("title") or nid.split("/")[-1], "screen", True
    return nid.split("/")[-1], "screen", False


def node_class(data: dict[str, Any], nid: str, kind: str) -> str:
    """Blocked screens get the blocked style so an unreached node never looks visited."""
    if nid in data["screens"] and data["screens"][nid].get("status") == "blocked":
        return "blocked"
    return kind


def edge_arrow(edge: dict[str, Any]) -> str:
    """Arrow style carries the epistemic status: thick spine, solid seen, dotted not."""
    if edge.get("status") in ("inferred", "blocked"):
        return "-.->"
    if edge.get("spine"):
        return "==>"
    return "-->"


def edge_text(edge: dict[str, Any]) -> str:
    """Build the edge label: the literal trigger, plus condition, cost and caveat."""
    parts = []
    trigger = edge.get("trigger") or edge.get("kind") or ""
    if edge.get("kind") == "auto" and trigger and not trigger.lower().startswith("auto"):
        trigger = f"auto: {trigger}"
    if edge.get("kind") == "back" and trigger and not trigger.lower().startswith("back"):
        trigger = f"back: {trigger}"
    if trigger:
        parts.append(trigger)
    if edge.get("condition"):
        parts.append(f"[{edge['condition']}]")
    if edge.get("cost"):
        parts.append(edge["cost"])
    if edge.get("status") == "inferred":
        parts.append("(inferred, not tested)")
    elif edge.get("status") == "blocked":
        parts.append("(blocked)")
    return " · ".join(parts) or "?"


def select_edges(data: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    """Pick the edges belonging to the requested diagram scope."""
    edges = data["edges"]
    if args.scope == "flow":
        if not args.flow:
            sys.exit("--scope flow needs --flow <flow-id>")
        edges = [e for e in edges if e.get("flow") == args.flow]
    elif args.scope == "journey":
        tagged = [e for e in edges if "journey" in (e.get("tags") or [])]
        edges = tagged or [e for e in edges if e.get("spine")]
        if not tagged and edges:
            print("note: no edges tagged `journey`; falling back to the spine edges."
                  " Tag the first-run path with `--tag journey` for a truer journey.",
                  file=sys.stderr)
    if args.tag:
        edges = [e for e in edges if set(args.tag) & set(e.get("tags") or [])]
    if args.observed_only:
        edges = [e for e in edges if e.get("status") == "observed"]
    if args.no_back:
        edges = [e for e in edges if e.get("kind") != "back"]
    return edges


def lint_diagram(data: dict[str, Any], edges: list[dict[str, Any]]) -> list[str]:
    """Report what would make the diagram misleading, so it can be fixed first."""
    warnings: list[str] = []
    known = set(data["screens"]) | set(data["nodes"])
    seen_keys: set[tuple[str, str, str]] = set()
    targets = {e.get("to") for e in edges}
    sources = {e.get("from") for e in edges}
    for e in edges:
        label = f"{e.get('from')} -> {e.get('to')}"
        for nid in (e.get("from"), e.get("to")):
            if nid not in known:
                warnings.append(f"{label}: node `{nid}` is not a known screen or node"
                                " — it will render with a guessed label")
        if e.get("status") == "observed" and not e.get("evidence"):
            warnings.append(f"{label}: observed but has no evidence screenshot")
        key = edge_key(e)
        if key in seen_keys:
            warnings.append(f"{label}: duplicate edge for the same trigger")
        seen_keys.add(key)
    for nid in sorted(sources | targets):
        _, kind, _ = node_meta(data, nid)
        explored = data["screens"].get(nid, {}).get("status") == "done"
        if nid not in targets and kind not in ("terminal", "external"):
            warnings.append(f"`{nid}` has no incoming edge — how does a user get there?")
        # A dead end only counts as suspicious once you have been through the node: a
        # still-queued screen has no outgoing edge because nobody has opened it yet.
        dead_end_matters = kind in ("decision", "system", "gate") or explored
        if nid not in sources and dead_end_matters and kind not in ("terminal", "store"):
            warnings.append(f"`{nid}` has no outgoing edge — is that a real dead end,"
                            " or an untested next step?")
    documented = {sid for sid, s in data["screens"].items() if s.get("status") == "done"}
    missing = sorted(documented - (sources | targets))
    if missing:
        warnings.append("documented screens absent from this diagram: "
                        + ", ".join(f"`{m}`" for m in missing))
    return warnings


def render_diagram(data: dict[str, Any], edges: list[dict[str, Any]],
                   args: argparse.Namespace) -> str:
    """Emit the Mermaid block (plus its evidence table) for the selected edges."""
    order: list[str] = []
    for e in edges:
        for nid in (e.get("from"), e.get("to")):
            if nid and nid not in order:
                order.append(nid)

    direction = args.direction or ("LR" if args.scope == "app" else "TD")
    lines = [f"flowchart {direction}"]
    by_class: dict[str, list[str]] = {}
    for nid in order:
        title, kind, _ = node_meta(data, nid)
        shape = NODE_SHAPE.get(kind, NODE_SHAPE["screen"])
        lines.append("    " + shape.format(id=mm_id(nid), label=mm_label(title)))
        by_class.setdefault(node_class(data, nid, kind), []).append(mm_id(nid))
    lines.append("")
    for e in edges:
        lines.append(f"    {mm_id(e['from'])} {edge_arrow(e)}"
                     f"|{mm_label(edge_text(e))}| {mm_id(e['to'])}")
    lines.append("")
    used = {c for c in by_class}
    lines += ["    " + cd for cd in CLASS_DEFS if cd.split()[1] in used]
    for cls, ids in by_class.items():
        lines.append(f"    class {','.join(ids)} {cls};")

    out = ["```mermaid", *lines, "```", ""]
    if not args.no_evidence:
        out += ["| # | Transition | Trigger | Status | Evidence |",
                "|---|---|---|---|---|"]
        for i, e in enumerate(edges, 1):
            title_from, _, _ = node_meta(data, e["from"])
            title_to, _, _ = node_meta(data, e["to"])
            ev = ", ".join(f"`{p}`" for p in e.get("evidence") or []) or "—"
            out.append(f"| {i} | {title_from} → {title_to} | {edge_text(e)} |"
                       f" {e.get('status')} | {ev} |")
        out.append("")
    return "\n".join(out)


def inject_block(path: str, marker: str, block: str) -> str:
    """Replace the marked region of a report with a freshly generated diagram.

    Regenerating in place matters because the prose around a diagram is written by
    hand and must survive the next render — otherwise nobody re-renders and the
    diagram drifts away from the graph it is supposed to summarise.
    """
    start, end = f"<!-- flow-diagram:{marker} -->", f"<!-- /flow-diagram:{marker} -->"
    body = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
    replacement = f"{start}\n{block}{end}\n"
    if start in body and end in body:
        head, rest = body.split(start, 1)
        _, tail = rest.split(end, 1)
        body = head + replacement + tail
        action = "updated"
    else:
        if body and not body.endswith("\n"):
            body += "\n"
        body += ("\n" if body else "") + replacement
        action = "appended"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return action


def cmd_render_diagram(args: argparse.Namespace) -> None:
    """Generate a user-flow diagram from the recorded graph."""
    data = load(args.root)
    edges = select_edges(data, args)
    if not edges:
        sys.exit("No edges match this scope. Record transitions with `add-edge`"
                 " while you explore — the diagram is generated, not drawn.")
    block = render_diagram(data, edges, args)
    marker = f"flow-{args.flow}" if args.scope == "flow" else args.scope

    if args.inject:
        target = args.inject if os.path.isabs(args.inject) \
            else os.path.join(args.root, args.inject)
        action = inject_block(target, marker, block)
        print(f"{action.capitalize()} <!-- flow-diagram:{marker} --> in {target}"
              f" ({len(edges)} edges)")
    elif args.out:
        target = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out)
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(block)
        print(f"Wrote {target} ({len(edges)} edges)")
    else:
        print(block)

    warnings = lint_diagram(data, edges)
    if warnings:
        print(f"\n{len(warnings)} thing(s) to check before publishing this diagram:",
              file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
        if args.strict:
            sys.exit(1)
    else:
        print("\nlint: clean — every edge has evidence and every node is reachable.",
              file=sys.stderr)


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
        ("ux-flows.md", "User flow (diagrams)"),
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

    sp = with_root(sub.add_parser("add-node",
                                  help="Declare a non-screen diagram node"))
    sp.add_argument("--id", required=True,
                    help="Node id, e.g. scan/analyzing or gate/quota")
    sp.add_argument("--kind", required=True, choices=NODE_KINDS)
    sp.add_argument("--title", default=None)
    sp.add_argument("--evidence", action="append", help="Screenshot path; repeatable")
    sp.add_argument("--note", default=None)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_add_node)

    sp = with_root(sub.add_parser("add-edge",
                                 help="Record an observed transition between nodes"))
    sp.add_argument("--from", dest="source", required=True)
    sp.add_argument("--to", dest="target", required=True)
    sp.add_argument("--trigger", required=True,
                    help="The literal control or gesture, e.g. \"tap `Scan`\"")
    sp.add_argument("--kind", default="tap", choices=EDGE_KINDS)
    sp.add_argument("--status", default="observed", choices=EDGE_STATUSES)
    sp.add_argument("--spine", action="store_true",
                    help="Part of the happy path; drawn as a thick arrow")
    sp.add_argument("--flow", default=None, help="Flow id this transition belongs to")
    sp.add_argument("--cost", default=None, help="Measured cost, e.g. ~4s or 3 taps")
    sp.add_argument("--condition", default=None,
                    help="State that selects this branch, e.g. \"quota exhausted\"")
    sp.add_argument("--evidence", action="append", help="Screenshot path; repeatable")
    sp.add_argument("--tag", action="append", help="Free tag, e.g. journey; repeatable")
    sp.add_argument("--note", default=None)
    sp.set_defaults(func=cmd_add_edge)

    sp = with_root(sub.add_parser("render-diagram",
                                 help="Generate a Mermaid user-flow diagram"))
    sp.add_argument("--scope", default="app", choices=DIAGRAM_SCOPES)
    sp.add_argument("--flow", default=None, help="Flow id, required for --scope flow")
    sp.add_argument("--direction", default=None, choices=["TD", "TB", "LR", "RL", "BT"])
    sp.add_argument("--tag", action="append", help="Only edges carrying this tag")
    sp.add_argument("--observed-only", action="store_true",
                    help="Drop inferred and blocked edges")
    sp.add_argument("--no-back", action="store_true", help="Drop back-navigation edges")
    sp.add_argument("--no-evidence", action="store_true",
                    help="Omit the evidence table under the diagram")
    sp.add_argument("--inject", default=None,
                    help="Report to write into, between flow-diagram markers")
    sp.add_argument("--out", default=None, help="Write the block to this file instead")
    sp.add_argument("--strict", action="store_true", help="Exit 1 if lint warns")
    sp.set_defaults(func=cmd_render_diagram)

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

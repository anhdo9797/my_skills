#!/usr/bin/env python3
"""Filter a mobile UI view hierarchy down to interactable elements only.

A raw view-hierarchy dump (Maestro ``inspect_screen`` JSON or Android
``uiautomator`` XML) contains every node on screen — including empty layout
containers and dozens of blank attributes per node. A single screen easily
reaches ~1 MB / ~250k tokens, of which ~95% is noise that has no bearing on
selector choice.

This script keeps only the nodes a tester actually needs to write a selector
(anything with visible text, a resource id, or that is clickable / scrollable /
an input field) and prints a compact table. Typical output is 1-2k tokens with
**no loss of decision-relevant information** — every interactable element is
preserved.

Usage:
    python filter_hierarchy.py <dump-file>          # auto-detect JSON or XML
    maestro hierarchy | python filter_hierarchy.py  # read from stdin
    adb exec-out uiautomator dump /dev/tty | python filter_hierarchy.py

Output: a Markdown table (text | id | class | flags | bounds) plus a one-line
summary of how many nodes were kept vs. dropped.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from typing import Any, Iterable


# Attribute keys vary across platforms / dump formats. Probe several.
_TEXT_KEYS = ("text",)
_HINT_KEYS = ("hintText", "hint")
_ID_KEYS = ("resource-id", "resourceId", "resource_id")
_DESC_KEYS = ("accessibilityText", "content-desc", "contentDescription", "label")
_CLASS_KEYS = ("class", "className", "elementType")

# Class-name fragments that mark a text input even when no text is present yet.
_INPUT_HINTS = ("edittext", "textfield", "searchview", "autocomplete")


def _first(attrs: dict, keys: Iterable[str]) -> str:
    """Return the first non-empty value among ``keys`` in ``attrs``."""
    for key in keys:
        val = attrs.get(key)
        if val:
            return str(val).strip()
    return ""


def _is_truthy(attrs: dict, key: str) -> bool:
    """Interpret a hierarchy boolean attribute (stored as a string) as bool."""
    return str(attrs.get(key, "")).lower() == "true"


def _short_class(class_name: str) -> str:
    """Strip the package prefix so ``android.widget.Button`` -> ``Button``."""
    return class_name.rsplit(".", 1)[-1] if class_name else ""


def _short_id(resource_id: str) -> str:
    """Drop the ``com.app:id/`` package prefix from a resource id."""
    return resource_id.split("/", 1)[-1] if "/" in resource_id else resource_id


class Node:
    """A normalized, format-agnostic view of a single hierarchy node."""

    __slots__ = ("text", "hint", "rid", "desc", "cls", "clickable",
                 "scrollable", "focusable", "checkable", "bounds")

    def __init__(self, attrs: dict):
        self.text = _first(attrs, _TEXT_KEYS)
        self.hint = _first(attrs, _HINT_KEYS)
        self.rid = _short_id(_first(attrs, _ID_KEYS))
        self.desc = _first(attrs, _DESC_KEYS)
        self.cls = _short_class(_first(attrs, _CLASS_KEYS))
        self.clickable = _is_truthy(attrs, "clickable")
        self.scrollable = _is_truthy(attrs, "scrollable")
        self.focusable = _is_truthy(attrs, "focusable") or _is_truthy(attrs, "focused")
        self.checkable = _is_truthy(attrs, "checkable") or _is_truthy(attrs, "checked")
        self.bounds = str(attrs.get("bounds", "")).strip()

    @property
    def is_input(self) -> bool:
        """True when the node is a text-entry widget."""
        cls = self.cls.lower()
        return any(hint in cls for hint in _INPUT_HINTS)

    @property
    def is_relevant(self) -> bool:
        """Keep nodes a tester could actually target; drop pure layout chrome.

        A node is worth keeping if it carries something to **assert on**
        (visible text, accessibility label, or input hint) OR something to
        **interact with** (clickable / scrollable / checkable / a text field).

        Note: a resource id alone is intentionally NOT enough. System chrome
        (status bar, navigation containers) is full of id-bearing layout nodes
        with no text and no interaction — keeping those just reintroduces noise.
        Any id-bearing node that is genuinely targetable also has text or is
        interactive, so its id is preserved through one of the checks below.
        """
        return bool(
            self.text
            or self.desc
            or self.hint
            or self.clickable
            or self.scrollable
            or self.checkable
            or self.is_input
        )

    def flags(self) -> str:
        """Compact interaction flags, e.g. ``tap,scroll,input``."""
        parts = []
        if self.clickable:
            parts.append("tap")
        if self.scrollable:
            parts.append("scroll")
        if self.is_input:
            parts.append("input")
        if self.checkable:
            parts.append("check")
        return ",".join(parts)

    def label(self) -> str:
        """Best human-readable label: visible text, else accessibility, else hint."""
        return self.text or self.desc or (f"<hint: {self.hint}>" if self.hint else "")


def _walk_json(node: Any) -> Iterable[Node]:
    """Yield :class:`Node` for every entry in a Maestro JSON hierarchy."""
    if not isinstance(node, dict):
        return
    attrs = node.get("attributes")
    if isinstance(attrs, dict):
        yield Node(attrs)
    for child in node.get("children", []) or []:
        yield from _walk_json(child)


def _walk_xml(elem: ET.Element) -> Iterable[Node]:
    """Yield :class:`Node` for every ``<node>`` in a uiautomator XML dump."""
    yield Node(dict(elem.attrib))
    for child in list(elem):
        yield from _walk_xml(child)


def _strip_to_payload(raw: str) -> str:
    """Maestro prefixes its JSON with lines like ``Running on Pixel_8``.

    Trim anything before the first ``{`` (JSON) or ``<`` (XML) so the payload
    parses cleanly regardless of CLI banners.
    """
    for marker in ("{", "<"):
        idx = raw.find(marker)
        if idx != -1:
            return raw[idx:]
    return raw


def parse(raw: str) -> list[Node]:
    """Parse a dump (JSON or XML, auto-detected) into a list of nodes."""
    payload = _strip_to_payload(raw)
    if payload.lstrip().startswith("{"):
        return list(_walk_json(json.loads(payload)))
    return list(_walk_xml(ET.fromstring(payload)))


def render(nodes: list[Node]) -> str:
    """Render relevant nodes as a Markdown table plus a summary line."""
    kept = [n for n in nodes if n.is_relevant]
    lines = [
        "| Label | id | class | flags | bounds |",
        "|-------|----|-------|-------|--------|",
    ]
    for n in kept:
        lines.append(
            f"| {n.label() or '—'} | {n.rid or '—'} | {n.cls or '—'} "
            f"| {n.flags() or '—'} | {n.bounds or '—'} |"
        )
    dropped = len(nodes) - len(kept)
    lines.append("")
    lines.append(
        f"_Kept {len(kept)} interactable nodes, dropped {dropped} noise nodes "
        f"(of {len(nodes)} total)._"
    )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """Entry point: read a dump from a file arg or stdin and print the table."""
    if len(argv) > 1:
        with open(argv[1], "r", encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        print("No input. Pass a dump file path or pipe a dump via stdin.",
              file=sys.stderr)
        return 1

    try:
        nodes = parse(raw)
    except (json.JSONDecodeError, ET.ParseError) as exc:
        print(f"Could not parse dump (not valid JSON or XML): {exc}",
              file=sys.stderr)
        return 1

    print(render(nodes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

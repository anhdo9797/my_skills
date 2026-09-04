#!/usr/bin/env python3
"""Parse a Bitbucket pull request URL into its addressing parts.

Supports Bitbucket Cloud (bitbucket.org) and Bitbucket Server / Data Center
(self-hosted), and rejects every non-Bitbucket host explicitly so that a
GitHub or GitLab URL can never be silently reinterpreted as a Bitbucket PR.

Usage:
    python parse_pr_url.py "<url>"

Output:
    stdout is always a single JSON object.
    exit 0 - parsed successfully
    exit 2 - not a supported Bitbucket pull request URL ("error" explains why)
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import unquote, urlparse

# Hosts that are frequently pasted by mistake. Naming them produces a clearer
# refusal than a generic "unrecognised URL".
KNOWN_OTHER_FORGES = {
    "github.com": "GitHub",
    "www.github.com": "GitHub",
    "gitlab.com": "GitLab",
    "www.gitlab.com": "GitLab",
    "dev.azure.com": "Azure DevOps",
    "gitea.com": "Gitea",
    "codeberg.org": "Codeberg",
}

CLOUD_HOSTS = {"bitbucket.org", "www.bitbucket.org"}

# Cloud: /{workspace}/{repo}/pull-requests/{id}[/anything]
CLOUD_RE = re.compile(
    r"^/(?P<workspace>[^/]+)/(?P<repo>[^/]+)/pull-requests/(?P<pr_id>\d+)(?:/.*)?$"
)

# Server / Data Center project repo:
#   /projects/{PROJECT}/repos/{repo}/pull-requests/{id}[/anything]
# optionally behind a context path such as /bitbucket or /stash.
SERVER_PROJECT_RE = re.compile(
    r"^(?P<context>(?:/[^/]+)*?)/projects/(?P<project>[^/]+)"
    r"/repos/(?P<repo>[^/]+)/pull-requests/(?P<pr_id>\d+)(?:/.*)?$"
)

# Server / Data Center personal repo:
#   /users/{user}/repos/{repo}/pull-requests/{id}[/anything]
SERVER_USER_RE = re.compile(
    r"^(?P<context>(?:/[^/]+)*?)/users/(?P<user>[^/]+)"
    r"/repos/(?P<repo>[^/]+)/pull-requests/(?P<pr_id>\d+)(?:/.*)?$"
)


def fail(message: str, **extra: object) -> None:
    """Print a JSON error object and exit with code 2."""
    payload: dict[str, object] = {"ok": False, "error": message}
    payload.update(extra)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(2)


def parse(url: str) -> dict[str, object]:
    """Parse a Bitbucket PR URL, or exit(2) with an explanatory JSON error.

    Args:
        url: The pull request URL as the user supplied it.

    Returns:
        A dict describing the pull request address.
    """
    raw = url.strip().strip("<>").strip('"').strip("'")
    if not raw:
        fail("Empty URL.")

    # Tolerate a scheme-less paste such as bitbucket.org/acme/app/pull-requests/1
    if "://" not in raw:
        raw = "https://" + raw

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not host:
        fail("Could not determine a host from the URL.", url=url)

    if host in KNOWN_OTHER_FORGES:
        fail(
            f"{KNOWN_OTHER_FORGES[host]} URL, not Bitbucket. "
            "This skill reviews Bitbucket pull requests only.",
            host=host,
            forge=KNOWN_OTHER_FORGES[host],
        )

    path = unquote(parsed.path).rstrip("/")

    if host in CLOUD_HOSTS:
        match = CLOUD_RE.match(path)
        if not match:
            fail(
                "Bitbucket Cloud host, but the path is not a pull request. "
                "Expected /{workspace}/{repo}/pull-requests/{id}.",
                host=host,
                path=path or "/",
            )
        workspace = match.group("workspace")
        repo = match.group("repo")
        pr_id = int(match.group("pr_id"))
        return {
            "ok": True,
            "kind": "cloud",
            "host": host,
            "workspace": workspace,
            "project": None,
            "repo": repo,
            "full_name": f"{workspace}/{repo}",
            "pr_id": pr_id,
            "canonical_url": (
                f"https://{host}/{workspace}/{repo}/pull-requests/{pr_id}"
            ),
        }

    # Anything else may still be a self-hosted Bitbucket Server. Its path shape
    # is distinctive enough to identify it without trusting the hostname.
    for regex, owner_key, kind_label in (
        (SERVER_PROJECT_RE, "project", "server"),
        (SERVER_USER_RE, "user", "server"),
    ):
        match = regex.match(path)
        if not match:
            continue
        owner = match.group(owner_key)
        repo = match.group("repo")
        pr_id = int(match.group("pr_id"))
        context = match.group("context") or ""
        base = f"{parsed.scheme}://{parsed.netloc}{context}"
        owner_segment = (
            f"projects/{owner}" if owner_key == "project" else f"users/{owner}"
        )
        return {
            "ok": True,
            "kind": kind_label,
            "host": host,
            "workspace": owner if owner_key == "user" else None,
            "project": owner if owner_key == "project" else None,
            "repo": repo,
            "full_name": f"{owner}/{repo}",
            "pr_id": pr_id,
            "canonical_url": (
                f"{base}/{owner_segment}/repos/{repo}/pull-requests/{pr_id}"
            ),
        }

    fail(
        "Not a recognised Bitbucket pull request URL. Expected Bitbucket Cloud "
        "(/{workspace}/{repo}/pull-requests/{id}) or Bitbucket Server "
        "(/projects/{KEY}/repos/{repo}/pull-requests/{id}).",
        host=host,
        path=path or "/",
    )
    raise AssertionError("unreachable")  # pragma: no cover


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) != 2:
        fail("Usage: parse_pr_url.py <url>")
    result = parse(sys.argv[1])
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

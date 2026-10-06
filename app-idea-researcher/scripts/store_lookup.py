#!/usr/bin/env python3
"""Read public app store data for competitor research. Standard library only, no API keys.

Usage:
  store_lookup.py play-search QUERY [--gl US] [--limit 10] [--details] [--json]
  store_lookup.py play PACKAGE [PACKAGE ...] [--gl US] [--json]
  store_lookup.py ios-search TERM [--country us] [--limit 10] [--json]
  store_lookup.py ios ID [ID ...] [--country us] [--json]

Google Play has no public API, so `play` reads the public details page: the schema.org JSON-LD
block (name, category, developer, rating, rating count, price) plus the visible install bucket,
"Updated on" date and the "Contains ads" / "In-app purchases" flags. App Store data comes from
the public iTunes Search API.

Any field that cannot be read is reported as null. The script never guesses; if Play changes its
page layout, fields go null and the caller should read the page directly.
"""

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
PLAY_DETAILS = "https://play.google.com/store/apps/details?id={pkg}&hl=en&gl={gl}"
PLAY_SEARCH = "https://play.google.com/store/search?q={q}&c=apps&hl=en&gl={gl}"
ITUNES_SEARCH = "https://itunes.apple.com/search?term={q}&entity=software&country={country}&limit={limit}"
ITUNES_LOOKUP = "https://itunes.apple.com/lookup?id={ids}&country={country}"
PLAY_DELAY_SECONDS = 1.0


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _first(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    return html.unescape(m.group(1)).strip() if m else None


def parse_play_details(page, pkg):
    app = {
        "store": "google_play",
        "id": pkg,
        "name": None,
        "developer": None,
        "category": None,
        "rating": None,
        "rating_count": None,
        "installs": None,
        "updated": None,
        "price": None,
        "contains_ads": None,
        "in_app_purchases": None,
        "url": "https://play.google.com/store/apps/details?id=" + pkg,
    }

    for block in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if data.get("@type") != "SoftwareApplication":
            continue
        app["name"] = data.get("name")
        app["category"] = data.get("applicationCategory")
        app["developer"] = (data.get("author") or {}).get("name")
        rating = data.get("aggregateRating") or {}
        if rating.get("ratingValue"):
            app["rating"] = round(float(rating["ratingValue"]), 2)
        if rating.get("ratingCount"):
            app["rating_count"] = int(rating["ratingCount"])
        offers = data.get("offers") or []
        if offers:
            app["price"] = "{} {}".format(offers[0].get("price"), offers[0].get("priceCurrency")).strip()
        break

    app["installs"] = _first(r">([0-9][0-9.,]*[KMB]?\+)</div><div[^>]*>Downloads<", page)
    app["updated"] = _first(r"Updated on</div><div[^>]*>([^<]+)<", page)

    # The ads / IAP flags sit between the app title and the Downloads stat. Searching only that
    # window keeps flags of "similar apps" further down the page from leaking in.
    start = page.find('itemprop="name"')
    end = page.find(">Downloads<", start if start >= 0 else 0)
    if start >= 0 and end > start:
        header = page[start:end]
        app["contains_ads"] = "Contains ads" in header
        app["in_app_purchases"] = "In-app purchases" in header
    return app


def play_details(pkgs, gl):
    results = []
    for i, pkg in enumerate(pkgs):
        if i:
            time.sleep(PLAY_DELAY_SECONDS)
        try:
            page = fetch(PLAY_DETAILS.format(pkg=urllib.parse.quote(pkg), gl=gl))
            results.append(parse_play_details(page, pkg))
        except urllib.error.HTTPError as e:
            results.append({"store": "google_play", "id": pkg, "error": "HTTP {}".format(e.code)})
        except (urllib.error.URLError, TimeoutError) as e:
            results.append({"store": "google_play", "id": pkg, "error": str(e)})
    return results


def play_search(query, gl, limit):
    page = fetch(PLAY_SEARCH.format(q=urllib.parse.quote(query), gl=gl))
    seen = []
    for pkg in re.findall(r"/store/apps/details\?id=([A-Za-z0-9_.]+)", page):
        if pkg not in seen:
            seen.append(pkg)
        if len(seen) >= limit:
            break
    return seen


def _ios_row(r):
    return {
        "store": "app_store",
        "id": r.get("trackId"),
        "name": r.get("trackName"),
        "developer": r.get("sellerName") or r.get("artistName"),
        "category": r.get("primaryGenreName"),
        "rating": round(r["averageUserRating"], 2) if r.get("averageUserRating") is not None else None,
        "rating_count": r.get("userRatingCount"),
        "installs": None,  # the App Store does not publish install counts
        "updated": (r.get("currentVersionReleaseDate") or "")[:10] or None,
        "released": (r.get("releaseDate") or "")[:10] or None,
        "price": r.get("formattedPrice"),
        "bundle_id": r.get("bundleId"),
        "url": r.get("trackViewUrl", "").split("?")[0] or None,
    }


def ios_search(term, country, limit):
    data = json.loads(fetch(ITUNES_SEARCH.format(q=urllib.parse.quote(term), country=country, limit=limit)))
    return [_ios_row(r) for r in data.get("results", [])]


def ios_lookup(ids, country):
    data = json.loads(fetch(ITUNES_LOOKUP.format(ids=",".join(ids), country=country)))
    found = [_ios_row(r) for r in data.get("results", []) if r.get("wrapperType") == "software"]
    missing = set(ids) - {str(r["id"]) for r in found}
    return found + [{"store": "app_store", "id": i, "error": "not found in this country"} for i in sorted(missing)]


def print_table(rows):
    cols = ["name", "id", "developer", "rating", "rating_count", "installs", "updated", "price",
            "contains_ads", "in_app_purchases", "error"]
    cols = [c for c in cols if any(c in r for r in rows)]

    def cell(v):
        if v is None:
            return "null"
        return str(v).replace("|", "/")

    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        print("| " + " | ".join(cell(r.get(c)) for c in cols) + " |")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("play-search", help="Google Play search: package ids in result order")
    p.add_argument("query")
    p.add_argument("--gl", default="US")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--details", action="store_true", help="also fetch each app's details page")

    p = sub.add_parser("play", help="Google Play details for one or more package ids")
    p.add_argument("packages", nargs="+")
    p.add_argument("--gl", default="US")

    p = sub.add_parser("ios-search", help="App Store search via the iTunes Search API")
    p.add_argument("term")
    p.add_argument("--country", default="us")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("ios", help="App Store lookup by numeric app id")
    p.add_argument("ids", nargs="+")
    p.add_argument("--country", default="us")

    for p in sub.choices.values():
        p.add_argument("--json", action="store_true", help="print JSON instead of a Markdown table")

    args = parser.parse_args()
    try:
        if args.cmd == "play-search":
            pkgs = play_search(args.query, args.gl, args.limit)
            rows = play_details(pkgs, args.gl) if args.details else [
                {"store": "google_play", "id": pkg} for pkg in pkgs]
        elif args.cmd == "play":
            rows = play_details(args.packages, args.gl)
        elif args.cmd == "ios-search":
            rows = ios_search(args.term, args.country, args.limit)
        else:
            rows = ios_lookup(args.ids, args.country)
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit("store_lookup: request failed: {}".format(e))

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif rows:
        print_table(rows)
    else:
        print("(no results)")


if __name__ == "__main__":
    main()

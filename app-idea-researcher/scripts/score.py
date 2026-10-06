#!/usr/bin/env python3
"""Score app ideas with the Phase 4 weighted model and apply the verdict rules.

Usage:
  score.py ideas.json [--lang vi]
  score.py --scores 6,8,8,7,6,7,8 [--confidence L,M,H,M,L,H,H] [--name TankMate] [--lang vi]

ideas.json is a list of ideas:
  [
    {
      "name": "TankMate",
      "scores":     {"market_demand": 6, "competition_gap": 8, "usp_strength": 8,
                     "technical_feasibility": 7, "revenue_potential": 6,
                     "time_to_mvp": 7, "scalability": 8},
      "confidence": {"market_demand": "low", "competition_gap": "high", ...},
      "scenarios":  {"Strip-reading spike fails": {"usp_strength": 5, "technical_feasibility": 5}}
    }
  ]

`--scores` takes the seven scores in the order of CRITERIA below.

Rules (single source of truth, mirrored in references/feasibility_scoring_model.md):
  - Overall = weighted sum, rounded half-up to 1 decimal. Verdict uses the rounded score.
  - Bands: >= 7.5 Go | 6.5-7.4 Conditional Go | 5.5-6.4 Backup | < 5.5 No-Go
  - Any criterion <= 3            -> at best Conditional Go
  - Two or more criteria <= 3     -> No-Go
  - Market Demand or Revenue Potential at Low confidence -> at best Conditional Go
  - A missing confidence counts as Low.
  - Downside: every Low-confidence criterion 2 points worse (min 1).
"""

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal

CRITERIA = [
    ("market_demand", "0.20"),
    ("competition_gap", "0.20"),
    ("usp_strength", "0.15"),
    ("technical_feasibility", "0.15"),
    ("revenue_potential", "0.15"),
    ("time_to_mvp", "0.10"),
    ("scalability", "0.05"),
]
WEIGHTS = {k: Decimal(w) for k, w in CRITERIA}
GATED_BY_CONFIDENCE = ("market_demand", "revenue_potential")
VERDICTS = ["no_go", "backup", "conditional", "go"]  # worst -> best
BANDS = [(Decimal("7.5"), "go"), (Decimal("6.5"), "conditional"), (Decimal("5.5"), "backup")]

LABELS = {
    "en": {
        "criteria": {
            "market_demand": "Market Demand",
            "competition_gap": "Competition Gap",
            "usp_strength": "USP Strength",
            "technical_feasibility": "Technical Feasibility",
            "revenue_potential": "Revenue Potential",
            "time_to_mvp": "Time to MVP",
            "scalability": "Scalability",
        },
        "verdict": {"go": "🟢 Go", "conditional": "🟡 Conditional Go", "backup": "🟠 Backup", "no_go": "🔴 No-Go"},
        "confidence": {"high": "High", "medium": "Medium", "low": "Low"},
        "head_rank": ["Rank", "Idea", "Score", "Verdict", "Gates", "Downside"],
        "head_detail": ["Criterion", "Score", "Weight", "Points", "Confidence"],
        "overall": "Overall",
        "scenario": "Scenario",
        "gate_low": "{n} criterion ≤3 → max Conditional",
        "gate_many": "{n} criteria ≤3 → No-Go",
        "gate_conf": "{c} at Low confidence → max Conditional",
        "missing_conf": "confidence missing for {c} → treated as Low",
    },
    "vi": {
        "criteria": {
            "market_demand": "Nhu cầu thị trường",
            "competition_gap": "Khoảng trống cạnh tranh",
            "usp_strength": "Sức mạnh USP",
            "technical_feasibility": "Khả thi kỹ thuật",
            "revenue_potential": "Tiềm năng doanh thu",
            "time_to_mvp": "Thời gian ra MVP",
            "scalability": "Khả năng mở rộng",
        },
        "verdict": {"go": "🟢 Go", "conditional": "🟡 Go có điều kiện", "backup": "🟠 Dự phòng", "no_go": "🔴 Loại"},
        "confidence": {"high": "Cao", "medium": "TB", "low": "Thấp"},
        "head_rank": ["Hạng", "Ý tưởng", "Điểm", "Kết luận", "Chặn cứng", "Kịch bản xấu"],
        "head_detail": ["Tiêu chí", "Điểm", "Trọng số", "Điểm quy đổi", "Độ tin cậy"],
        "overall": "Tổng",
        "scenario": "Kịch bản",
        "gate_low": "{n} tiêu chí ≤3 → tối đa Go có điều kiện",
        "gate_many": "{n} tiêu chí ≤3 → Loại",
        "gate_conf": "{c} độ tin cậy Thấp → tối đa Go có điều kiện",
        "missing_conf": "thiếu độ tin cậy cho {c} → coi là Thấp",
    },
}
CONFIDENCE_ALIASES = {"h": "high", "high": "high", "m": "medium", "medium": "medium", "med": "medium",
                      "l": "low", "low": "low"}


def round1(x):
    return x.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def weighted(scores):
    return sum(Decimal(str(scores[k])) * WEIGHTS[k] for k, _ in CRITERIA)


def band(score):
    for floor, verdict in BANDS:
        if score >= floor:
            return verdict
    return "no_go"


def worse(a, b):
    return a if VERDICTS.index(a) <= VERDICTS.index(b) else b


def evaluate(scores, confidence, lab):
    exact = weighted(scores)
    shown = round1(exact)
    verdict = band(shown)
    gates = []
    low = [k for k, _ in CRITERIA if scores[k] <= 3]
    if len(low) >= 2:
        verdict = "no_go"
        gates.append(lab["gate_many"].format(n=len(low)))
    elif len(low) == 1:
        verdict = worse(verdict, "conditional")
        gates.append(lab["gate_low"].format(n=1))
    for k in GATED_BY_CONFIDENCE:
        if confidence[k] == "low":
            verdict = worse(verdict, "conditional")
            gates.append(lab["gate_conf"].format(c=lab["criteria"][k]))
    return exact, shown, verdict, gates


def normalize(idea, index):
    name = idea.get("name") or "Idea {}".format(index + 1)
    scores = idea.get("scores") or {}
    missing = [k for k, _ in CRITERIA if k not in scores]
    if missing:
        sys.exit("{}: missing scores for {}".format(name, ", ".join(missing)))
    for k, v in scores.items():
        if k not in WEIGHTS:
            sys.exit("{}: unknown criterion '{}'".format(name, k))
        if not 1 <= float(v) <= 10:
            sys.exit("{}: {} must be between 1 and 10 (got {})".format(name, k, v))
    conf_in = idea.get("confidence") or {}
    confidence, warnings = {}, []
    for k, _ in CRITERIA:
        raw = str(conf_in.get(k, "")).strip().lower()
        if raw in CONFIDENCE_ALIASES:
            confidence[k] = CONFIDENCE_ALIASES[raw]
        else:
            confidence[k] = "low"
            warnings.append(k)
    return name, scores, confidence, idea.get("scenarios") or {}, warnings


def run(ideas, lang):
    lab = LABELS[lang]
    rows = []
    for i, idea in enumerate(ideas):
        name, scores, confidence, scenarios, warnings = normalize(idea, i)
        exact, shown, verdict, gates = evaluate(scores, confidence, lab)
        low_conf = [k for k, _ in CRITERIA if confidence[k] == "low"]
        downside = None
        if low_conf:
            dscores = dict(scores, **{k: max(1, scores[k] - 2) for k in low_conf})
            _, dshown, dverdict, _ = evaluate(dscores, confidence, lab)
            downside = (dshown, dverdict)
        rows.append(dict(name=name, scores=scores, confidence=confidence, exact=exact, shown=shown,
                         verdict=verdict, gates=gates, downside=downside, scenarios=scenarios,
                         warnings=warnings))

    rows.sort(key=lambda r: (-r["exact"], r["name"]))

    h = lab["head_rank"]
    print("| " + " | ".join(h) + " |")
    print("|:-:|---|:-:|---|---|---|")
    for rank, r in enumerate(rows, 1):
        down = "—" if not r["downside"] else "{} ({})".format(r["downside"][0], lab["verdict"][r["downside"][1]])
        print("| {} | {} | **{}** | {} | {} | {} |".format(
            rank, r["name"], r["shown"], lab["verdict"][r["verdict"]], "; ".join(r["gates"]) or "—", down))

    for r in rows:
        print("\n### {} — {} {}".format(r["name"], r["shown"], lab["verdict"][r["verdict"]]))
        h = lab["head_detail"]
        print("| " + " | ".join(h) + " |")
        print("|---|:-:|:-:|:-:|:-:|")
        for k, _ in CRITERIA:
            print("| {} | {}/10 | {}% | {} | {} |".format(
                lab["criteria"][k], r["scores"][k], int(WEIGHTS[k] * 100),
                (Decimal(str(r["scores"][k])) * WEIGHTS[k]).normalize(), lab["confidence"][r["confidence"][k]]))
        exact_note = "" if r["exact"] == r["shown"] else " (= {})".format(r["exact"].normalize())
        print("| **{}** | | | **{}**{} | |".format(lab["overall"], r["shown"], exact_note))
        for title, overrides in r["scenarios"].items():
            unknown = [k for k in overrides if k not in WEIGHTS]
            if unknown:
                sys.exit("{}: scenario '{}' has unknown criteria {}".format(r["name"], title, unknown))
            sscores = dict(r["scores"], **overrides)
            _, sshown, sverdict, _ = evaluate(sscores, r["confidence"], lab)
            delta = sshown - r["shown"]
            print("- {} \"{}\": {} ({:+}) → {}".format(lab["scenario"], title, sshown, delta, lab["verdict"][sverdict]))
        for k in r["warnings"]:
            print("- ⚠️ " + lab["missing_conf"].format(c=lab["criteria"][k]))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", help="JSON file with a list of ideas")
    parser.add_argument("--scores", help="seven comma-separated scores in CRITERIA order")
    parser.add_argument("--confidence", help="seven comma-separated confidences (H/M/L)")
    parser.add_argument("--name", default="Idea")
    parser.add_argument("--lang", choices=sorted(LABELS), default="en")
    args = parser.parse_args()

    if args.scores:
        values = [float(v) if "." in v else int(v) for v in args.scores.split(",")]
        if len(values) != len(CRITERIA):
            sys.exit("--scores needs {} values".format(len(CRITERIA)))
        idea = {"name": args.name, "scores": dict(zip([k for k, _ in CRITERIA], values))}
        if args.confidence:
            conf = [c.strip() for c in args.confidence.split(",")]
            if len(conf) != len(CRITERIA):
                sys.exit("--confidence needs {} values".format(len(CRITERIA)))
            idea["confidence"] = dict(zip([k for k, _ in CRITERIA], conf))
        ideas = [idea]
    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            ideas = json.load(f)
        if isinstance(ideas, dict):
            ideas = [ideas]
    else:
        parser.error("pass a JSON file or --scores")
    run(ideas, args.lang)


if __name__ == "__main__":
    main()

"""Check whether the circulars the rule-pack cites are still current.

Why this exists
---------------
The rule-pack cites paragraph numbers in one specific document. That document can be
amended or repealed without a single byte of our YAML changing, and the pack would go on
citing dead law with full confidence. This is not hypothetical: RBI/DPSS/2026-27/396 --
the circular we cite -- itself repealed eight earlier circulars in one stroke. Anyone who
had encoded those was, that morning, wrong and unaware.

This script is the cheap insurance. It reads RBI's notifications feed, looks for anything
on our topic published since our circular took effect, and reports it. It decides nothing
and changes no rule: the output is a prompt for a human to go and read something.

Why it matches on topic, not on circular number
-----------------------------------------------
An earlier version asked "is any circular number higher than ours?". That was wrong, and
the feed proves it: notifications from September 2026 are numbered RBI/2026-27/242..251
while the circular we cite, from April 2026, is RBI/DPSS/2026-27/396. The serial is not a
global sequence -- departmental streams number independently -- so comparing 396 against
251 answers nothing. Dates and subject matter are the only sound signals here.

Deliberately outside the verdict path
-------------------------------------
It touches the network, so it lives in scripts/ and not in app/core/, which
tests/test_isolation.py forbids from importing anything of the kind. Nothing at request
time depends on it. If the feed is unreachable or its shape has changed, this says so and
exits 2 -- it never blocks a verdict, and it never reports "all clear" on no evidence.

Known limitation: the feed carries only the ~10 most recent notifications, so it is a
"what changed lately" check, not an archive search. Run it regularly, or widen the window
by hand if a long time has passed.

Usage
-----
    python scripts/check_circulars.py            # fetch and report
    python scripts/check_circulars.py --offline  # report what we cite, no network
    python scripts/check_circulars.py --stamp    # record today's date in the pack

Exit codes: 0 nothing on topic found, 1 needs a human, 2 could not check.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core.rules_loader import DEFAULT_RULES_DIR, load_pack  # noqa: E402

RBI_RSS = "https://rbi.org.in/notifications_rss.xml"
RBI_HUMAN_URL = "https://www.rbi.org.in/Scripts/NotificationUser.aspx"

CIRCULAR_RE = re.compile(r"RBI/(?:[A-Z]+/)?\d{4}-\d{2}/\d+")
ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S | re.I)

# Subject matter that would touch this rule-pack. Deliberately broad: a false alarm costs
# a minute of reading, a miss costs a wrong verdict cited to a repealed clause.
TOPIC_WORDS = (
    "e-mandate",
    "e mandate",
    "emandate",
    "recurring transaction",
    "recurring payment",
    "auto-debit",
    "auto debit",
    "additional factor of authentication",
    "afa",
    "fastag",
    "ncmc",
    "standing instruction",
)

STALE_AFTER_DAYS = 90


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", block, re.S | re.I)
    return (m.group(1) if m else "").strip()


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _parse_pubdate(raw: str) -> date | None:
    for fmt in ("%a, %d %b %Y %H:%M:%S", "%a, %d %b %Y %H:%M:%S %z", "%d %b %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def fetch(url: str, timeout: int = 30) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rakshak-circular-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  could not reach {url}: {exc}")
        return None


def cited_circulars() -> list[tuple[str, str, date | None, date | None]]:
    """(pack_file, circular, effective_from, circular_checked_on) per primary pack file."""
    import yaml

    seen: dict[str, tuple[str, str, date | None, date | None]] = {}
    for path in sorted(DEFAULT_RULES_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "circular" not in raw:
            continue  # non-primary file: carries no circular of its own
        pack = load_pack(str(raw["version"]))
        for s in pack.sources:
            if s.primary and s.circular and s.file == path.name:
                seen[s.file] = (s.file, s.circular, s.effective_from, s.circular_checked_on)
    return list(seen.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="skip the network check")
    ap.add_argument("--stamp", action="store_true", help="record today in circular_checked_on")
    args = ap.parse_args()

    cited = cited_circulars()
    if not cited:
        print("No primary pack declares a `circular:` -- nothing to check.")
        return 1

    print("Cited circulars")
    print("-" * 70)
    stale = False
    since: date | None = None
    for file, circ, eff, checked in cited:
        age = f"checked {checked}" if checked else "NEVER CHECKED"
        if checked:
            days = (date.today() - checked).days
            age += f" ({days}d ago)"
            if days > STALE_AFTER_DAYS:
                age += "  STALE"
                stale = True
        else:
            stale = True
        print(f"  {circ:28} effective {eff}   {age}")
        print(f"    from {file}")
        if eff and (since is None or eff < since):
            since = eff

    if args.offline:
        print("\n--offline: no network check performed.")
        return 1 if stale else 0

    print(f"\nFetching {RBI_RSS}")
    xml = fetch(RBI_RSS)
    if xml is None:
        print("\nRESULT: could not check. This is not a failure of the rule-pack; it is")
        print(f"a failure to verify it. Re-run, or read {RBI_HUMAN_URL} by hand.")
        return 2

    blocks = ITEM_RE.findall(xml)
    if not blocks:
        # Fetched but unparseable means this run proves nothing. Saying "all clear" here
        # would be the worst outcome, since the point is to catch silent drift.
        print("\nRESULT: INCONCLUSIVE. The feed was fetched but no <item> could be parsed,")
        print("so this run proves nothing either way. The feed shape may have changed.")
        print(f"Check {RBI_HUMAN_URL} by hand, or update the parser.")
        print("Do NOT read this as confirmation.")
        return 2

    items = []
    for b in blocks:
        body = _strip_html(_tag(b, "description"))
        title = _strip_html(_tag(b, "title"))
        published = _parse_pubdate(_tag(b, "pubDate"))
        ref_match = CIRCULAR_RE.search(body)
        items.append(
            {
                "title": title,
                "ref": ref_match.group(0) if ref_match else "(no ref)",
                "published": published,
                "haystack": f"{title} {body}".lower(),
            }
        )

    print(f"  parsed {len(items)} notification(s)")
    dates = [i["published"] for i in items if i["published"]]
    if dates:
        print(f"  covering {min(dates)} to {max(dates)}")

    recent = [i for i in items if since is None or i["published"] is None or i["published"] >= since]
    hits = [i for i in recent if any(w in i["haystack"] for w in TOPIC_WORDS)]

    print("\nRESULT")
    print("-" * 70)
    if hits:
        print(f"  ATTENTION. {len(hits)} recent notification(s) touch this rule-pack's subject:")
        for i in hits:
            print(f"    {i['ref']}  {i['published']}  {i['title'][:70]}")
        print("\n  Read them. If any amends or repeals what we cite, update the clause")
        print("  fields and re-verify the affected values before trusting a verdict.")
        return 1

    print(f"  No notification in the feed mentions this pack's subject matter.")
    print(f"  Checked {len(recent)} notification(s) published on or after {since}.")
    print("  Note: the feed carries only the most recent notifications, so this is a")
    print("  'nothing changed lately' signal, not an archive search.")

    if args.stamp:
        n = stamp_today()
        print(f"\n  stamped circular_checked_on: {date.today()} in {n} file(s)")
        return 0

    print("\n  Re-run with --stamp to record that you checked today.")
    return 1 if stale else 0


def stamp_today() -> int:
    """Rewrite `circular_checked_on:` in every primary pack. Textual on purpose --
    round-tripping the YAML through a parser would strip the comments, and those comments
    are where the reasoning behind each value lives."""
    n = 0
    today = date.today().isoformat()
    for path in sorted(DEFAULT_RULES_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        if "circular:" not in text:
            continue
        if "circular_checked_on:" in text:
            text = re.sub(
                r'circular_checked_on:\s*"?[\d-]*"?', f'circular_checked_on: "{today}"', text
            )
        else:
            text = re.sub(
                r'(effective_from:\s*"?[\d-]+"?\n)', rf'\1circular_checked_on: "{today}"\n', text
            )
        path.write_text(text, encoding="utf-8")
        n += 1
    return n


if __name__ == "__main__":
    raise SystemExit(main())

"""The circular-currency watcher's parser, exercised without a network call.

The parser is the fragile part: RBI can change the feed's shape at any time, and the
failure that matters is not a crash but a *silent* one -- a run that parses nothing and
reports "all clear". These tests pin the shape and, more importantly, pin the honesty of
the no-evidence path.

The script lives in scripts/ rather than app/ because it reaches the network, which
`test_isolation.py` forbids anywhere near the core.
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_circulars.py"


@pytest.fixture(scope="module")
def cc():
    spec = importlib.util.spec_from_file_location("check_circulars", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_circulars"] = mod
    spec.loader.exec_module(mod)
    return mod


FEED = """<rss><channel>
<item><title><![CDATA[Deposits and Accounts]]></title>
<description><![CDATA[<p>RBI/2026-27/251<br>A.P. (DIR Series) Circular No. 20</p>]]></description>
<pubDate>Wed, 02 Sep 2026 20:35:00</pubDate></item>
<item><title><![CDATA[Processing of e-mandates for recurring transactions]]></title>
<description><![CDATA[<p>RBI/DPSS/2026-27/400</p><p>additional factor of authentication</p>]]></description>
<pubDate>Mon, 31 Aug 2026 10:00:00</pubDate></item>
</channel></rss>"""


def test_extracts_ref_title_and_date(cc):
    blocks = cc.ITEM_RE.findall(FEED)
    assert len(blocks) == 2
    body = cc._strip_html(cc._tag(blocks[0], "description"))
    assert cc.CIRCULAR_RE.search(body).group(0) == "RBI/2026-27/251"
    assert cc._parse_pubdate(cc._tag(blocks[0], "pubDate")) == date(2026, 9, 2)


def test_cdata_and_html_are_stripped(cc):
    title = cc._tag(cc.ITEM_RE.findall(FEED)[1], "title")
    assert title == "Processing of e-mandates for recurring transactions"
    assert "<" not in cc._strip_html(cc._tag(cc.ITEM_RE.findall(FEED)[1], "description"))


def test_topic_matching_finds_the_relevant_notification(cc):
    hits = [
        b
        for b in cc.ITEM_RE.findall(FEED)
        if any(
            w in f"{cc._tag(b, 'title')} {cc._tag(b, 'description')}".lower()
            for w in cc.TOPIC_WORDS
        )
    ]
    assert len(hits) == 1
    assert "e-mandate" in cc._tag(hits[0], "title").lower()


def test_an_unrelated_notification_is_not_flagged(cc):
    block = cc.ITEM_RE.findall(FEED)[0]
    hay = f"{cc._tag(block, 'title')} {cc._tag(block, 'description')}".lower()
    # "Deposits and Accounts" must not trip the watcher; a watcher that cries wolf on
    # every circular gets muted, and a muted watcher is worse than none.
    assert not any(w in hay for w in cc.TOPIC_WORDS)


def test_serial_numbers_are_not_used_for_ordering(cc):
    """A regression guard on a real bug this script used to have.

    It once asked "is any circular number higher than ours?". RBI's serials are not a
    global sequence: September 2026 notifications are RBI/2026-27/24x while the April 2026
    circular we cite is RBI/DPSS/2026-27/396. Comparing those answers nothing, so no
    ordering helper may come back.
    """
    assert not hasattr(cc, "_sort_key"), "ordering by serial is not sound; do not reinstate"


def test_unparseable_feed_is_inconclusive_not_clear(cc, monkeypatch, capsys):
    """The failure that matters: parsing nothing must never read as 'all clear'."""
    monkeypatch.setattr(cc, "fetch", lambda *a, **k: "<html>not a feed</html>")
    # main() reads argv, so give it a clean one rather than pytest's.
    monkeypatch.setattr(sys, "argv", ["check_circulars.py"])
    code = cc.main()
    out = capsys.readouterr().out
    assert code == 2, "an unparseable feed must exit 2, not 0"
    assert "INCONCLUSIVE" in out
    assert "Do NOT read this as confirmation" in out


def test_unreachable_feed_exits_two(cc, monkeypatch, capsys):
    monkeypatch.setattr(cc, "fetch", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["check_circulars.py"])
    code = cc.main()
    assert code == 2
    assert "could not check" in capsys.readouterr().out

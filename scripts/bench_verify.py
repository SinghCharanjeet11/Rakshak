"""Latency benchmark for the deterministic core.

The point is not vanity numbers. `01-architecture.md` positions Rakshak as a verifier that
sits *above* acting agents; if a single-action verdict costs microseconds, an agent can call
it **before** it executes rather than auditing afterwards — still report-only, because
Rakshak returns a verdict and the agent decides. That reframes the product from an audit
tool into the compliance layer a payment agent checks with, and the claim needs a measurement
behind it.

Run:  python scripts/bench_verify.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core.models import Action  # noqa: E402
from app.core.rule_engine import evaluate  # noqa: E402
from app.core.rules_loader import load_pack  # noqa: E402
from app.core.scoring import compute  # noqa: E402

SEED = ROOT / "backend" / "app" / "seed"


def load(name: str) -> list[Action]:
    raw = json.loads((SEED / name).read_text(encoding="utf-8"))
    return [Action.model_validate(a) for a in raw]


def bench(label: str, fn, n: int) -> None:
    fn()  # warm the code paths so the first call's import cost is not measured
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1_000_000)  # microseconds

    samples.sort()
    p50 = statistics.median(samples)
    p99 = samples[int(len(samples) * 0.99)]
    print(
        f"{label:<44} p50 {p50:9.1f}µs   p99 {p99:9.1f}µs   "
        f"({1_000_000 / statistics.mean(samples):,.0f}/s)"
    )


def main() -> None:
    pack = load_pack()
    clean = load("clean_actions.json")
    violating = load("violating_actions.json")
    combined = clean + violating
    one = [violating[2]]  # the Rs 20,000 AFA breach

    print(f"rule-pack {pack.version} · {len(pack.rules)} rules · {len(pack.exemptions)} exemptions\n")

    bench("evaluate() — 1 action", lambda: evaluate(one, pack), 20_000)
    bench("evaluate() — 22 actions", lambda: evaluate(combined, pack), 5_000)
    bench(
        "evaluate() + score — 22 actions",
        lambda: compute(combined, evaluate(combined, pack)),
        5_000,
    )
    bench(
        "full verdict path — 500 actions (budget cap)",
        lambda: compute(combined * 23, evaluate(combined * 23, pack)),
        200,
    )

    print(
        "\nThe verdict path holds no locks, opens no sockets and reads no clock, so these are\n"
        "the real numbers rather than a warm-cache best case. A single-action check is cheap\n"
        "enough to sit in an agent's pre-flight path instead of a nightly audit."
    )


if __name__ == "__main__":
    main()

"""The wall, mechanically enforced — invariant I2, 02-system-design.md Part C.

One of the three tests shown live in the demo. The claim "no language model decides
compliance" is only worth something if something other than good intentions enforces it,
so this walks the AST of every module in `core/` and fails on the first import that could
reach a model, a network, or mutable application state.

If this test ever fails, the architecture's central claim has been broken — do not
"fix" it by adding to the allow-list.
"""

import ast
from pathlib import Path

import pytest

CORE_DIR = Path(__file__).resolve().parent.parent / "app" / "core"

FORBIDDEN_PREFIXES = (
    # the model layer and everything that orchestrates it
    "app.llm",
    "app.orchestration",
    "app.store",
    "app.api",
    "app.config",
    # provider SDKs
    "openai",
    "anthropic",
    "cohere",
    "google.generativeai",
    # network
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "http",
    "socket",
    "websockets",
)


def _module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module)
            elif node.level:  # relative import inside core/ is fine
                names.add(f"app.core.{node.module or ''}")
    return names


def core_modules() -> list[Path]:
    return sorted(p for p in CORE_DIR.glob("*.py") if p.name != "__init__.py")


def test_core_directory_is_not_empty():
    assert core_modules(), "isolation test would vacuously pass with no core modules"


@pytest.mark.parametrize("path", core_modules(), ids=lambda p: p.name)
def test_core_module_imports_nothing_forbidden(path: Path):
    offenders = [
        name
        for name in _module_names(path)
        for prefix in FORBIDDEN_PREFIXES
        if name == prefix or name.startswith(prefix + ".")
    ]
    assert not offenders, (
        f"{path.name} breaks the wall (invariant I2) by importing {offenders}. "
        "The deterministic core must not reach a model, the network, or app state."
    )


BLOCKED_IMPORT_PROBE = """
import sys
from importlib.abc import MetaPathFinder

BLOCKED = ("app.llm", "app.orchestration", "app.store", "app.api",
           "openai", "anthropic", "httpx", "requests")

class Blocker(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == b or fullname.startswith(b + ".") for b in BLOCKED):
            raise ImportError("blocked by isolation probe: " + fullname)
        return None

sys.meta_path.insert(0, Blocker())

import app.core.models
import app.core.run
import app.core.rules_loader
import app.core.rule_engine
import app.core.scoring

print("OK")
"""


def test_core_is_importable_without_the_llm_package():
    """`core/` must still work if the model layer were deleted outright.

    Runs in a subprocess on purpose. Doing this in-process — by reloading modules or
    editing `sys.modules` — rebinds exception classes that other test modules already
    imported, and the resulting failures land in unrelated files.
    """
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-c", BLOCKED_IMPORT_PROBE],
        cwd=CORE_DIR.parent.parent,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"core failed to import in isolation:\n{proc.stderr}"
    assert "OK" in proc.stdout


def _call_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        ast.unparse(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }


@pytest.mark.parametrize("name", ["rule_engine.py", "scoring.py"])
def test_verdict_modules_do_not_read_the_clock_or_random(name: str):
    """A verdict that depends on `now()` or on randomness is not reproducible, which
    would break replay and make the idempotency guarantee a lie.

    Checked against the AST rather than the file text, so the modules stay free to
    *describe* the constraint in their own docstrings.
    """
    path = CORE_DIR / name
    assert "random" not in _module_names(path)

    forbidden = ("datetime.now", "datetime.today", "date.today", "time.time", "random")
    offenders = [c for c in _call_targets(path) if c.endswith(forbidden)]
    assert not offenders, f"{name} reads non-deterministic state: {offenders}"

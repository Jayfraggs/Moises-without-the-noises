#!/usr/bin/env python3
"""
run_tests.py — mwtn unified test runner.

Discovers and runs every test suite in the project:
  - backend/   → pytest  (Python)
  - frontend/  → vitest  (JS/JSX via npm test)
  - electron/  → vitest  (JS via npm test, if configured)

Usage:
  python run_tests.py            # run everything
  python run_tests.py backend    # only backend
  python run_tests.py frontend   # only frontend
  python run_tests.py electron   # only electron

Requires:
  - Python ≥ 3.10 with the backend venv active (or pytest on PATH)
  - Node.js / npm (for frontend + electron suites)

Exit code: 0 if all suites pass, 1 if any fail.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent.resolve()

# ── ANSI colours (disabled when not a TTY or on Windows without VT) ──────────
_USE_COLOUR = sys.stdout.isatty() and os.name != "nt" or (
    os.name == "nt" and os.environ.get("WT_SESSION")  # Windows Terminal supports VT
)

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def green(t: str)  -> str: return _c("32;1", t)
def red(t: str)    -> str: return _c("31;1", t)
def yellow(t: str) -> str: return _c("33;1", t)
def cyan(t: str)   -> str: return _c("36;1", t)
def bold(t: str)   -> str: return _c("1",    t)
def dim(t: str)    -> str: return _c("2",    t)

# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class SuiteResult:
    name: str
    passed: bool
    skipped: bool = False
    skip_reason: str = ""
    duration: float = 0.0
    output: str = ""
    returncode: int = 0

    @property
    def status_label(self) -> str:
        if self.skipped:
            return yellow("SKIP")
        return green("PASS") if self.passed else red("FAIL")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_pytest() -> str | None:
    """Prefer the venv's pytest so the backend deps are available."""
    venv_pytest = HERE / "venv" / "Scripts" / "pytest.exe"  # Windows
    if venv_pytest.exists():
        return str(venv_pytest)
    venv_pytest = HERE / "venv" / "bin" / "pytest"          # Unix
    if venv_pytest.exists():
        return str(venv_pytest)
    return shutil.which("pytest")


def _find_npm() -> str | None:
    if os.name == "nt":
        npm = shutil.which("npm.cmd") or shutil.which("npm")
    else:
        npm = shutil.which("npm")
    return npm


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> tuple[int, str]:
    """Run a subprocess, capture combined stdout+stderr, return (returncode, output)."""
    merged_env = {**os.environ, **(env or {})}
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout


def _count_tests_from_pytest_output(output: str) -> str:
    """Extract the summary line from pytest output, e.g. '14 passed, 2 failed'."""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if "passed" in line or "failed" in line or "error" in line:
            # Strip ANSI codes
            import re
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
            # Strip the leading '=== ' and trailing ' ===' delimiters
            clean = clean.strip("= ").strip()
            return clean
    return ""


def _count_tests_from_vitest_output(output: str) -> str:
    """Extract test counts from vitest output."""
    import re
    # Look for "Tests X passed" or "X failed" lines
    for line in reversed(output.splitlines()):
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if "Tests " in clean and ("passed" in clean or "failed" in clean):
            return clean
        if re.search(r"\d+ (passed|failed|skipped)", clean):
            return clean
    return ""


# ── Suite runners ─────────────────────────────────────────────────────────────

def run_backend() -> SuiteResult:
    name = "backend (pytest)"
    pytest_bin = _find_pytest()

    if not pytest_bin:
        return SuiteResult(name=name, passed=False, skipped=True,
                           skip_reason="pytest not found — activate venv first: .\\activate.ps1")

    backend_dir = HERE / "backend"
    if not backend_dir.is_dir():
        return SuiteResult(name=name, passed=False, skipped=True,
                           skip_reason="backend/ directory not found")

    tests_dir = backend_dir / "tests"
    if not tests_dir.is_dir() or not list(tests_dir.glob("test_*.py")):
        return SuiteResult(name=name, passed=False, skipped=True,
                           skip_reason="no test files found in backend/tests/")

    t0 = time.monotonic()
    rc, output = _run(
        [pytest_bin, "--tb=short", "-v", "--color=yes"],
        cwd=backend_dir,
    )
    duration = time.monotonic() - t0
    summary = _count_tests_from_pytest_output(output)

    return SuiteResult(
        name=name,
        passed=(rc == 0),
        duration=duration,
        output=output,
        returncode=rc,
    )


def run_frontend() -> SuiteResult:
    """
    The frontend is now plain HTML/CSS/JS in frontend/static/ — no build, no npm.
    We validate that the required files exist and are non-empty, and run a
    quick Python-based sanity check on the JS module structure.
    """
    name = "frontend (static file checks)"
    frontend_dir = HERE / "frontend" / "static"

    if not frontend_dir.is_dir():
        return SuiteResult(name=name, passed=False, skipped=True,
                           skip_reason="frontend/static/ not found")

    required = [
        "index.html",
        "js/app.js",
        "js/api.js",
        "js/state.js",
        "js/catalog.js",
        "js/studio.js",
        "js/transport.js",
        "js/import.js",
        "js/settings.js",
        "css/variables.css",
        "css/base.css",
        "css/layout.css",
    ]

    t0 = time.monotonic()
    missing, empty = [], []
    for rel in required:
        p = frontend_dir / rel
        if not p.exists():
            missing.append(rel)
        elif p.stat().st_size < 10:
            empty.append(rel)

    # Check that ES module exports are present in key files
    checks = [
        ("js/app.js",       "import"),
        ("js/state.js",     "export const State"),
        ("js/api.js",       "export const API"),
        ("js/catalog.js",   "export class Catalog"),
        ("js/studio.js",    "export class Studio"),
        ("js/studio.js",    "STEM_ICONS"),
        ("js/studio.js",    "_buildMixer"),
        ("js/studio.js",    "_populateAnalysis"),
        ("js/transport.js", "export class Transport"),
        ("js/import.js",    "export class Import"),
        ("js/settings.js",  "export class Settings"),
        ("js/settings.js",  "_runScan"),
        ("js/settings.js",  "/api/scan"),
    ]
    bad_exports = []
    for rel, marker in checks:
        p = frontend_dir / rel
        if p.exists() and marker not in p.read_text(encoding="utf-8", errors="replace"):
            bad_exports.append(f"{rel} missing '{marker}'")

    duration = time.monotonic() - t0
    lines = []
    passed = True

    if missing:
        passed = False
        lines.append(f"MISSING FILES ({len(missing)}):")
        lines.extend(f"  ✗ {f}" for f in missing)
    if empty:
        passed = False
        lines.append(f"EMPTY FILES ({len(empty)}):")
        lines.extend(f"  ✗ {f}" for f in empty)
    if bad_exports:
        passed = False
        lines.append(f"BAD EXPORTS ({len(bad_exports)}):")
        lines.extend(f"  ✗ {e}" for e in bad_exports)

    if passed:
        found = [r for r in required if (frontend_dir / r).exists()]
        lines.append(f"All {len(found)} required files present and valid.")
        lines.append(f"  index.html: {(frontend_dir / 'index.html').stat().st_size} bytes")
        lines.append(f"  JS modules: {len([r for r in required if r.startswith('js/')])} files")
        lines.append(f"  CSS files:  {len([r for r in required if r.startswith('css/')])} files")

    return SuiteResult(
        name=name,
        passed=passed,
        duration=duration,
        output="\n".join(lines),
        returncode=0 if passed else 1,
    )


def run_electron() -> SuiteResult:
    name = "electron (vitest/jest)"
    npm = _find_npm()

    if not npm:
        return SuiteResult(name=name, passed=False, skipped=True,
                           skip_reason="npm not found")

    electron_dir = HERE / "electron"
    if not electron_dir.is_dir():
        return SuiteResult(name=name, passed=False, skipped=True,
                           skip_reason="electron/ directory not found")

    if not (electron_dir / "node_modules").is_dir():
        return SuiteResult(name=name, passed=False, skipped=True,
                           skip_reason="electron/node_modules missing — run .\\activate.ps1 first")

    # Check package.json has a test script
    pkg_json = electron_dir / "package.json"
    has_test_script = False
    if pkg_json.exists():
        import json
        try:
            scripts = json.loads(pkg_json.read_text()).get("scripts", {})
            has_test_script = "test" in scripts
        except (json.JSONDecodeError, OSError):
            pass

    if not has_test_script:
        test_files = list((electron_dir).rglob("*.test.js")) + list((electron_dir).rglob("*.spec.js"))
        if not test_files:
            return SuiteResult(name=name, passed=True, skipped=True,
                               skip_reason="no test script configured in electron/package.json")

    t0 = time.monotonic()
    rc, output = _run(
        [npm, "test", "--", "--run"],
        cwd=electron_dir,
        env={"CI": "true"},
    )
    duration = time.monotonic() - t0

    return SuiteResult(
        name=name,
        passed=(rc == 0),
        duration=duration,
        output=output,
        returncode=rc,
    )


# ── Reporting ─────────────────────────────────────────────────────────────────

_SUITE_SEP  = "─" * 72
_BLOCK_SEP  = "═" * 72

def _print_suite_header(name: str) -> None:
    print()
    print(cyan(_SUITE_SEP))
    print(cyan(f"  {name}"))
    print(cyan(_SUITE_SEP))


def _print_suite_output(result: SuiteResult) -> None:
    if result.skipped:
        print(f"  {yellow('⚠')}  {dim(result.skip_reason)}")
        return
    if result.output:
        # Indent every output line slightly for readability
        for line in result.output.splitlines():
            print(f"  {line}")


def _print_summary(results: list[SuiteResult], total_duration: float) -> None:
    print()
    print(bold(_BLOCK_SEP))
    print(bold("  TEST SUMMARY"))
    print(bold(_BLOCK_SEP))

    col_w = max(len(r.name) for r in results) + 2
    for r in results:
        dur_str = dim(f"  {r.duration:.1f}s")
        name_str = r.name.ljust(col_w)
        if r.skipped:
            reason = dim(f"  ({r.skip_reason})")
            print(f"  {r.status_label}  {name_str}{dur_str}{reason}")
        else:
            print(f"  {r.status_label}  {name_str}{dur_str}")

    passed  = sum(1 for r in results if r.passed and not r.skipped)
    failed  = sum(1 for r in results if not r.passed and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)

    print()
    parts = []
    if passed:  parts.append(green(f"{passed} passed"))
    if failed:  parts.append(red(f"{failed} failed"))
    if skipped: parts.append(yellow(f"{skipped} skipped"))
    print(f"  {',  '.join(parts)}  {dim(f'in {total_duration:.1f}s')}")
    print(bold(_BLOCK_SEP))
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

SUITES: dict[str, callable] = {
    "backend":  run_backend,
    "frontend": run_frontend,
    "electron": run_electron,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            mwtn unified test runner.
            Runs all test suites (backend, frontend, electron) and prints a summary.
            Pass a suite name to run only that suite.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "suites",
        nargs="*",
        choices=[*SUITES.keys(), []],
        metavar="SUITE",
        help=f"Which suites to run: {', '.join(SUITES)}. Defaults to all.",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Suppress per-suite output; show summary only.",
    )
    args = parser.parse_args()

    to_run = args.suites if args.suites else list(SUITES.keys())
    results: list[SuiteResult] = []
    t_global = time.monotonic()

    print()
    print(bold("mwtn — running test suites: " + ", ".join(to_run)))

    for key in to_run:
        runner = SUITES[key]
        _print_suite_header(key)
        result = runner()
        results.append(result)
        if not args.no_output:
            _print_suite_output(result)

    total_duration = time.monotonic() - t_global
    _print_summary(results, total_duration)

    # If any failed suite has output we haven't shown, print a recap
    if args.no_output:
        for r in results:
            if not r.passed and not r.skipped and r.output:
                print(red(f"\n── {r.name} failure output ──"))
                for line in r.output.splitlines():
                    print(f"  {line}")
                print()

    any_failed = any(not r.passed and not r.skipped for r in results)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())

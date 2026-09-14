"""
INVARIANT 3.4 — LEGACY BARRIER regression tests.

``setup_alpha.py`` is the frozen v1.6.4 skeleton bootstrap. It must never be
able to write its stubs over the v2.0 production codebase, and it must not
mutate the filesystem before deciding whether it is allowed to run.

These tests execute the real script in a subprocess with a hermetic ``HOME``
(so ``TARGET_BASE`` = ``$HOME/Downloads/Projekt_Alpha`` points into a tmp dir)
and assert:

  1. default invocation            -> exit 1, refusal message, ZERO directories created
  2. override flag + clean target  -> exit 0, the historical scaffold is written
  3. override flag + target that
     already holds v2.0 production -> exit 1 (protected even when forced)
  4. the barrier is the first mutation — no partial directory tree on refusal
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = REPO_ROOT / "setup_alpha.py"
OVERRIDE_FLAG = "--i-understand-this-is-the-frozen-v1.6.4-skeleton"


def _run(home: Path, *extra_args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_PRIVATE_KEY", None)
    return subprocess.run(
        [sys.executable, str(SETUP_SCRIPT), *extra_args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_script_exists() -> None:
    assert SETUP_SCRIPT.is_file(), f"{SETUP_SCRIPT} missing"


def test_default_invocation_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    """Frozen by default: exit 1 and NOT ONE directory created."""
    home = tmp_path / "home"
    home.mkdir()

    proc = _run(home)

    assert proc.returncode == 1, f"legacy bootstrap must fail closed, got rc={proc.returncode}\n{proc.stdout}"
    out = proc.stdout + proc.stderr
    assert "EINGEFRORENES Legacy-Skript" in out
    assert "Kraken Pro Execution System v2.0" in out
    # the refusal must point the operator at the real setup path
    assert "README.md" in out

    # ZERO filesystem mutation: the barrier runs before os.makedirs()
    assert not (home / "Downloads").exists(), "barrier must not create directories before refusing"
    assert list(home.iterdir()) == [], f"expected an untouched HOME, found {list(home.iterdir())}"


def test_override_flag_writes_the_historical_scaffold(tmp_path: Path) -> None:
    """With the explicit operator acknowledgement the legacy path still works."""
    home = tmp_path / "home"
    home.mkdir()

    proc = _run(home, OVERRIDE_FLAG)

    assert proc.returncode == 0, f"override run failed rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    target = home / "Downloads" / "Projekt_Alpha"
    assert target.is_dir(), "scaffold root not created"
    assert (target / "app" / "execution" / "M8StateEngine.py").is_file()
    assert "Legacy-Override aktiv" in proc.stdout


def test_override_is_refused_when_target_holds_production_code(tmp_path: Path) -> None:
    """Even forced, the scaffold must not land on a v2.0 installation."""
    home = tmp_path / "home"
    target = home / "Downloads" / "Projekt_Alpha"
    (target / "app").mkdir(parents=True)
    (target / "app" / "main.py").write_text("# real v2.0 backend\n", encoding="utf-8")

    proc = _run(home, OVERRIDE_FLAG)

    assert proc.returncode == 1, f"must refuse to overwrite production code\n{proc.stdout}"
    assert "v2.0-Produktionscode" in proc.stdout + proc.stderr
    # the production marker file must be untouched
    assert (target / "app" / "main.py").read_text(encoding="utf-8") == "# real v2.0 backend\n"
    assert not (target / "app" / "execution").exists(), "no stub directory may be created"


def test_override_is_refused_when_target_is_a_git_repository(tmp_path: Path) -> None:
    """`.git` alone is enough to identify a live checkout and refuse."""
    home = tmp_path / "home"
    target = home / "Downloads" / "Projekt_Alpha"
    (target / ".git").mkdir(parents=True)

    proc = _run(home, OVERRIDE_FLAG)

    assert proc.returncode == 1, f"must refuse to write into a git checkout\n{proc.stdout}"
    assert ".git" in proc.stdout + proc.stderr


def test_barrier_precedes_directory_creation_in_source_order() -> None:
    """Static guard: _legacy_barrier() must be called before the first makedirs.

    Protects against someone re-introducing eager directory creation above the
    barrier (the exact defect that made the old guard a no-op).
    """
    source = SETUP_SCRIPT.read_text(encoding="utf-8")

    barrier_call = source.index("_legacy_barrier()")
    first_makedirs = source.index("os.makedirs(")
    assert barrier_call < first_makedirs, (
        "_legacy_barrier() must run before any os.makedirs() call"
    )

    # the stale, wrong-path guard must stay deleted
    assert "DEPRECATION GUARD" not in source


def test_production_repository_is_intact_after_barrier_runs(tmp_path: Path) -> None:
    """Running the frozen script must not touch the real production modules."""
    before = {
        p: p.stat().st_mtime_ns
        for p in REPO_ROOT.glob("app/**/*.py")
    }
    assert before, "no production modules found"

    proc = _run(tmp_path)
    assert proc.returncode == 1

    after = {p: p.stat().st_mtime_ns for p in REPO_ROOT.glob("app/**/*.py")}
    assert before == after, "the legacy bootstrap modified production code"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

#!/usr/bin/env python3
"""Audit the MySQL acceptance list against the code that actually branches on dialect.

``MYSQL_PYTEST_TARGETS`` is hand-maintained, so nothing notices when an
integration file starts exercising dialect-branched app code and is never added
to the list -- which is precisely how the automations API and the dashboard-user
race stayed invisible until they were run against MySQL by hand.

This tool reports every integration test file whose *direct* imports pull in an
app module containing a dialect branch, and says whether that file is in the
list. Files that deliberately stay out are listed in
``tools/mysql_target_exclusions.txt`` (``path<TAB>reason``), and ``--check``
fails only for unexplained gaps, so the exclusion itself is reviewed code.

Usage:
    python tools/mysql_target_audit.py            # report everything noticed
    python tools/mysql_target_audit.py --check    # exit 1 on an unexplained gap
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TESTS = ROOT / "tests" / "integration"
MAKEFILE = ROOT / "Makefile"
EXCLUSIONS = ROOT / "tools" / "mysql_target_exclusions.txt"

#: What a module looks like when it decides something per dialect.
BRANCH_SIGNALS = ("is_mysql(", "MYSQL_DIALECT_NAMES", "dialect_name(", "same_table_subquery(")

#: Fixtures/markers that mean "this file drives the configured test database".
DATABASE_MARKERS = ("db_setup", "async_client", "app_instance", "SessionLocal", "CODEX_LB_TEST_DATABASE_URL")


def mysql_targets() -> set[str]:
    """Paths (without ``::node`` suffixes) in the Makefile's MySQL list."""

    text = MAKEFILE.read_text()
    match = re.search(r"^MYSQL_PYTEST_TARGETS :=(.*?)(?=\n[A-Z_]+ :=|\n[a-z-]+:)", text, re.S | re.M)
    if match is None:
        raise SystemExit("MYSQL_PYTEST_TARGETS not found in the Makefile")
    entries = re.findall(r"tests/[\w/\.]+\.py(?:::\w+)?", match.group(1))
    unique = {entry.split("::", 1)[0] for entry in entries}
    return unique, len(entries)


def split_exclusions() -> dict[str, str]:
    """Documented exclusions: path -> reason (blank lines and # comments skipped)."""

    if not EXCLUSIONS.exists():
        return {}
    excluded: dict[str, str] = {}
    for line in EXCLUSIONS.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        path, _, reason = stripped.partition("\t")
        excluded[path.strip()] = reason.strip()
    return excluded


def branching_modules() -> dict[str, list[str]]:
    """App modules that branch on dialect, with the signals each one uses."""

    modules: dict[str, list[str]] = {}
    for path in sorted(APP.rglob("*.py")):
        source = path.read_text(errors="replace")
        found = [signal for signal in BRANCH_SIGNALS if signal in source]
        if found:
            modules[str(path.relative_to(ROOT))] = found
    return modules


def imported_app_modules(test_file: Path) -> set[str]:
    """App module paths a test file imports directly (``from app.x import y``)."""

    tree = ast.parse(test_file.read_text(errors="replace"), filename=str(test_file))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            imported.add(module_to_path(node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    imported.add(module_to_path(alias.name))
    return {path for path in imported if path}


def module_to_path(module: str) -> str:
    """``app.modules.proxy.sticky_repository`` -> ``app/modules/proxy/sticky_repository.py``."""

    return module.replace(".", "/") + ".py"


def uses_configured_database(test_file: Path) -> bool:
    """True when the file drives the configured test database (vs. self-contained)."""

    source = test_file.read_text(errors="replace")
    return any(marker in source for marker in DATABASE_MARKERS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 when an undocumented gap exists")
    args = parser.parse_args()

    targets, entries = mysql_targets()
    excluded = split_exclusions()
    branches = branching_modules()

    in_list: list[tuple[str, bool]] = []
    candidates: list[tuple[str, list[str]]] = []
    documented: list[tuple[str, list[str]]] = []
    incidental: list[str] = []
    for test_file in sorted(TESTS.glob("test_*.py")):
        relative = str(test_file.relative_to(ROOT))
        reachable = sorted(imported_app_modules(test_file) & set(branches))
        if not reachable:
            continue
        signals = sorted({signal for module in reachable for signal in branches[module]})
        drives_db = uses_configured_database(test_file)
        if relative in targets:
            in_list.append((relative, drives_db))
        elif relative in excluded:
            documented.append((relative, signals))
        elif drives_db:
            candidates.append((relative, signals))
        else:
            incidental.append(relative)

    print(f"MySQL list entries: {entries} ({len(targets)} unique files)")
    print(f"app modules that branch on dialect: {len(branches)}")
    print()
    print(f"IN the list ({len(in_list)}):")
    for path, drives_db in in_list:
        print(f"  {path}{'' if drives_db else '   (does not drive the test database)'}")
    print()
    print(f"EXCLUDED with a documented reason ({len(documented)}):")
    for path, _ in documented:
        print(f"  {path}: {excluded[path]}")
    print()
    print(f"CANDIDATES: drive the test database, exercise dialect branches, not in the list ({len(candidates)}):")
    for path, signals in candidates:
        print(f"  {path}  [{', '.join(signals)}]")
    print()
    print(f"incidental (import a branching module but never drive the database) ({len(incidental)}):")
    for path in incidental:
        print(f"  {path}")
    if args.check and candidates:
        print()
        print("Run each candidate against MySQL, then add it to MYSQL_PYTEST_TARGETS,")
        print(f"or document it in {EXCLUSIONS.relative_to(ROOT)} with its reason.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

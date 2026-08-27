#!/usr/bin/env python3
"""
Environment check and setup for the Engineering Continuity Platform.

    python doctor.py            check everything, report, change nothing
    python doctor.py --fix      install what is missing and create the tables
    python doctor.py --fix --yes    same, without the confirmation prompt

Checks the Python version, the packages, the database, the schema, whether the
scoring engine has been run, and whether Confluence is configured and synced.
Every failure prints the exact command that fixes it.

This file deliberately imports nothing outside the standard library at module
level -- it has to run and give useful advice on a machine where none of the
project's dependencies are installed yet.
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

_SYMBOL = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[FAIL]"}

MIN_PYTHON = (3, 10)

# import name -> (pip requirement, what breaks without it)
REQUIRED_PACKAGES = {
    "sqlalchemy": ("SQLAlchemy>=2.0.0", "database access - nothing runs without it"),
    "alembic": ("alembic>=1.13.0", "database migrations"),
    "dotenv": ("python-dotenv>=1.0.0", "reading .env"),
    "fastapi": ("fastapi", "the HTTP API"),
    "uvicorn": ("uvicorn", "running the API server"),
    "httpx": ("httpx>=0.27.0", "talking to the Confluence API"),
}

OPTIONAL_PACKAGES = {
    "psycopg2": ("psycopg2-binary>=2.9.0", "PostgreSQL support (SQLite works without it)"),
    "reportlab": ("reportlab>=4.0.0", "PDF export (Markdown still works)"),
    "docx": ("python-docx>=1.1.0", "DOCX export (Markdown still works)"),
    "pytest": ("pytest>=8.0.0", "running the test suite"),
}

CORE_TABLES = ["employees", "capabilities", "modules", "services", "evidence_records", "capability_scores"]
RAG_TABLES = ["confluence_pages", "confluence_sections", "confluence_page_capabilities"]


class Report:
    """Collects results so the summary can be printed at the end."""

    def __init__(self):
        self.rows: list[tuple[str, str, str, str | None]] = []

    def add(self, status: str, name: str, detail: str = "", fix: str | None = None) -> None:
        self.rows.append((status, name, detail, fix))
        line = "%s %-34s %s" % (_SYMBOL[status], name, detail)
        print(line.rstrip())
        if fix and status != OK:
            print("        fix: %s" % fix)

    def section(self, title: str) -> None:
        print()
        print(title)
        print("-" * 72)

    def count(self, status: str) -> int:
        return sum(1 for row in self.rows if row[0] == status)

    @property
    def failed(self) -> bool:
        return self.count(FAIL) > 0


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------


def check_python(report: Report) -> None:
    report.section("Python")
    version = sys.version_info
    text = "%d.%d.%d" % (version.major, version.minor, version.micro)
    if version[:2] >= MIN_PYTHON:
        report.add(OK, "Python version", "%s at %s" % (text, sys.executable))
    else:
        report.add(
            FAIL, "Python version",
            "%s - need %d.%d or newer" % (text, *MIN_PYTHON),
            "install a newer Python and re-run this script with it",
        )


def _installed(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def check_packages(report: Report, fix: bool, assume_yes: bool) -> None:
    report.section("Python packages")

    missing_required = []
    for module, (requirement, why) in REQUIRED_PACKAGES.items():
        if _installed(module):
            report.add(OK, module, why)
        else:
            missing_required.append(requirement)
            report.add(FAIL, module, "missing - %s" % why,
                       "pip install %s" % requirement)

    missing_optional = []
    for module, (requirement, why) in OPTIONAL_PACKAGES.items():
        if _installed(module):
            report.add(OK, module, why)
        else:
            missing_optional.append(requirement)
            report.add(WARN, module, "missing - %s" % why,
                       "pip install %s" % requirement)

    to_install = missing_required + missing_optional
    if to_install and fix:
        _install(report, to_install, assume_yes)
    elif to_install:
        report.add(
            WARN, "install missing packages", "%d package(s) to install" % len(to_install),
            "python doctor.py --fix   (or: pip install -r requirements.txt)",
        )


def _install(report: Report, requirements: list[str], assume_yes: bool) -> None:
    print()
    print("About to install: %s" % ", ".join(requirements))
    if not assume_yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            report.add(WARN, "package install", "skipped by user")
            return

    command = [sys.executable, "-m", "pip", "install", *requirements]
    print("Running: %s" % " ".join(command))
    result = subprocess.run(command)
    if result.returncode == 0:
        report.add(OK, "package install", "installed %d package(s)" % len(requirements))
    else:
        report.add(FAIL, "package install", "pip exited %d" % result.returncode,
                   "run the pip command above by hand to see the error")


def check_env_file(report: Report, fix: bool) -> None:
    report.section("Configuration")

    env_path = BASE_DIR / ".env"
    example_path = BASE_DIR / ".env.example"

    if env_path.exists():
        report.add(OK, ".env", str(env_path))
        return

    if fix and example_path.exists():
        shutil.copyfile(example_path, env_path)
        report.add(WARN, ".env", "created from .env.example - edit it with real values",
                   "open %s and set your database password" % env_path)
        return

    report.add(
        WARN, ".env", "not found - defaults will be used",
        "copy .env.example to .env and fill it in",
    )


def _database_url() -> str | None:
    try:
        from backend.config import DATABASE_URL
        return DATABASE_URL
    except Exception:
        return os.environ.get("DATABASE_URL")


def _redact(url: str) -> str:
    """Hide the password in a connection URL before printing it."""
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return "%s://%s:***@%s" % (scheme, user, host)


def check_database(report: Report, fix: bool) -> dict:
    report.section("Database")
    state = {"connected": False, "tables": set()}

    if not _installed("sqlalchemy"):
        report.add(FAIL, "database", "SQLAlchemy not installed - cannot check",
                   "python doctor.py --fix")
        return state

    url = _database_url()
    if not url:
        report.add(FAIL, "DATABASE_URL", "could not be resolved",
                   "set DATABASE_URL in .env")
        return state

    report.add(OK, "connection string", _redact(url))

    if url.startswith("postgresql") and not _installed("psycopg2"):
        report.add(FAIL, "psycopg2", "required for a postgresql:// URL",
                   "pip install psycopg2-binary   (or use DATABASE_URL=sqlite:///fallback.db)")
        return state

    from sqlalchemy import create_engine, inspect

    try:
        engine = create_engine(url)
        with engine.connect() as connection:
            inspector = inspect(connection)
            state["tables"] = set(inspector.get_table_names())
        state["connected"] = True
        report.add(OK, "connection", "reachable, %d table(s)" % len(state["tables"]))
    except Exception as exc:
        message = str(exc).splitlines()[0][:90]
        report.add(
            FAIL, "connection", message,
            "start PostgreSQL and check the password in .env, or use "
            "DATABASE_URL=sqlite:///fallback.db for a local run",
        )
        return state

    _check_tables(report, state, fix, url)
    return state


def _check_tables(report: Report, state: dict, fix: bool, url: str) -> None:
    tables = state["tables"]

    missing_core = [t for t in CORE_TABLES if t not in tables]
    if missing_core:
        report.add(FAIL, "core schema", "missing: %s" % ", ".join(missing_core),
                   "alembic upgrade head")
    else:
        report.add(OK, "core schema", "all %d core tables present" % len(CORE_TABLES))

    missing_rag = [t for t in RAG_TABLES if t not in tables]
    if not missing_rag:
        report.add(OK, "RAG schema", "all %d Confluence tables present" % len(RAG_TABLES))
        return

    if fix:
        _create_tables(report, url)
        return

    report.add(FAIL, "RAG schema", "missing: %s" % ", ".join(missing_rag),
               "alembic upgrade head   (or: python doctor.py --fix)")


def _create_tables(report: Report, url: str) -> None:
    """Create any missing tables from the models. Never drops or alters."""
    try:
        from sqlalchemy import create_engine
        from backend.database import Base
        import backend.models          # noqa: F401  registers core + raw tables
        import backend.rag.models      # noqa: F401  registers the RAG tables

        Base.metadata.create_all(bind=create_engine(url))
        report.add(OK, "RAG schema", "tables created")
    except Exception as exc:
        report.add(FAIL, "RAG schema", str(exc).splitlines()[0][:90],
                   "alembic upgrade head")


def check_data(report: Report, state: dict) -> None:
    if not state["connected"]:
        return

    report.section("Data")
    url = _database_url()
    from sqlalchemy import create_engine, text

    engine = create_engine(url)

    def count(table: str) -> int | None:
        if table not in state["tables"]:
            return None
        try:
            with engine.connect() as connection:
                return connection.execute(text("SELECT COUNT(*) FROM %s" % table)).scalar()
        except Exception:
            return None

    employees = count("employees")
    capabilities = count("capabilities")
    evidence = count("evidence_records")
    scores = count("capability_scores")

    if employees:
        report.add(OK, "taxonomy loaded",
                   "%s employees, %s capabilities" % (employees, capabilities))
    else:
        report.add(WARN, "taxonomy loaded", "no employees found",
                   "python -m backend.seed")

    if evidence:
        report.add(OK, "evidence ingested", "%s records" % evidence)
    else:
        report.add(WARN, "evidence ingested", "no evidence records",
                   "python -m backend.run_pipeline")

    if scores:
        report.add(OK, "scoring engine has run", "%s capability scores" % scores)
    else:
        report.add(
            WARN, "scoring engine has run", "no capability scores",
            "python -m backend.run_engine   (the RAG needs these to find gaps)",
        )

    pages = count("confluence_pages")
    sections = count("confluence_sections")
    if pages:
        report.add(OK, "Confluence synced", "%s pages, %s sections" % (pages, sections))
    else:
        report.add(
            WARN, "Confluence synced", "no pages indexed",
            "python -m backend.run_rag sync   (packages still generate without it, "
            "but with no supporting documentation)",
        )


def check_confluence(report: Report) -> None:
    report.section("Confluence")
    try:
        from backend.rag import config as rag_config
    except Exception as exc:
        report.add(WARN, "RAG config", str(exc).splitlines()[0][:80])
        return

    if rag_config.confluence_is_configured():
        report.add(OK, "credentials", rag_config.CONFLUENCE_BASE_URL)
        spaces = rag_config.CONFLUENCE_SPACE_KEYS or "all readable spaces"
        report.add(OK, "spaces", str(spaces))
        return

    unset = rag_config.unset_confluence_settings()
    placeholders = rag_config.placeholder_confluence_settings()

    if placeholders:
        # Worth calling out separately: a placeholder looks configured, so
        # without this the first symptom is an HTTP 401 that reads as a bad
        # token rather than an unedited file.
        report.add(
            WARN, "credentials",
            "still the .env.example example values: %s" % ", ".join(placeholders),
            "edit .env and replace them with your real Atlassian site, "
            "account email and API token - see INSTRUCTIONS.md section 3",
        )
    if unset:
        report.add(
            WARN, "credentials", "not set: %s" % ", ".join(unset),
            "add them to .env - see INSTRUCTIONS.md section 3",
        )


def check_engine_integration(report: Report) -> None:
    """The RAG borrows a few engine internals; report which resolved."""
    report.section("Engine integration")
    try:
        from backend.rag.compat import engine_status
    except Exception as exc:
        report.add(WARN, "engine compat", str(exc).splitlines()[0][:80])
        return

    labels = {
        "band_for_score": "coverage bands",
        "tokenize": "text tokenizing",
        "keyword_overlap": "term overlap",
        "label_aliases": "label aliases",
    }
    for key, found in engine_status().items():
        if found:
            report.add(OK, labels.get(key, key), "using the engine's own implementation")
        else:
            report.add(WARN, labels.get(key, key), "engine function not found, using fallback",
                       "harmless, but check backend/engine/ was not refactored unexpectedly")


def check_frontend(report: Report) -> None:
    report.section("Frontend (optional)")
    node = shutil.which("node")
    npm = shutil.which("npm") or shutil.which("npm.cmd")

    if node:
        try:
            version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
            report.add(OK, "node", version)
        except Exception:
            report.add(OK, "node", node)
    else:
        report.add(WARN, "node", "not found - only needed for the React dashboard",
                   "install Node 18+ from nodejs.org")

    if npm:
        modules = BASE_DIR / "frontend" / "node_modules"
        if modules.exists():
            report.add(OK, "frontend deps", "node_modules present")
        else:
            report.add(WARN, "frontend deps", "not installed",
                       "cd frontend && npm install")
    else:
        report.add(WARN, "npm", "not found")


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check (and optionally set up) this project's environment.",
    )
    parser.add_argument("--fix", action="store_true",
                        help="Install missing packages and create missing tables.")
    parser.add_argument("--yes", action="store_true",
                        help="Do not prompt before installing.")
    args = parser.parse_args(argv)

    print("=" * 72)
    print("Engineering Continuity Platform - environment check")
    print("=" * 72)
    if args.fix:
        print("Running in --fix mode: missing packages and tables will be created.")

    report = Report()

    check_python(report)
    check_packages(report, args.fix, args.yes)

    # Re-check after a --fix install so later checks see the new packages.
    if args.fix:
        importlib.invalidate_caches()

    check_env_file(report, args.fix)
    state = check_database(report, args.fix)
    check_data(report, state)
    check_confluence(report)
    check_engine_integration(report)
    check_frontend(report)

    print()
    print("=" * 72)
    print("%d ok, %d warning(s), %d failure(s)"
          % (report.count(OK), report.count(WARN), report.count(FAIL)))

    if report.failed:
        print()
        print("Blocking problems:")
        for status, name, detail, fix in report.rows:
            if status == FAIL:
                print("  - %s: %s" % (name, detail))
                if fix:
                    print("      %s" % fix)
        print()
        print("Re-run with --fix to attempt automatic setup.")
    elif report.count(WARN):
        print("Nothing blocking. Warnings above are optional or not-yet-done steps.")
    else:
        print("Everything is ready.")

    print("=" * 72)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

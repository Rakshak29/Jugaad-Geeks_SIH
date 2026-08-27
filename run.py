#!/usr/bin/env python3
"""
One command to check, install, and run the whole app.

    python run.py                 check, install anything missing, start both servers
    python run.py --check         check only, start nothing
    python run.py --backend-only  API only
    python run.py --frontend-only dashboard only
    python run.py --kill-ports    free ports 8000/5173 first, then start
    python run.py --no-install    fail on anything missing instead of installing it
    python run.py --yes           never prompt

Ctrl+C stops both servers cleanly.

Environment checking is delegated to doctor.py rather than duplicated, so
there is one place that knows what this project needs.

Imports nothing outside the standard library at module level -- it has to run
on a machine where the project's dependencies are not installed yet.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

# The frontend hardcodes http://localhost:8000 in src/services/api.js, so the
# backend cannot simply move to a free port -- the dashboard would load but
# show nothing. A conflict here has to be resolved, not worked around.
BACKEND_PORT = 8000
FRONTEND_PORT = 5173

_STOP = threading.Event()
_PROCESSES: list[subprocess.Popen] = []


def say(message: str = "") -> None:
    print(message, flush=True)


def rule(title: str = "") -> None:
    say()
    say("=" * 70)
    if title:
        say(title)
        say("=" * 70)


# ---------------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------------


def check_environment(install: bool, assume_yes: bool) -> bool:
    """Run doctor.py, optionally letting it install and create what is missing."""
    rule("1/4  Environment")

    command = [sys.executable, str(BASE_DIR / "doctor.py")]
    if install:
        command.append("--fix")
        if assume_yes:
            command.append("--yes")

    result = subprocess.run(command, cwd=str(BASE_DIR))

    if result.returncode == 0:
        return True

    say()
    say("Environment check failed. Fix the problems listed above and re-run.")
    if not install:
        say("Or drop --no-install and let this script install what is missing.")
    return False


def check_frontend_dependencies(install: bool, assume_yes: bool) -> bool:
    """Install node_modules if it is absent."""
    rule("2/4  Frontend dependencies")

    if not FRONTEND_DIR.exists():
        say("[warn] no frontend/ directory - skipping")
        return True

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        say("[FAIL] npm not found on PATH.")
        say("       Install Node 18+ from https://nodejs.org and re-run,")
        say("       or use --backend-only to run just the API.")
        return False

    if (FRONTEND_DIR / "node_modules").exists():
        say("[ ok ] node_modules present")
        return True

    if not install:
        say("[FAIL] node_modules missing. Run: cd frontend && npm install")
        return False

    if not assume_yes:
        say("frontend/node_modules is missing.")
        answer = input("Run 'npm install' now? [Y/n] ").strip().lower()
        if answer in ("n", "no"):
            say("[FAIL] cannot start the dashboard without its dependencies")
            return False

    say("Running npm install (this takes a minute the first time)...")
    result = subprocess.run([npm, "install"], cwd=str(FRONTEND_DIR))
    if result.returncode != 0:
        say("[FAIL] npm install failed - see the output above")
        return False

    say("[ ok ] frontend dependencies installed")
    return True


# ---------------------------------------------------------------------------
# ports
# ---------------------------------------------------------------------------


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pids_on_port(port: int) -> list[int]:
    """Best-effort lookup of what is holding a port. Never raises."""
    pids: set[int] = set()
    try:
        if os.name == "nt":
            output = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[3].upper() == "LISTENING":
                    if parts[1].endswith(":%d" % port):
                        pids.add(int(parts[4]))
        else:
            output = subprocess.run(
                ["lsof", "-ti", "tcp:%d" % port, "-sTCP:LISTEN"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            for line in output.split():
                pids.add(int(line))
    except Exception:
        pass
    return sorted(pids)


def free_port(port: int) -> bool:
    """Stop whatever is listening on a port."""
    pids = pids_on_port(port)
    if not pids:
        return port_is_free(port)

    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=15)
            else:
                os.kill(pid, signal.SIGKILL)
            say("       stopped PID %d" % pid)
        except Exception as exc:
            say("       could not stop PID %d: %s" % (pid, exc))

    time.sleep(1.5)
    return port_is_free(port)


def check_ports(wanted: list[int], kill: bool) -> bool:
    rule("3/4  Ports")
    ok = True

    for port in wanted:
        if port_is_free(port):
            say("[ ok ] port %d is free" % port)
            continue

        pids = pids_on_port(port)
        detail = (" (PID %s)" % ", ".join(str(p) for p in pids)) if pids else ""

        if kill:
            say("[warn] port %d is in use%s - stopping it" % (port, detail))
            if free_port(port):
                say("[ ok ] port %d is now free" % port)
                continue
            say("[FAIL] port %d is still in use" % port)
            ok = False
            continue

        say("[FAIL] port %d is already in use%s" % (port, detail))
        if port == BACKEND_PORT:
            # Moving the backend is not an option: the dashboard would load
            # but stay empty, which is a far more confusing failure.
            say("       The dashboard expects the API on port %d "
                "(hardcoded in frontend/src/services/api.js)." % BACKEND_PORT)
        say("       Re-run with --kill-ports to stop whatever is holding it.")
        ok = False

    return ok


# ---------------------------------------------------------------------------
# processes
# ---------------------------------------------------------------------------


def child_environment() -> dict:
    env = os.environ.copy()
    # backend/run_engine.py and friends print emoji. Windows terminals default
    # to cp1252, which cannot encode them, and the process dies with
    # UnicodeEncodeError. Forcing UTF-8 avoids that without touching the code.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def start_backend() -> subprocess.Popen:
    command = [
        sys.executable, "-m", "uvicorn", "backend.main:app",
        "--reload", "--port", str(BACKEND_PORT),
    ]
    return subprocess.Popen(
        command, cwd=str(BASE_DIR), env=child_environment(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )


def start_frontend() -> subprocess.Popen:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    return subprocess.Popen(
        [npm, "run", "dev"], cwd=str(FRONTEND_DIR), env=child_environment(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )


def pump(process: subprocess.Popen, label: str) -> None:
    """Forward a child's output with a prefix so two logs stay readable."""
    try:
        for line in process.stdout:
            if _STOP.is_set():
                break
            say("%-9s| %s" % (label, line.rstrip()))
    except Exception:
        pass


def wait_until_up(port: int, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _STOP.is_set():
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1.0)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def stop_all() -> None:
    _STOP.set()
    for process in _PROCESSES:
        if process.poll() is not None:
            continue
        try:
            process.terminate()
        except Exception:
            pass

    deadline = time.time() + 8
    for process in _PROCESSES:
        remaining = max(0.0, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python run.py",
        description="Check, install and run the Engineering Continuity Platform.",
    )
    parser.add_argument("--check", action="store_true", help="Check only; start nothing.")
    parser.add_argument("--backend-only", action="store_true", help="Start only the API.")
    parser.add_argument("--frontend-only", action="store_true", help="Start only the dashboard.")
    parser.add_argument("--kill-ports", action="store_true",
                        help="Stop whatever is holding the ports, then start.")
    parser.add_argument("--no-install", action="store_true",
                        help="Fail on anything missing instead of installing it.")
    parser.add_argument("--yes", action="store_true", help="Never prompt.")
    args = parser.parse_args(argv)

    if args.backend_only and args.frontend_only:
        say("--backend-only and --frontend-only are mutually exclusive.")
        return 2

    want_backend = not args.frontend_only
    want_frontend = not args.backend_only
    install = not args.no_install

    rule("Engineering Continuity Platform")
    say("Working directory: %s" % BASE_DIR)

    if not check_environment(install, args.yes):
        return 1

    if want_frontend and not check_frontend_dependencies(install, args.yes):
        return 1

    if args.check:
        rule("Check complete")
        say("Everything needed is present. Run 'python run.py' to start the app.")
        return 0

    wanted_ports = ([BACKEND_PORT] if want_backend else []) + \
                   ([FRONTEND_PORT] if want_frontend else [])
    if not check_ports(wanted_ports, args.kill_ports):
        return 1

    rule("4/4  Starting")

    try:
        if want_backend:
            say("Starting API on http://localhost:%d ..." % BACKEND_PORT)
            backend = start_backend()
            _PROCESSES.append(backend)
            threading.Thread(target=pump, args=(backend, "backend"), daemon=True).start()

            if not wait_until_up(BACKEND_PORT):
                say()
                say("[FAIL] the API did not come up - see the backend output above.")
                stop_all()
                return 1
            say("[ ok ] API is up")

        if want_frontend:
            say("Starting dashboard on http://localhost:%d ..." % FRONTEND_PORT)
            frontend = start_frontend()
            _PROCESSES.append(frontend)
            threading.Thread(target=pump, args=(frontend, "frontend"), daemon=True).start()

            if not wait_until_up(FRONTEND_PORT, timeout=90):
                say()
                say("[FAIL] the dashboard did not come up - see the frontend output above.")
                stop_all()
                return 1
            say("[ ok ] dashboard is up")

        rule("Running")
        if want_frontend:
            say("  Dashboard : http://localhost:%d" % FRONTEND_PORT)
        if want_backend:
            say("  API       : http://localhost:%d" % BACKEND_PORT)
            say("  API docs  : http://localhost:%d/docs" % BACKEND_PORT)
        say()
        say("  Press Ctrl+C to stop.")
        say("=" * 70)
        say()

        # Exit as soon as either server dies -- a half-running app is a
        # confusing state to leave someone staring at.
        while not _STOP.is_set():
            for process in _PROCESSES:
                if process.poll() is not None:
                    say()
                    say("A server exited (code %s). Shutting the other one down."
                        % process.returncode)
                    stop_all()
                    return 1
            time.sleep(0.5)

    except KeyboardInterrupt:
        say()
        say("Stopping...")
    finally:
        stop_all()

    say("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

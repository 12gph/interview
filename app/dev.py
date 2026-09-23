#!/usr/bin/env python3
"""Start both halves of the Variant PDP app with one command.

Standard library only, on purpose. The obvious alternative is an npm package such as
`concurrently`, which would add a dependency to the frontend and a second toolchain to
understand; Python is already required for the backend, so this costs nothing that is
not already installed.

    python dev.py              # start both servers
    python dev.py --install    # install whatever is missing, then start

Dependencies are checked before anything is started. Without `--install` a missing
dependency is reported together with the exact command that fixes it -- silently
spending minutes on the network the first time someone runs this is worse than asking.
The check itself costs two `is_dir()` calls once the environment exists.

Ctrl+C stops both servers. If either one exits on its own -- a port already in use, a
compile error -- the other is shut down too, so a failure never leaves a half-running
stack behind.

Deliberately no `--reload`: reload spawns a supervising parent and a worker child per
server, and a launcher whose whole job is clean lifecycle management is the wrong place
to add a process tree to untangle.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR / "backend"
FRONTEND_DIR = APP_DIR / "frontend"

BACKEND_VENV = BACKEND_DIR / ".venv"
FRONTEND_MODULES = FRONTEND_DIR / "node_modules"

BACKEND_PORT = 8000
FRONTEND_PORT = 5173

Processes = list[tuple[str, "subprocess.Popen[bytes]"]]


# --------------------------------------------------------------------------- commands


def npm_executable() -> str:
    """npm is a shell script on Windows, so the .cmd shim has to be named explicitly."""
    return "npm.cmd" if os.name == "nt" else "npm"


def _venv_bin(name: str) -> Path:
    """Path to an executable inside the backend virtualenv, per platform."""
    if os.name == "nt":
        return BACKEND_VENV / "Scripts" / f"{name}.exe"
    return BACKEND_VENV / "bin" / name


def _venv_python() -> Path:
    if os.name == "nt":
        return BACKEND_VENV / "Scripts" / "python.exe"
    return BACKEND_VENV / "bin" / "python"


def _venv_python_hint() -> str:
    """The venv interpreter as a path relative to backend/, for copy-pasteable advice.

    An absolute path would work too, but the reader is told to `cd app/backend` first,
    and a relative one keeps the command valid if they run it from a different checkout.
    """
    if os.name == "nt":
        return r".venv\Scripts\python"
    return ".venv/bin/python"


def backend_command() -> list[str]:
    """Prefer `uv run`, fall back to the venv's own uvicorn.

    `uv` looks after the environment, so it is the better default; the fallback keeps
    the script working for anyone who set the project up with plain pip and then
    prefers not to depend on uv being on PATH.
    """
    uv = shutil.which("uv")
    if uv is not None:
        return [
            uv,
            "run",
            "--project",
            str(BACKEND_DIR),
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        ]

    uvicorn = _venv_bin("uvicorn")
    if uvicorn.exists():
        return [
            str(uvicorn),
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        ]

    raise SystemExit(
        "Found a backend virtualenv but no uvicorn inside it. Re-run "
        "`python dev.py --install`, or see the setup section of the repository README."
    )


def frontend_command() -> list[str]:
    return [npm_executable(), "run", "dev", "--", "--port", str(FRONTEND_PORT)]


# ----------------------------------------------------------------------- dependencies


def missing_dependencies() -> list[str]:
    """Which halves cannot start yet, in the order the README introduces them.

    Presence of the environment directory is the whole test. Resolving the dependency
    graph ourselves would duplicate the package managers and still be less accurate.
    """
    missing = []
    if not BACKEND_VENV.is_dir():
        missing.append("backend")
    if not FRONTEND_MODULES.is_dir():
        missing.append("frontend")
    return missing


def dependency_report(missing: list[str]) -> str:
    """The exact commands that fix each missing half, spelled for this platform.

    Paths are relative to the repository root, which is where anyone reading this will
    be standing -- `dev.py` lives one level below it.
    """
    lines: list[str] = ["[dev] dependencies are not installed yet:", ""]

    if "backend" in missing:
        lines.append(f"[dev]   backend  -- {BACKEND_VENV} not found")
        lines.append("[dev]     with uv:  cd app/backend && uv sync")
        lines.append(
            "[dev]     no uv:    cd app/backend && python -m venv .venv"
            f" && {_venv_python_hint()} -m pip install -e . --group dev"
        )
        lines.append("")

    if "frontend" in missing:
        lines.append(f"[dev]   frontend -- {FRONTEND_MODULES} not found")
        lines.append("[dev]     cd app/frontend && npm install")
        lines.append("")

    lines.append("[dev] or re-run this script with --install to do it here.")
    return "\n".join(lines)


def install_dependencies(missing: list[str]) -> None:
    """Install whichever halves are missing.

    A non-zero exit stops the script: starting the stack on top of a half-finished
    install would only move the failure to somewhere less obvious.
    """
    if "backend" in missing:
        uv = shutil.which("uv")
        if uv is not None:
            print("[dev] installing backend dependencies: uv sync", flush=True)
            subprocess.run([uv, "sync"], cwd=str(BACKEND_DIR), check=True)
        else:
            print("[dev] uv not found; falling back to venv + pip", flush=True)
            subprocess.run([sys.executable, "-m", "venv", str(BACKEND_VENV)], check=True)
            print(
                "[dev] installing backend dependencies: pip install -e . --group dev",
                flush=True,
            )
            # `--group dev` to match `uv sync`, which installs the dev group by
            # default. `check=False` on purpose: pip older than 25.1 does not
            # know `--group`, and a bare CalledProcessError would bury the one
            # fact the reader needs -- which command to run instead.
            installed = subprocess.run(
                [str(_venv_python()), "-m", "pip", "install", "-e", ".", "--group", "dev"],
                cwd=str(BACKEND_DIR),
                check=False,
            )
            if installed.returncode != 0:
                raise SystemExit(
                    "[dev] pip could not install the dev group (it needs pip >= 25.1). "
                    f"Run this in {BACKEND_VENV} instead:\n"
                    f"[dev]   {_venv_python_hint()} -m pip install -e . pytest httpx pytest-asyncio"
                )

    if "frontend" in missing:
        print("[dev] installing frontend dependencies: npm install", flush=True)
        subprocess.run([npm_executable(), "install"], cwd=str(FRONTEND_DIR), check=True)


# ----------------------------------------------------------------------- process care


def stop(process: "subprocess.Popen[bytes]") -> None:
    """Terminate a server and anything it spawned.

    On Windows `terminate()` kills only the process we started, and npm immediately
    forks node -- so the dev server would survive. `taskkill /T` walks the tree.
    """
    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def stop_all(processes: Processes) -> None:
    for _, process in processes:
        stop(process)


# -------------------------------------------------------------------------------- main


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dev.py",
        description="Start the Variant PDP backend and frontend together.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="install missing backend/frontend dependencies before starting",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(None)

    if not BACKEND_DIR.is_dir() or not FRONTEND_DIR.is_dir():
        raise SystemExit(f"Expected backend/ and frontend/ next to {__file__}.")

    missing = missing_dependencies()
    if missing:
        if not args.install:
            print(dependency_report(missing), file=sys.stderr, flush=True)
            return 1
        install_dependencies(missing)

    plan = (
        ("backend", backend_command(), BACKEND_DIR),
        ("frontend", frontend_command(), FRONTEND_DIR),
    )

    processes: Processes = []
    try:
        for name, command, cwd in plan:
            print(f"[dev] starting {name}: {' '.join(command)}", flush=True)
            processes.append((name, subprocess.Popen(command, cwd=str(cwd))))

        print(
            f"\n[dev] backend  http://localhost:{BACKEND_PORT}  (API docs at /docs)\n"
            f"[dev] frontend http://localhost:{FRONTEND_PORT}\n"
            f"[dev] press Ctrl+C to stop both\n",
            flush=True,
        )

        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"[dev] {name} exited with code {code}; stopping the other one")
                    return code if code != 0 else 1
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\n[dev] interrupted; stopping both servers")
        return 0
    finally:
        stop_all(processes)


if __name__ == "__main__":
    sys.exit(main())

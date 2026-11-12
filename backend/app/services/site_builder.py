"""Build the static site and release it atomically.

0. Preflight: check the frontend folder, build dependencies and every folder the build
   writes to, and fail at once with a clear, permanent error (no retries) when the
   worker can't build, instead of a generic build failure on every attempt.
1. Take an exclusive file lock (no concurrent builds, even across processes).
2. Run the configured build command (default ``npm run build``: Vite client +
   SSR bundle + prerender from the Flask API) without a shell.
3. Verify the output (index, 404, sitemap and a manifest newer than the job).
4. Add ``redirects.json`` (an audit copy; Nginx asks Flask for redirects).
5. Copy the output to ``PUBLISH_RELEASES_DIR/<release>`` and switch the
   ``PUBLISH_CURRENT_LINK`` symlink with an atomic rename. The previous release
   keeps being served until the switch, so a failed build never replaces the
   live site. Old releases beyond ``PUBLISH_KEEP_RELEASES`` are removed.
6. Optionally run ``PUBLISH_DEPLOY_COMMAND`` (remote/CDN sync adapter).
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import current_app

REQUIRED_FILES = ("index.html", "404.html", "sitemap.xml", "prerender-manifest.json")
NODE_TOOLS = ("npm", "npx", "node", "pnpm", "yarn")

# Failure categories (recorded on the job). Permission, dependency and configuration
# problems are permanent: retrying the same job can't fix them.
PERMISSION = "permission"
DEPENDENCIES = "dependencies"
CONFIGURATION = "configuration"
BUILD = "build"

_PERMISSION_LOG = re.compile(
    r"\bE(?:ACCES|PERM|ROFS)\b|permission denied|read-only file system", re.IGNORECASE
)
_MISSING_LOG = re.compile(
    r"Cannot find (?:module|package)|ERR_MODULE_NOT_FOUND|command not found|: not found\b",
    re.IGNORECASE,
)
PERMISSION_MESSAGE = (
    "The build couldn't write to the frontend build folders (permission denied). The "
    "publishing worker needs write access to the frontend folder, node_modules/.vite-temp, "
    ".ssr and dist. Retrying won't help until that is fixed; the live site is unchanged."
)
MISSING_MESSAGE = (
    "The build couldn't find a module or command it needs: the frontend dependencies look "
    "incomplete. Retrying won't help until they are installed; the live site is unchanged."
)


class BuildError(RuntimeError):
    def __init__(
        self,
        message: str,
        log: str = "",
        *,
        transient: bool = True,
        category: str = BUILD,
    ):
        super().__init__(message)
        self.log = log
        self.transient = transient
        self.category = category


def _writable(path: Path) -> bool:
    return os.access(path, os.W_OK | os.X_OK)


def _writable_x(path: str) -> bool:
    return os.access(path, os.X_OK)


def _existing(path: Path) -> Path:
    """The path itself or its nearest existing parent (where it would be created)."""
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


@dataclass
class BuildOutcome:
    release: str
    log: str
    details: dict[str, Any] = field(default_factory=dict)


def sanitise(text: str) -> str:
    """Strip absolute paths and secret-looking values from diagnostic output."""
    roots = {
        current_app.config.get("FRONTEND_DIR", ""),
        current_app.config.get("PUBLISH_RELEASES_DIR", ""),
        str(Path.home()),
    }
    for root in sorted((r for r in roots if r and len(r) > 3), key=len, reverse=True):
        text = text.replace(root, "<path>")
    text = re.sub(r"(?i)(password|secret|token|key)=\S+", r"\1=<redacted>", text)
    text = re.sub(r"postgres(ql)?(\+\w+)?://\S+", "<database-url>", text)
    return text


def _command(raw: Any, default: list[str]) -> list[str]:
    if not raw:
        return default
    if isinstance(raw, list):
        return [str(x) for x in raw]
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise BuildError("PUBLISH_BUILD_COMMAND must be a JSON list of strings.", transient=False)
    return value


class LocalReleaseBuilder:
    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or current_app.config
        self.frontend = Path(cfg["FRONTEND_DIR"])
        self.dist = Path(cfg.get("PUBLISH_DIST_DIR") or self.frontend / "dist")
        self.releases = Path(cfg["PUBLISH_RELEASES_DIR"])
        self.current = Path(cfg["PUBLISH_CURRENT_LINK"])
        self.keep = max(2, int(cfg["PUBLISH_KEEP_RELEASES"]))
        self.timeout = int(cfg["PUBLISH_BUILD_TIMEOUT_SECONDS"])
        self.command = _command(cfg.get("PUBLISH_BUILD_COMMAND"), ["npm", "run", "build"])
        self.deploy = cfg.get("PUBLISH_DEPLOY_COMMAND") or ""
        self.api_url = cfg["PUBLISH_API_URL"]

    # -- helpers -------------------------------------------------------------------------

    def _run(self, argv: list[str], heartbeat: Callable[[], None], cwd: Path) -> str:
        env = {
            **os.environ,
            "PRERENDER_API_URL": self.api_url,
            "NODE_ENV": "production",
            "CI": "1",
        }
        try:
            proc = subprocess.Popen(  # noqa: S603 - fixed argv from configuration, no shell
                argv,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            raise BuildError(
                f"The build command “{Path(argv[0]).name}” isn't installed or isn't on the PATH.",
                transient=False,
                category=DEPENDENCIES,
            ) from None
        except PermissionError:
            raise BuildError(PERMISSION_MESSAGE, transient=False, category=PERMISSION) from None
        except OSError as exc:
            raise BuildError(f"Could not start the build command ({exc.strerror}).") from None
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                out, _ = proc.communicate(timeout=10)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() > deadline:
                    proc.kill()
                    out, _ = proc.communicate()
                    raise BuildError(
                        f"The build took longer than {self.timeout} seconds.", sanitise(out or "")
                    ) from None
                heartbeat()  # still running: tell the queue the worker is alive
        output = [out or ""]
        log = sanitise("".join(output))
        if proc.returncode != 0:
            # Permission and missing-dependency failures are permanent: say so and stop.
            if _PERMISSION_LOG.search(log):
                raise BuildError(PERMISSION_MESSAGE, log, transient=False, category=PERMISSION)
            if _MISSING_LOG.search(log):
                raise BuildError(MISSING_MESSAGE, log, transient=False, category=DEPENDENCIES)
            raise BuildError(f"The build command failed (exit code {proc.returncode}).", log)
        return log

    def _label(self, path: Path) -> str:
        """A path for messages, relative to the frontend or releases folder (no absolutes)."""
        for root, name in ((self.frontend, "frontend"), (self.releases, "releases")):
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            return name if str(rel) == "." else f"{name}/{rel}"
        return path.name or "the publishing folder"

    def problems(self) -> list[tuple[str, str]]:
        """Everything that would stop a build, as ``(category, message)`` pairs."""
        found: list[tuple[str, str]] = []

        def must_write(path: Path, what: str | None = None) -> None:
            target = _existing(path)
            if not _writable(target):
                suffix = "" if target == path else f" (needed to create {self._label(path)})"
                found.append(
                    (
                        PERMISSION,
                        f"The publishing worker can't write to {what or self._label(target)}"
                        f"{suffix}.",
                    )
                )

        if not self.frontend.is_dir():
            return [(CONFIGURATION, "The frontend folder doesn't exist.")]
        tool = self.command[0] if self.command else ""
        if not tool or not (shutil.which(tool) or (Path(tool).is_absolute() and _writable_x(tool))):
            found.append(
                (
                    DEPENDENCIES,
                    f"The build command “{Path(tool).name}” isn't installed or isn't on the PATH.",
                )
            )
        if Path(tool).name in NODE_TOOLS:
            modules = self.frontend / "node_modules"
            if not (self.frontend / "package.json").is_file():
                found.append((CONFIGURATION, "frontend/package.json is missing."))
            if not modules.is_dir():
                found.append(
                    (DEPENDENCIES, "frontend/node_modules is missing (dependencies not installed).")
                )
            else:
                if not (modules / ".bin" / "vite").exists():
                    found.append((DEPENDENCIES, "Vite isn't installed in frontend/node_modules."))
                must_write(modules / ".vite-temp")
            must_write(self.frontend / ".ssr")
        must_write(self.dist)
        if self.dist.is_dir():  # Vite empties dist, so its folders must be writable too
            for sub in sorted(p for p in self.dist.iterdir() if p.is_dir() and not p.is_symlink()):
                must_write(sub)
        must_write(self.releases)
        lock = self.releases / ".build.lock"
        if lock.exists() and not os.access(lock, os.W_OK):
            found.append((PERMISSION, "The publishing worker can't write to releases/.build.lock."))
        must_write(self.current.parent, "the folder of the live-release link")
        return list(dict.fromkeys(found))  # unique, in order

    def preflight(self) -> None:
        found = self.problems()
        if not found:
            return
        category = next(
            c for c in (PERMISSION, DEPENDENCIES, CONFIGURATION) if any(f[0] == c for f in found)
        )
        lines = [message for _, message in found]
        raise BuildError(
            "Publishing can't start: "
            + " ".join(lines)
            + " Retrying won't help until this is fixed; the live site is unchanged.",
            "Preflight check failed before building:\n" + "\n".join(f"- {x}" for x in lines),
            transient=False,
            category=category,
        )

    def _verify(self, started: datetime) -> dict[str, Any]:
        missing = [f for f in REQUIRED_FILES if not (self.dist / f).is_file()]
        if missing:
            raise BuildError(
                "The build output is incomplete (missing " + ", ".join(missing) + ").",
                transient=False,
            )
        try:
            manifest = json.loads((self.dist / "prerender-manifest.json").read_text("utf-8"))
            generated = datetime.fromisoformat(manifest["generatedAt"].replace("Z", "+00:00"))
        except (OSError, ValueError, KeyError):
            raise BuildError("The prerender manifest is unreadable.", transient=False) from None
        if generated < started.replace(microsecond=0):
            raise BuildError("The build output is stale (manifest older than the job).")
        return {
            "pages": len(manifest.get("pages", [])),
            "indexing": bool(manifest.get("indexing")),
            "generated_at": manifest["generatedAt"],
        }

    def _switch(self, target: Path) -> None:
        self.current.parent.mkdir(parents=True, exist_ok=True)
        tmp_link = self.current.with_name(f".{self.current.name}.{os.getpid()}.tmp")
        tmp_link.unlink(missing_ok=True)
        os.symlink(target, tmp_link)
        os.replace(tmp_link, self.current)  # atomic on POSIX

    def _prune(self) -> list[str]:
        live = self.current.resolve() if self.current.exists() else None
        releases = sorted(
            (p for p in self.releases.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name,
        )
        removed = []
        for old in releases[: max(0, len(releases) - self.keep)]:
            if live is not None and old.resolve() == live:
                continue
            shutil.rmtree(old, ignore_errors=True)
            removed.append(old.name)
        return removed

    # -- entry point ---------------------------------------------------------------------

    def run(self, job, heartbeat: Callable[[], None]) -> BuildOutcome:
        from . import redirect_service

        self.preflight()
        try:
            return self._build(job, heartbeat, redirect_service)
        except PermissionError as exc:  # a folder changed under us: permanent, not "unexpected"
            where = self._label(Path(exc.filename)) if exc.filename else "a publishing folder"
            raise BuildError(
                f"Permission denied while publishing ({where}). Retrying won't help until that "
                "is fixed; the live site is unchanged.",
                transient=False,
                category=PERMISSION,
            ) from None

    def _build(self, job, heartbeat: Callable[[], None], redirect_service) -> BuildOutcome:
        self.releases.mkdir(parents=True, exist_ok=True)
        lock_path = self.releases / ".build.lock"
        with open(lock_path, "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise BuildError("Another build is already running.") from None
            started = datetime.now(UTC)
            log = self._run(self.command, heartbeat, self.frontend)
            details = self._verify(started)
            (self.dist / "redirects.json").write_text(
                json.dumps(redirect_service.active_redirects(), indent=2) + "\n", "utf-8"
            )
            release = f"{started.strftime('%Y%m%d-%H%M%S')}-job{job.id}"
            staging = self.releases / f".{release}.partial"
            final = self.releases / release
            shutil.rmtree(staging, ignore_errors=True)
            shutil.copytree(self.dist, staging, symlinks=False)
            os.chmod(staging, 0o755)
            os.replace(staging, final)
            self._switch(final)
            details["removed_releases"] = self._prune()
            if self.deploy:
                argv = [a.replace("{release}", str(final)) for a in _command(self.deploy, [])]
                log += "\n--- deploy ---\n" + self._run(argv, heartbeat, final)
            heartbeat()
        return BuildOutcome(release=release, log=log, details=details)

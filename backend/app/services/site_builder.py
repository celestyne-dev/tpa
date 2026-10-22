"""Build the static site and release it atomically.

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


class BuildError(RuntimeError):
    def __init__(self, message: str, log: str = "", *, transient: bool = True):
        super().__init__(message)
        self.log = log
        self.transient = transient


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
            raise BuildError(f"The build command failed (exit code {proc.returncode}).", log)
        return log

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

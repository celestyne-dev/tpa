"""Publishing preflight: permission and dependency problems fail once, clearly, and never
touch the live release.

The frontend layout mimics the real one (package.json, node_modules/.bin/vite, a
``npm`` command) with a stand-in ``npm`` that runs the small build script.
"""

# ruff: noqa: F811 - the shared ``builder_config`` fixture is imported from its module

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

from app.extensions import db
from app.services import publishing, site_builder
from app.services.site_builder import LocalReleaseBuilder

from .test_seo_publishing import builder_config  # noqa: F401


@pytest.fixture()
def node_frontend(builder_config, tmp_path):
    """A frontend that builds with ``npm run build`` (a stand-in npm)."""
    app = builder_config
    frontend = Path(app.config["FRONTEND_DIR"])
    (frontend / "package.json").write_text('{"name": "tpa-frontend"}')
    (frontend / "node_modules" / ".bin").mkdir(parents=True)
    (frontend / "node_modules" / ".bin" / "vite").write_text("")
    (frontend / "node_modules" / ".vite-temp").mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    npm = bindir / "npm"
    npm.write_text(f'#!/bin/sh\nexec "{sys.executable}" build.py\n')
    npm.chmod(npm.stat().st_mode | stat.S_IXUSR)
    app.config["PUBLISH_BUILD_COMMAND"] = json.dumps([str(npm), "run", "build"])
    return app


@pytest.fixture()
def deny(monkeypatch):
    """Make folders unwritable for the worker (also when the tests run as root)."""
    blocked: list[Path] = []
    real = site_builder._writable

    def _deny(*paths: Path) -> None:
        for path in paths:
            path.chmod(0o555)
            blocked.append(path)
        if os.geteuid() == 0:  # root ignores permission bits
            monkeypatch.setattr(
                site_builder, "_writable", lambda p: Path(p) not in blocked and real(p)
            )

    yield _deny
    for path in blocked:
        path.chmod(0o755)


def _publish(app):
    with app.app_context():
        publishing.request_build("t", None, trigger="manual")
        db.session.commit()
        job = publishing.run_job(publishing.claim_next(), LocalReleaseBuilder())
        return {
            "status": job.status,
            "attempts": job.attempts,
            "error": job.error or "",
            "log": job.log_tail or "",
            "details": job.details or {},
            "release": job.release,
        }


def _live(app):
    current = Path(app.config["PUBLISH_CURRENT_LINK"])
    return current.resolve() if current.exists() else None


def _assert_permanent(job, category):
    assert job["status"] == "failed" and job["attempts"] == 1  # no retries scheduled
    assert job["details"]["failure"] == {"category": category, "retry": False}
    assert "/tmp" not in job["error"] and "/tmp" not in job["log"]  # sanitised


def test_successful_publishing_with_the_node_layout(node_frontend):
    app = node_frontend
    job = _publish(app)
    assert job["status"] == "succeeded", job["error"]
    assert "failure" not in job["details"] and job["details"]["pages"] == 1
    assert _live(app).name == job["release"]
    with app.app_context():
        assert publishing.summary()["state"] == "published"


def test_unwritable_build_directory_fails_once_and_keeps_the_live_site(node_frontend, deny):
    app = node_frontend
    first = _publish(app)
    assert first["status"] == "succeeded"
    live = _live(app)
    releases = sorted(p.name for p in Path(app.config["PUBLISH_RELEASES_DIR"]).iterdir())
    dist = Path(app.config["PUBLISH_DIST_DIR"])
    (dist / "assets").mkdir(exist_ok=True)
    deny(dist / "assets")
    job = _publish(app)
    _assert_permanent(job, "permission")
    assert "can't write to frontend/dist/assets" in job["error"]
    assert "the live site is unchanged" in job["error"]
    assert "Preflight check failed" in job["log"]
    assert _live(app) == live
    assert sorted(p.name for p in Path(app.config["PUBLISH_RELEASES_DIR"]).iterdir()) == releases
    with app.app_context():
        summary = publishing.summary()
        assert summary["state"] == "failed" and summary["last_failure"]["error"] == job["error"]
        assert summary["last_success"]["release"] == first["release"]


def test_unwritable_vite_temp_directory_is_reported_before_building(node_frontend, deny):
    app = node_frontend
    deny(Path(app.config["FRONTEND_DIR"]) / "node_modules" / ".vite-temp")
    job = _publish(app)
    _assert_permanent(job, "permission")
    assert "frontend/node_modules/.vite-temp" in job["error"]
    assert not (Path(app.config["PUBLISH_DIST_DIR"]) / "index.html").exists()  # never built
    assert _live(app) is None


def test_missing_vite_temp_needs_a_writable_node_modules(node_frontend, deny):
    app = node_frontend
    modules = Path(app.config["FRONTEND_DIR"]) / "node_modules"
    (modules / ".vite-temp").rmdir()
    deny(modules)
    job = _publish(app)
    _assert_permanent(job, "permission")
    assert "needed to create frontend/node_modules/.vite-temp" in job["error"]


def test_missing_build_dependencies(node_frontend):
    app = node_frontend
    modules = Path(app.config["FRONTEND_DIR"]) / "node_modules"
    (modules / ".bin" / "vite").unlink()
    job = _publish(app)
    _assert_permanent(job, "dependencies")
    assert "Vite isn't installed" in job["error"]

    shutil.rmtree(modules)
    job = _publish(app)
    _assert_permanent(job, "dependencies")
    assert "frontend/node_modules is missing" in job["error"]

    app.config["PUBLISH_BUILD_COMMAND"] = json.dumps(["/nonexistent/npm", "run", "build"])
    job = _publish(app)
    _assert_permanent(job, "dependencies")
    assert "“npm” isn't installed" in job["error"]


def test_permission_errors_during_the_build_are_permanent(node_frontend):
    """The production failure: Vite can't write its temporary config file."""
    app = node_frontend
    first = _publish(app)
    live = _live(app)
    script = Path(app.config["FRONTEND_DIR"]) / "build.py"
    script.write_text(
        "import sys\n"
        'print("failed to load config: EACCES: permission denied, open '
        "'node_modules/.vite-temp/vite.config.js.timestamp-1-abc.mjs'\", file=sys.stderr)\n"
        "sys.exit(1)\n"
    )
    job = _publish(app)
    _assert_permanent(job, "permission")
    assert "permission denied" in job["error"]
    assert "vite.config.js.timestamp" in job["log"]  # the build output is kept for diagnosis
    assert _live(app) == live and first["status"] == "succeeded"


def test_ordinary_build_failures_are_still_retried(node_frontend, monkeypatch):
    app = node_frontend
    monkeypatch.setenv("FAIL_BUILD", "1")
    job = _publish(app)
    assert job["status"] == "pending" and "exit code 3" in job["error"]
    assert job["details"]["failure"] == {"category": "build", "retry": True}
    with app.app_context():
        assert publishing.summary()["state"] == "queued"

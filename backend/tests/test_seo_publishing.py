"""SEO checks, sitemap, redirects and the static publishing pipeline."""

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Article, AuditLog, PublishJob, Redirect
from app.services import publishing, redirect_service, seo_service
from app.services.site_builder import BuildError, BuildOutcome, LocalReleaseBuilder
from app.utils.errors import ConflictError, ValidationError

from .test_admin_content import _draft

ART = "/api/v1/admin/articles"
RED = "/api/v1/admin/redirects"
JOBS = "/api/v1/admin/publishing/jobs"


# ---- SEO checks ------------------------------------------------------------------------


def _codes(result):
    return {c["code"] for c in result["checks"]}


def test_article_seo_checks(seeded, as_role):
    owner = as_role("super_admin")
    bare = owner.post(ART, {"title": "x" * 70}).get_json()["data"]
    codes = _codes(owner.get(f"{ART}/{bare['id']}/seo-checks").get_json()["data"])
    assert {
        "empty_content",
        "missing_meta_description",
        "missing_featured_image",
        "missing_author",
        "missing_topic",
        "long_title",
    } <= codes
    article = _draft(owner, seeded)
    body = [
        {"type": "heading", "text": "Too deep first", "level": 3},
        {"type": "paragraph", "text": "Words " * 30},
        {"type": "button", "label": "Read", "href": "/articles/does-not-exist"},
        {"type": "button", "label": "Topics", "href": "/topics/positive-mindset"},
    ]
    owner.patch(
        f"{ART}/{article['id']}",
        {
            "body": body,
            "meta_description": "A practical guide to calmer weeks with small, kind habits.",
            "noindex": True,
            "canonical_url": "https://elsewhere.example.org/original",
        },
    )
    result = owner.get(f"{ART}/{article['id']}/seo-checks").get_json()["data"]
    codes = _codes(result)
    assert {"heading_hierarchy", "broken_internal_link", "noindex", "external_canonical"} <= codes
    assert "missing_meta_description" not in codes
    broken = [c for c in result["checks"] if c["code"] == "broken_internal_link"]
    assert len(broken) == 1 and "/articles/does-not-exist" in broken[0]["message"]
    assert result["preview"]["indexable"] is False
    assert result["preview"]["url"].endswith(f"/articles/{article['slug']}")


def test_duplicate_canonical_and_slug_checks(seeded, as_role):
    owner = as_role("super_admin")
    a = _draft(owner, seeded, canonical_url="https://example.org/same")
    _draft(owner, seeded, title="Another", canonical_url="https://example.org/same")
    codes = _codes(owner.get(f"{ART}/{a['id']}/seo-checks").get_json()["data"])
    assert "duplicate_canonical" in codes
    status = owner.get(f"{ART}/slug-check?slug={a['slug']}").get_json()["data"]
    assert status == {**status, "valid": True, "available": False}
    assert owner.get(f"{ART}/slug-check?slug=Bad Slug").get_json()["data"]["valid"] is False
    free = owner.get(f"{ART}/slug-check?slug={a['slug']}&exclude={a['id']}").get_json()["data"]
    assert free["available"] is True


def test_seo_overview_reports_real_counts(seeded, as_role):
    owner = as_role("super_admin")
    data = owner.get("/api/v1/admin/seo/overview").get_json()["data"]
    assert data["published_articles"] == 6
    assert data["totals"]["missing_meta_description"] >= 0
    assert data["sitemap"]["articles"] == 6 and data["redirects"] == {"total": 0, "active": 0}
    assert as_role("editor").get("/api/v1/admin/seo/overview").status_code == 200  # seo.view
    assert as_role("moderator").get("/api/v1/admin/seo/overview").status_code == 403


def test_static_paths_match_the_frontend():
    """The sitemap lists exactly the frontend's indexable static routes (``staticRoutes``),
    never a private route (account, checkout, auth, newsletter tokens) and nothing under
    /admin or /learn."""
    nav = (Path(__file__).resolve().parents[2] / "frontend/src/config/navigation.js").read_text()
    routes = dict(re.findall(r'^\s+(\w+): "(/[^"]*)",', nav, re.M))
    static_block = nav.split("export const staticRoutes")[1].split("];")[0]
    frontend = [routes[k] for k in re.findall(r"path: routes\.(\w+)", static_block)]
    sitemap = [p for p, _, _ in seo_service.STATIC_PATHS]
    assert frontend == sitemap
    private_block = nav.split("export const privateRoutes")[1].split("];")[0]
    private = {routes[k] for k in re.findall(r"routes\.(\w+)", private_block)}
    assert private and not private & set(sitemap)
    assert not [p for p in sitemap if p.startswith(("/admin", "/learn", "/account", "/checkout"))]


# ---- sitemap -----------------------------------------------------------------------------


def test_sitemap_lists_only_indexable_published_content(seeded, as_role, client):
    owner = as_role("super_admin")
    draft = _draft(owner, seeded, title="Private draft")
    noindex = _draft(owner, seeded, title="Hidden one")
    owner.post(f"{ART}/{noindex['id']}/publish")
    owner.patch(f"{ART}/{noindex['id']}", {"noindex": True})
    canonical = _draft(owner, seeded, title="Syndicated")
    owner.post(f"{ART}/{canonical['id']}/publish")
    owner.patch(f"{ART}/{canonical['id']}", {"canonical_url": "https://other.example/x"})
    archived = _draft(owner, seeded, title="Old news")
    owner.post(f"{ART}/{archived['id']}/publish")
    owner.post(f"{ART}/{archived['id']}/archive")

    entries = client.get("/api/v1/sitemap").get_json()["data"]
    paths = [e["path"] for e in entries]
    for hidden in (draft, noindex, canonical, archived):
        assert f"/articles/{hidden['slug']}" not in paths
    assert not [p for p in paths if p.startswith(("/admin", "/api"))]
    articles = [e for e in entries if e["type"] == "article"]
    assert len(articles) == 6 and all(e["lastmod"] for e in articles)
    assert any(e["images"] for e in articles)
    assert entries[0]["path"] == "/"


# ---- redirects -----------------------------------------------------------------------------


def test_redirect_crud_validation_and_resolution(app, as_role, client):
    seo = as_role("seo_manager")
    res = seo.post(RED, {"source_path": "/old-post/", "destination": "/articles/new-post"})
    assert res.status_code == 201
    created = res.get_json()["data"]
    assert created["source_path"] == "/old-post" and created["status_code"] == 301
    assert seo.post(RED, {"source_path": "/old-post", "destination": "/x"}).status_code == 409
    hop = client.get("/_redirect/old-post")
    assert hop.status_code == 301 and hop.headers["Location"] == "/articles/new-post"
    assert client.get("/api/v1/redirects/resolve?path=/old-post").status_code == 200
    seo.patch(f"{RED}/{created['id']}", {"status_code": 308})
    assert client.get("/_redirect/old-post").status_code == 308
    seo.patch(f"{RED}/{created['id']}", {"is_active": False})
    assert client.get("/_redirect/old-post").status_code == 404
    assert seo.delete(f"{RED}/{created['id']}").status_code == 200
    assert (
        as_role("editor").post(RED, {"source_path": "/a", "destination": "/b"}).status_code == 403
    )


@pytest.mark.parametrize(
    "source,destination,fragment",
    [
        ("/admin/login", "/x", "cannot be redirected"),
        ("/", "/x", "cannot be redirected"),
        ("/same", "/same", "itself"),
        ("/a", "https://evil.example/phish", "open redirects"),
        ("/a", "//evil.example", "site path"),
        ("/a", "javascript:alert(1)", "site path or a full https"),
        ("/bad path", "/x", "Use a path"),
        ("/a", '/x" onload="y', "invalid characters"),
    ],
)
def test_redirects_reject_unsafe_values(app, source, destination, fragment):
    with app.app_context():
        with pytest.raises(ValidationError) as exc:
            redirect_service.create_redirect(
                {"source_path": source, "destination": destination}, None
            )
        assert fragment in json.dumps(exc.value.details or exc.value.message)


def test_redirect_loops_and_chains_are_blocked(app):
    with app.app_context():
        create = redirect_service.create_redirect
        create({"source_path": "/a", "destination": "/b"}, None)
        create({"source_path": "/b", "destination": "/c"}, None)
        with pytest.raises(ValidationError, match="loop"):
            create({"source_path": "/c", "destination": "/a"}, None)
        for src, dst in (("/c", "/d"), ("/d", "/e"), ("/e", "/f")):
            create({"source_path": src, "destination": dst}, None)
        with pytest.raises(ValidationError):
            create({"source_path": "/z", "destination": "/a"}, None)  # 6 hops
        with pytest.raises(ConflictError):
            create({"source_path": "/a", "destination": "/q"}, None)


def test_allowed_external_hosts(app):
    app.config["REDIRECT_ALLOWED_HOSTS"] = ["partners.example.org"]
    with app.app_context():
        r = redirect_service.create_redirect(
            {"source_path": "/partner", "destination": "https://partners.example.org/tpa"}, None
        )
        assert r.destination.startswith("https://partners")


def test_redirect_import_and_export(app, as_role):
    api = as_role("super_admin")
    csv_text = (
        "source_path,destination,status_code,is_active,note\n"
        "/2019/01/old-a,/articles/a,301,1,migrated\n"
        "/2019/01/old-b,/articles/b,308,1,\n"
        "/2019/01/old-a,/articles/dupe,301,1,\n"
        "/admin,/x,301,1,\n"
        "/loop,/loop,301,1,\n"
    )
    dry = api.post(f"{RED}/import", {"csv": csv_text, "dry_run": True}).get_json()["data"]
    assert dry["valid"] == 2 and dry["created"] == 0 and len(dry["errors"]) == 3
    assert api.get(RED).get_json()["meta"]["pagination"]["total"] == 0
    result = api.post(f"{RED}/import", {"csv": csv_text}).get_json()["data"]
    assert result["created"] == 2 and [e["row"] for e in result["errors"]] == [3, 4, 5]
    exported = api.get(f"{RED}/export")
    assert exported.headers["Content-Type"].startswith("text/csv")
    text = exported.get_data(as_text=True)
    assert "/2019/01/old-a,/articles/a,301,1,migrated" in text
    with app.app_context():
        assert {r.origin for r in db.session.scalars(db.select(Redirect))} == {"import"}


def test_public_redirect_list_for_static_servers(app, client):
    with app.app_context():
        redirect_service.create_redirect({"source_path": "/a", "destination": "/b"}, None)
        db.session.commit()
    data = client.get("/api/v1/redirects").get_json()["data"]
    assert data == [{"source": "/a", "destination": "/b", "status_code": 301}]


# ---- publishing jobs -------------------------------------------------------------------------


def test_public_changes_queue_one_debounced_job(seeded, as_role):
    seeded.config["PUBLISH_DEBOUNCE_SECONDS"] = 30
    editor = as_role("editor")
    article = _draft(editor, seeded)
    with seeded.app_context():
        db.session.query(PublishJob).delete()
        db.session.commit()
    editor.post(f"{ART}/{article['id']}/publish")
    editor.patch(f"{ART}/{article['id']}", {"subtitle": "Tweak"})
    editor.post(f"{ART}/{article['id']}/unpublish")
    with seeded.app_context():
        jobs = db.session.scalars(db.select(PublishJob)).all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.status == "pending" and job.trigger == "content"
        assert job.reasons == [
            "article_published",
            "published_article_updated",
            "article_unpublished",
        ]
        assert job.not_before > datetime.now(UTC) + timedelta(seconds=20)
        # A drafts-only edit does not queue anything.
        db.session.query(PublishJob).delete()
        db.session.commit()
    draft = _draft(editor, seeded, title="Quiet draft")
    editor.patch(f"{ART}/{draft['id']}", {"subtitle": "x"})
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(PublishJob.id))) == 0


class FakeBuilder:
    def __init__(self, outcome=None, error=None):
        self.outcome, self.error, self.calls = outcome, error, 0

    def run(self, job, heartbeat):
        self.calls += 1
        heartbeat()
        if self.error:
            raise self.error
        return self.outcome or BuildOutcome(release=f"r{job.id}", log="ok", details={"pages": 3})


def test_worker_claims_runs_retries_and_fails(app):
    with app.app_context():
        job = publishing.request_build("test", None, trigger="manual")
        db.session.commit()
        claimed = publishing.claim_next()
        assert claimed.id == job.id and claimed.status == "running" and claimed.attempts == 1
        assert publishing.claim_next() is None  # one build at a time
        result = publishing.run_job(claimed, FakeBuilder())
        assert result.status == "succeeded" and result.release == f"r{job.id}"

        job = publishing.request_build("again", None, trigger="manual")
        db.session.commit()
        failing = FakeBuilder(error=BuildError("npm failed", "log /secret/path"))
        result = publishing.run_job(publishing.claim_next(), failing)
        assert result.status == "pending" and result.error == "npm failed"
        assert result.not_before > datetime.now(UTC)  # backoff
        for _ in range(2):
            result.not_before = datetime.now(UTC) - timedelta(seconds=1)
            db.session.commit()
            result = publishing.run_job(publishing.claim_next(), failing)
        assert result.status == "failed" and result.attempts == 3
        permanent = publishing.request_build("bad config", None, trigger="manual")
        db.session.commit()
        result = publishing.run_job(
            publishing.claim_next(), FakeBuilder(error=BuildError("bad", transient=False))
        )
        assert result.status == "failed" and result.attempts == 1 and permanent.id == result.id
        actions = [a for (a,) in db.session.execute(db.select(AuditLog.action))]
        assert "publish.succeeded" in actions and "publish.failed" in actions


def test_stale_running_jobs_are_recovered(app):
    with app.app_context():
        job = publishing.request_build("x", None, trigger="manual")
        db.session.commit()
        claimed = publishing.claim_next()
        claimed.heartbeat_at = datetime.now(UTC) - timedelta(hours=2)
        db.session.commit()
        assert publishing.recover_stale() == 1
        assert db.session.get(PublishJob, job.id).status == "pending"


def test_publishing_api_permissions_retry_and_cancel(app, as_role):
    owner = as_role("super_admin")
    created = owner.post(JOBS)
    assert created.status_code == 201
    job_id = created.get_json()["data"]["id"]
    listing = owner.get(JOBS).get_json()
    assert listing["data"][0]["id"] == job_id and listing["meta"]["summary"]["pending"]
    editor = as_role("editor")  # publishing.view only
    assert editor.get(JOBS).status_code == 200
    assert editor.post(JOBS).status_code == 403
    assert editor.post(f"{JOBS}/{job_id}/cancel").status_code == 403
    assert owner.post(f"{JOBS}/{job_id}/retry").status_code == 409  # not failed
    assert owner.post(f"{JOBS}/{job_id}/cancel").get_json()["data"]["status"] == "cancelled"
    retried = owner.post(f"{JOBS}/{job_id}/retry")
    assert retried.status_code == 201 and retried.get_json()["data"]["status"] == "pending"
    status = editor.get("/api/v1/admin/publishing/status").get_json()["data"]
    assert "jobs" in status and status["rebuild_required"] in (True, False)
    assert as_role("analyst").post(JOBS).status_code == 403


# ---- real builder with a stand-in build command ----------------------------------------------

BUILD_SCRIPT = """
import json, os, sys, datetime, pathlib
dist = pathlib.Path("dist")
dist.mkdir(exist_ok=True)
if os.environ.get("FAIL_BUILD"):
    print("build failed on purpose", file=sys.stderr)
    sys.exit(3)
for name in ("index.html", "404.html", "sitemap.xml"):
    (dist / name).write_text("<html>" + name + "</html>")
(dist / "prerender-manifest.json").write_text(json.dumps({
    "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "indexing": False, "pages": [{"path": "/"}],
}))
print("built with API", os.environ["PRERENDER_API_URL"])
"""


@pytest.fixture()
def builder_config(app, tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "build.py").write_text(BUILD_SCRIPT)
    app.config.update(
        FRONTEND_DIR=str(frontend),
        PUBLISH_DIST_DIR=str(frontend / "dist"),
        PUBLISH_BUILD_COMMAND=json.dumps([sys.executable, "build.py"]),
        PUBLISH_KEEP_RELEASES=2,
    )
    return app


def test_release_is_switched_atomically_and_old_releases_pruned(builder_config, monkeypatch):
    app = builder_config
    current = Path(app.config["PUBLISH_CURRENT_LINK"])
    releases = Path(app.config["PUBLISH_RELEASES_DIR"])
    with app.app_context():
        redirect_service.create_redirect({"source_path": "/old", "destination": "/new"}, None)
        names = []
        for _ in range(3):
            publishing.request_build("t", None, trigger="manual")
            db.session.commit()
            job = publishing.run_job(publishing.claim_next(), LocalReleaseBuilder())
            assert job.status == "succeeded", job.error
            names.append(job.release)
            assert current.is_symlink() and current.resolve().name == job.release
            assert job.details["pages"] == 1 and "built with API" in job.log_tail
        assert sorted(p.name for p in releases.iterdir() if not p.name.startswith(".")) == names[1:]
        assert json.loads((current / "redirects.json").read_text())[0]["source"] == "/old"
        live = current.resolve()

        # A failing build leaves the live release untouched.
        monkeypatch.setenv("FAIL_BUILD", "1")
        publishing.request_build("t", None, trigger="manual")
        db.session.commit()
        job = publishing.run_job(publishing.claim_next(), LocalReleaseBuilder())
        assert job.status == "pending" and "exit code 3" in job.error
        assert "build failed on purpose" in job.log_tail
        assert current.resolve() == live


def test_concurrent_builds_are_prevented(builder_config):
    import fcntl

    app = builder_config
    releases = Path(app.config["PUBLISH_RELEASES_DIR"])
    releases.mkdir(parents=True, exist_ok=True)
    with open(releases / ".build.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with app.app_context(), pytest.raises(BuildError, match="already running"):
            LocalReleaseBuilder().run(type("J", (), {"id": 1})(), lambda: None)


def test_build_log_is_sanitised(builder_config):
    app = builder_config
    with app.app_context():
        from app.services.site_builder import sanitise

        text = f"{app.config['FRONTEND_DIR']}/x failed password=hunter2 postgresql://u:p@h/db"
        clean = sanitise(text)
        assert app.config["FRONTEND_DIR"] not in clean
        assert "hunter2" not in clean and "u:p@h" not in clean


def test_worker_cli_processes_a_job(builder_config):
    app = builder_config
    with app.app_context():
        publishing.request_build("cli", None, trigger="manual")
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["publish", "worker", "--once", "--no-scheduler"])
    assert "succeeded" in result.output, result.output
    with app.app_context():
        assert db.session.scalar(db.select(PublishJob.status)) == "succeeded"
        assert db.session.scalar(db.select(Article.id)) is None  # untouched content

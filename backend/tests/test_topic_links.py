"""Topic links: menus only link published topics, renamed topics keep a 301 from the old
URL, and a misspelled slug can be corrected without creating a second topic."""

from sqlalchemy import func, select

from app.extensions import db
from app.models import Article, NavigationItem, NavigationMenu, Redirect, Topic

TYPO, FIXED = "elationships-and-connection", "relationships-and-connection"


def _nav(client):
    return client.get("/api/v1/site").get_json()["data"]["navigation"]


def _nav_urls(client):
    nav = _nav(client)
    urls = []
    for item in [*nav["primary"], *(nav["mobile"] or []), *nav["legal"]]:
        urls.append(item.get("url"))
        urls += [c["url"] for c in item.get("children") or []]
    for group in nav["footer"]:
        urls += [i["url"] for i in group["items"]]
    return [u for u in urls if u]


def _active_slugs(app):
    with app.app_context():
        return set(db.session.scalars(select(Topic.slug).where(Topic.status == "active")))


def _rename_seed_topic(app, old, new, name=None):
    """Simulate production data whose slugs differ from the seed file."""
    with app.app_context():
        topic = db.session.scalar(select(Topic).where(Topic.slug == old))
        topic.slug = new
        if name:
            topic.name = name
        db.session.commit()
        return topic.id


def _topic_usage(app, topic_id):
    with app.app_context():
        primary = db.session.scalar(
            select(func.count(Article.id)).where(Article.primary_topic_id == topic_id)
        )
        return primary


def assert_topic_links_are_live(app, client, urls):
    live = _active_slugs(app)
    for url in urls:
        if url.startswith("/topics/"):
            slug = url.removeprefix("/topics/").split("/")[0].split("?")[0].split("#")[0]
            assert slug in live, f"{url} links to a topic that is not published"
            assert client.get(f"/api/v1/topics/{slug}").status_code == 200


# ---- navigation --------------------------------------------------------------------------


def test_default_menus_link_only_real_topics(seeded, app, client):
    urls = _nav_urls(client)
    assert any(u.startswith("/topics/") for u in urls)
    assert_topic_links_are_live(app, client, urls)


def test_default_menus_follow_production_slugs_not_seed_slugs(seeded, app, client):
    """The three 404s: production topics do not use the seed slugs the menus hardcoded."""
    for old in ("positive-mindset", "personal-growth", "resilience-starting-over"):
        with app.app_context():
            db.session.execute(
                Topic.__table__.update().where(Topic.slug == old).values(slug=old + "-x")
            )
            db.session.commit()
    urls = _nav_urls(client)
    for dead in ("positive-mindset", "personal-growth", "resilience-starting-over"):
        assert f"/topics/{dead}" not in urls
    assert_topic_links_are_live(app, client, urls)


def test_seeded_menus_get_real_topics(seeded, app, client):
    from app.services.seed_service import seed_cms_defaults

    _rename_seed_topic(app, "positive-mindset", "mindset")
    with app.app_context():
        for menu in db.session.scalars(select(NavigationMenu)):
            db.session.delete(menu)
        db.session.flush()
        seed_cms_defaults()
        db.session.commit()
        saved = [i.url for i in db.session.scalars(select(NavigationItem)) if i.url]
    assert "/topics/positive-mindset" not in saved
    topic_urls = [u for u in saved if u.startswith("/topics/")]
    assert topic_urls
    assert {u.removeprefix("/topics/") for u in topic_urls} <= _active_slugs(app)


def test_saved_menus_drop_missing_topics_and_follow_redirects(seeded, as_role, app, client):
    api = as_role("website_manager")
    with app.app_context():
        db.session.add(
            Redirect(source_path="/topics/old-growth", destination="/topics/personal-growth")
        )
        db.session.commit()
    res = api.put(
        "/api/v1/admin/navigation/primary",
        {
            "items": [
                {
                    "label": "Topics",
                    "link_type": "heading",
                    "children": [
                        {"label": "Mindset", "url": "/topics/positive-mindset"},
                        {"label": "Gone", "url": "/topics/no-such-topic"},
                        {"label": "Moved", "url": "/topics/old-growth"},
                    ],
                },
                {"label": "Dead", "url": "/topics/also-missing"},
                {"label": "Articles", "url": "/articles"},
            ]
        },
    )
    assert res.status_code == 200, res.get_json()
    warnings = res.get_json()["data"]["warnings"]
    assert "/topics/no-such-topic does not point to a published page yet." in warnings
    assert any("/topics/old-growth has moved" in w for w in warnings)

    primary = _nav(client)["primary"]
    assert [c["url"] for c in primary[0]["children"]] == [
        "/topics/positive-mindset",
        "/topics/personal-growth",
    ]
    assert [i["label"] for i in primary] == ["Topics", "Articles"]

    # A hidden topic is left out too, and a group with no links left disappears.
    api.put(
        "/api/v1/admin/navigation/footer",
        {
            "items": [
                {
                    "label": "Explore",
                    "link_type": "heading",
                    "children": [{"label": "Mindset", "url": "/topics/positive-mindset"}],
                }
            ]
        },
    )
    with app.app_context():
        tid = db.session.scalar(select(Topic.id).where(Topic.slug == "positive-mindset"))
    editor = as_role("editor")
    assert editor.patch(f"/api/v1/admin/topics/{tid}", {"status": "hidden"}).status_code == 200
    nav = _nav(client)
    assert nav["footer"] == []
    assert nav["primary"][0]["children"][0]["url"] == "/topics/personal-growth"


# ---- renaming a topic --------------------------------------------------------------------


def test_renaming_a_topic_keeps_articles_and_redirects_the_old_url(seeded, as_role, app, client):
    api = as_role("editor")
    with app.app_context():
        topic = db.session.scalar(select(Topic).where(Topic.slug == "personal-growth"))
        tid, count = topic.id, db.session.scalar(select(func.count(Topic.id)))
    before = client.get("/api/v1/articles?topic=personal-growth").get_json()["meta"]["pagination"]
    nav_before = [u for u in _nav_urls(client) if "personal-growth" in u]
    with app.app_context():  # save the menus so the stored links have to be updated
        from app.services.seed_service import seed_cms_defaults

        seed_cms_defaults()
        db.session.commit()

    res = api.patch(f"/api/v1/admin/topics/{tid}", {"slug": "growing-every-day"})
    assert res.status_code == 200, res.get_json()

    with app.app_context():
        assert db.session.scalar(select(func.count(Topic.id))) == count  # no duplicate
        redirect = db.session.scalar(
            select(Redirect).where(Redirect.source_path == "/topics/personal-growth")
        )
        assert (redirect.destination, redirect.status_code, redirect.is_active) == (
            "/topics/growing-every-day",
            301,
            True,
        )
        saved = [i.url for i in db.session.scalars(select(NavigationItem))]
    assert "/topics/personal-growth" not in saved
    assert nav_before and "/topics/growing-every-day" in saved

    assert client.get("/api/v1/topics/personal-growth").status_code == 404
    assert client.get("/api/v1/topics/growing-every-day").status_code == 200
    after = client.get("/api/v1/articles?topic=growing-every-day").get_json()["meta"]["pagination"]
    assert after["total"] == before["total"] > 0
    resolved = client.get("/api/v1/redirects/resolve?path=/topics/personal-growth").get_json()
    assert resolved["data"] == {"destination": "/topics/growing-every-day", "status_code": 301}

    paths = {e["path"] for e in client.get("/api/v1/sitemap").get_json()["data"]}
    assert "/topics/growing-every-day" in paths and "/topics/personal-growth" not in paths
    assert "/topics/personal-growth" not in _nav_urls(client)

    # Renaming back removes the now-wrong redirect instead of creating a loop.
    assert api.patch(f"/api/v1/admin/topics/{tid}", {"slug": "personal-growth"}).status_code == 200
    with app.app_context():
        sources = set(db.session.scalars(select(Redirect.source_path)))
    assert "/topics/personal-growth" not in sources
    assert "/topics/growing-every-day" in sources


def test_a_slug_already_in_use_is_refused(seeded, as_role, app):
    api = as_role("editor")
    with app.app_context():
        tid = db.session.scalar(select(Topic.id).where(Topic.slug == "personal-growth"))
    res = api.patch(f"/api/v1/admin/topics/{tid}", {"slug": "positive-mindset"})
    assert res.status_code == 409
    with app.app_context():
        assert db.session.scalar(select(func.count(Redirect.id))) == 0


# ---- correcting the misspelled Relationships slug -----------------------------------------


def _run(app, *args):
    return app.test_cli_runner().invoke(args=["content", "fix-topic-slug", *args])


def test_fix_topic_slug_corrects_the_typo_safely(seeded, as_role, app, client):
    tid = _rename_seed_topic(app, "relationships-boundaries", TYPO, "Relationships & Connection")
    usage = _topic_usage(app, tid)
    api = as_role("website_manager")
    api.put(
        "/api/v1/admin/navigation/footer",
        {
            "items": [
                {
                    "label": "Explore",
                    "link_type": "heading",
                    "children": [{"label": "Relationships", "url": f"/topics/{TYPO}#start"}],
                }
            ]
        },
    )
    with app.app_context():
        seo = db.session.get(Topic, tid)
        seo.seo_title, seo.seo_description = "Relationships", "Connection that lasts."
        db.session.commit()

    dry = _run(app, TYPO, FIXED, "--dry-run")
    assert dry.exit_code == 0 and "rolled back" in dry.output
    assert client.get(f"/api/v1/topics/{TYPO}").status_code == 200

    done = _run(app, TYPO, FIXED)
    assert done.exit_code == 0, done.output
    assert "renamed" in done.output

    with app.app_context():
        topic = db.session.get(Topic, tid)
        assert topic.slug == FIXED and topic.status == "active"
        assert (topic.seo_title, topic.seo_description) == (
            "Relationships",
            "Connection that lasts.",
        )
        assert (
            db.session.scalar(select(func.count(Topic.id)).where(Topic.slug.in_([TYPO, FIXED])))
            == 1
        )
    assert _topic_usage(app, tid) == usage

    assert client.get(f"/api/v1/topics/{TYPO}").status_code == 404
    assert client.get(f"/api/v1/topics/{FIXED}").get_json()["data"]["slug"] == FIXED
    resolved = client.get(f"/api/v1/redirects/resolve?path=/topics/{TYPO}").get_json()["data"]
    assert resolved == {"destination": f"/topics/{FIXED}", "status_code": 301}
    hop = client.get(f"/_redirect/topics/{TYPO}")
    assert hop.status_code == 301 and hop.headers["Location"] == f"/topics/{FIXED}"
    paths = {e["path"] for e in client.get("/api/v1/sitemap").get_json()["data"]}
    assert f"/topics/{FIXED}" in paths and f"/topics/{TYPO}" not in paths
    footer = _nav(client)["footer"][0]["items"]
    assert footer[0]["url"] == f"/topics/{FIXED}#start"

    # Running it again changes nothing and keeps the redirect.
    again = _run(app, TYPO, FIXED)
    assert again.exit_code == 0 and "already_renamed" in again.output
    assert "'redirect_added': False" in again.output
    with app.app_context():
        assert (
            db.session.scalar(
                select(func.count(Redirect.id)).where(Redirect.source_path == f"/topics/{TYPO}")
            )
            == 1
        )


def test_fix_topic_slug_restores_a_missing_redirect(seeded, app, client):
    _rename_seed_topic(app, "relationships-boundaries", FIXED)
    res = _run(app, TYPO, FIXED)
    assert res.exit_code == 0 and "'redirect_added': True" in res.output
    resolved = client.get(f"/api/v1/redirects/resolve?path=/topics/{TYPO}").get_json()["data"]
    assert resolved["destination"] == f"/topics/{FIXED}"


def test_fix_topic_slug_never_creates_or_merges_topics(seeded, app):
    _rename_seed_topic(app, "relationships-boundaries", TYPO)
    with app.app_context():
        count = db.session.scalar(select(func.count(Topic.id)))
    _rename_seed_topic(app, "personal-growth", FIXED)
    both = _run(app, TYPO, FIXED)
    assert both.exit_code == 1 and "Both" in both.output
    neither = _run(app, "no-such-topic", "still-no-topic")
    assert neither.exit_code == 1
    with app.app_context():
        assert db.session.scalar(select(func.count(Topic.id))) == count
        assert db.session.scalar(select(func.count(Redirect.id))) == 0

"""Pinterest / Instagram connections, social publishing and Instagram imports.

Every platform call goes through ``app.services.social.http.send``, replaced here by a fake:
no test contacts Pinterest or Instagram or needs real credentials.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, MediaAsset, SocialAccount, SocialImport, SocialPost
from app.services.social import accounts, crypto, http, posts

from .conftest import make_photo, make_png
from .test_quotes import _collection, _publish

API = "/api/v1/admin/social"
SITE = "https://thinkpositivealways.com"
PIN_TOKEN = "pina_ACCESS_plaintext_1"
PIN_REFRESH = "pinr_REFRESH_plaintext_1"
IG_TOKEN = "EAAG_SYSTEM_plaintext_1"


class Fake:
    """A scripted stand-in for both platforms' HTTP APIs."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.pins: list[dict] = []
        self.pin_status = 201  # status for POST /v5/pins
        self.pin_saves_on_error = False
        self.unauthorized = False
        self.boards = [{"id": "b1", "name": "Quotes", "privacy": "PUBLIC"}]
        self.ig_media = [
            {
                "id": "1790001",
                "caption": "Start <b>small</b>.\nKeep going. #courage",
                "media_type": "IMAGE",
                "media_url": "https://scontent.cdninstagram.com/v/t51/one.jpg",
                "permalink": "https://www.instagram.com/p/AAA111/",
                "timestamp": "2026-10-01T08:00:00+0000",
                "username": "thinkpositivealways",
            },
            {
                "id": "1790002",
                "caption": "A reel",
                "media_type": "VIDEO",
                "media_url": "https://scontent.cdninstagram.com/v/t51/two.mp4",
                "permalink": "https://www.instagram.com/p/BBB222/",
                "timestamp": "2026-10-02T08:00:00+0000",
                "username": "thinkpositivealways",
            },
        ]
        self.container_status = "FINISHED"
        self.ig_published: list[dict] = []
        # Meta (graph.facebook.com): a non-expiring system-user token by default.
        self.fb_app_id = "test-instagram-app"
        self.fb_token_type = "SYSTEM_USER"
        self.fb_expires_in = 0
        self.fb_scopes = ["instagram_basic", "instagram_content_publish"]
        self.fb_granular: list[dict] = []
        self.fb_debug = True
        self.fb_assigned = [{"id": "178", "username": "thinkpositivealways"}]
        self.fb_pages: list[dict] = []
        self.fb_profiles = {"178": "thinkpositivealways"}
        self.fb_redirect_error = False
        self.fb_token_revoked = False
        self.fb_extend_status = 200
        self.image = make_photo(1080, 1080)
        self.image_type = "image/jpeg"

    def count(self, method, fragment):
        return sum(1 for m, u, _ in self.calls if m == method and fragment in u)

    def __call__(self, method, url, *, params=None, form=None, json_body=None, headers=None,
                 max_bytes=0):  # fmt: skip
        self.calls.append((method, url, {"params": params, "form": form, "json": json_body,
                                         "headers": headers}))  # fmt: skip

        def ok(body, status=200, hdrs=None):
            return http.Response(status, json.dumps(body).encode(), hdrs or {})

        path = urllib.parse.urlparse(url).path
        host = urllib.parse.urlparse(url).hostname
        if host == "api.pinterest.com":
            if path == "/v5/oauth/token":
                assert headers["Authorization"].startswith("Basic ")
                if form.get("grant_type") == "authorization_code" and form["code"] != "good":
                    return ok({"code": 283, "message": "Invalid code"}, 400)
                return ok(
                    {
                        "access_token": PIN_TOKEN if form["grant_type"] != "refresh_token"
                        else "pina_REFRESHED",
                        "refresh_token": PIN_REFRESH,
                        "expires_in": 2592000,
                        "refresh_token_expires_in": 5184000,
                        "scope": "user_accounts:read boards:read boards:write pins:read pins:write",
                    }
                )  # fmt: skip
            if self.unauthorized:
                return ok({"code": 2, "message": "Authentication failed."}, 401)
            if path == "/v5/user_account":
                return ok({"id": "u9", "username": "tpa", "account_type": "BUSINESS"})
            if path == "/v5/boards":
                return ok({"items": self.boards, "bookmark": None})
            if path == "/v5/pins" and method == "POST":
                if self.pin_status >= 400:
                    if self.pin_saves_on_error:
                        self._save_pin(json_body)
                    hdrs = {"Retry-After": "120"} if self.pin_status == 429 else {}
                    return ok({"message": "nope"}, self.pin_status, hdrs)
                return ok(self._save_pin(json_body), 201)
            if path.endswith("/pins") and method == "GET":
                return ok({"items": self.pins})
        if host == "graph.facebook.com":
            tail = path.split("/", 2)[2]
            if tail == "oauth/access_token":
                assert params["client_id"] == "test-instagram-app"
                assert params["client_secret"] == "test-instagram-secret"
                if params.get("grant_type") == "fb_exchange_token":
                    if self.fb_extend_status != 200:
                        return ok({"error": {"message": "try later", "code": 2}},
                                  self.fb_extend_status)  # fmt: skip
                    return ok({"access_token": "EAAG_EXTENDED", "expires_in": 5184000})
                if self.fb_redirect_error and "redirect_uri" in params:
                    return ok({"error": {"message": "Error validating verification code. "
                                         "redirect_uri is not expected", "code": 100}}, 400)  # fmt: skip
                if params["code"] != "good":
                    return ok({"error": {"message": "This authorization code has expired.",
                                         "type": "OAuthException", "code": 100}}, 400)  # fmt: skip
                body = {"access_token": IG_TOKEN, "token_type": "bearer"}
                if self.fb_expires_in:
                    body["expires_in"] = self.fb_expires_in
                return ok(body)
            if tail == "debug_token":
                assert params["access_token"] == "test-instagram-app|test-instagram-secret"
                if not self.fb_debug:
                    return ok({"error": {"message": "nope", "code": 100}}, 400)
                expires_at = (
                    int(datetime.now(UTC).timestamp()) + self.fb_expires_in
                    if self.fb_expires_in
                    else 0
                )
                return ok({"data": {"app_id": self.fb_app_id, "type": self.fb_token_type,
                                    "is_valid": True, "expires_at": expires_at,
                                    "scopes": self.fb_scopes,
                                    "granular_scopes": self.fb_granular}})  # fmt: skip
            if self.fb_token_revoked:
                return ok({"error": {"message": "Error validating access token",
                                     "type": "OAuthException", "code": 190}}, 400)  # fmt: skip
            if tail == "me/assigned_instagram_accounts":
                return ok({"data": self.fb_assigned})
            if tail == "me/accounts":
                return ok({"data": self.fb_pages})
            if tail in self.fb_profiles and (params or {}).get("fields") == "id,username,name":
                return ok({"id": tail, "username": self.fb_profiles[tail], "name": "TPA"})
            if tail == "178/media" and method == "GET":
                return ok({"data": self.ig_published + self.ig_media, "paging": {}})
            if tail == "178/content_publishing_limit":
                return ok({"data": [{"quota_usage": 1, "config": {"quota_total": 100}}]})
            if tail == "178/media" and method == "POST":
                return ok({"id": "c555"})
            if tail == "c555":
                return ok({"status_code": self.container_status})
            if tail == "178/media_publish":
                item = {"id": "m777", "caption": "", "timestamp": "2099-01-01T00:00:00+0000",
                        "permalink": "https://www.instagram.com/p/NEW777/"}  # fmt: skip
                self.ig_published.append(item)
                return ok({"id": "m777"})
            if tail == "m777":
                return ok({"permalink": "https://www.instagram.com/p/NEW777/"})
            for item in self.ig_media:
                if tail == item["id"]:
                    return ok(item)
            return ok({"error": {"message": "Unsupported get request. Object does not exist "
                                 "or missing permissions", "code": 100}}, 400)  # fmt: skip
        if host and host.endswith(".cdninstagram.com"):
            return http.Response(200, self.image, {"Content-Type": self.image_type})
        raise AssertionError(f"unexpected call {method} {url}")

    def _save_pin(self, body):
        pin = {"id": f"p{len(self.pins) + 1}", "created_at": datetime.now(UTC).isoformat(), **body}
        self.pins.append(pin)
        return pin


@pytest.fixture()
def fake(seeded, monkeypatch):
    seeded.config["SITE_URL"] = SITE
    seeded.config["ADMIN_BASE_URL"] = SITE
    fake = Fake()
    monkeypatch.setattr(http, "send", fake)
    monkeypatch.setattr(http, "_resolve", lambda host: ["157.240.1.1"])
    return fake


def _connect(api, platform="pinterest"):
    res = api.post(f"{API}/{platform}/connect")
    assert res.status_code == 200, res.get_json()
    url = res.get_json()["data"]["authorize_url"]
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    done = api.post(f"{API}/{platform}/callback", {"code": "good", "state": state})
    assert done.status_code == 200, done.get_json()
    return done.get_json()["data"]


def _photo(api, width=1200, height=1800, seed=1):
    res = api.upload("/api/v1/admin/media", make_photo(width, height, seed=seed), "quote.jpg")
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]["id"]


def _pin(api, **extra):
    return api.post(f"{API}/posts", {"platform": "pinterest", "board_id": "b1",
                                     "title": "30 quotes about confidence",
                                     "text": "Save these for later.", **extra})  # fmt: skip


# ---- setup, connection and permissions -----------------------------------------------------


def test_missing_server_settings_are_a_setup_state_not_an_error(seeded, as_role):
    seeded.config.update(PINTEREST_CLIENT_ID="", SOCIAL_TOKEN_ENCRYPTION_KEY="")
    api = as_role("super_admin")
    rows = {a["platform"]: a for a in api.get(f"{API}/accounts").get_json()["data"]}
    assert rows["pinterest"]["setup"] == {
        "ready": False,
        "missing": ["PINTEREST_CLIENT_ID", "SOCIAL_TOKEN_ENCRYPTION_KEY"],
    }
    assert not rows["pinterest"]["connected"]
    res = api.post(f"{API}/pinterest/connect")
    assert res.status_code == 400 and "PINTEREST_CLIENT_ID" in res.get_json()["error"]["message"]
    assert api.get("/api/v1/admin/articles").status_code == 200  # the rest of the CMS works


def test_pinterest_oauth_connects_and_stores_encrypted_tokens(fake, app, as_role):
    api = as_role("super_admin")
    url = api.post(f"{API}/pinterest/connect").get_json()["data"]["authorize_url"]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert url.startswith("https://www.pinterest.com/oauth/?")
    assert query["client_id"] == ["test-pinterest-app"] and query["response_type"] == ["code"]
    assert query["redirect_uri"] == [f"{SITE}/admin/integrations/pinterest/callback"]
    assert query["scope"] == ["user_accounts:read,boards:read,boards:write,pins:read,pins:write"]
    assert "secret" not in url
    state = query["state"][0]
    # CSRF: forged, tampered and cross-platform states are refused.
    for bad in ("", "forged", state[:-2] + "xx"):
        res = api.post(f"{API}/pinterest/callback", {"code": "good", "state": bad})
        assert res.status_code == 400, bad
    assert (
        api.post(f"{API}/instagram/callback", {"code": "good", "state": state}).status_code == 400
    )
    denied = api.post(f"{API}/pinterest/callback", {"error": "access_denied", "state": state})
    assert denied.status_code == 400
    assert api.post(f"{API}/pinterest/callback", {"code": "bad", "state": state}).status_code == 400
    res = api.post(f"{API}/pinterest/callback", {"code": "good", "state": state})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()["data"]
    assert body["connected"] and body["account"]["username"] == "tpa"
    assert body["account"]["missing_scopes"] == []
    listing = api.get(f"{API}/accounts").get_data(as_text=True)
    for secret in (PIN_TOKEN, PIN_REFRESH, "test-pinterest-secret"):
        assert secret not in listing and secret not in json.dumps(body)
    with app.app_context():
        row = db.session.scalar(db.select(SocialAccount))
        assert PIN_TOKEN not in row.access_token_enc and PIN_REFRESH not in row.refresh_token_enc
        assert crypto.unseal(row.access_token_enc) == PIN_TOKEN
        assert crypto.unseal(row.refresh_token_enc) == PIN_REFRESH
        actions = set(db.session.scalars(db.select(AuditLog.action)))
        assert {"social.account_connected", "social.connect_failed"} <= actions
        logged = json.dumps([e.details for e in db.session.scalars(db.select(AuditLog))])
        assert PIN_TOKEN not in logged and PIN_REFRESH not in logged


def test_a_state_started_by_another_administrator_is_refused(fake, as_role):
    first = as_role("super_admin")
    second = as_role("super_admin", email="second@example.org")
    url = first.post(f"{API}/pinterest/connect").get_json()["data"]["authorize_url"]
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    res = second.post(f"{API}/pinterest/callback", {"code": "good", "state": state})
    assert res.status_code == 400


def test_role_permissions(fake, as_role):
    owner = as_role("super_admin")
    _connect(owner)
    admin = as_role("administrator")
    assert admin.get(f"{API}/accounts").status_code == 200
    assert admin.get(f"{API}/pinterest/boards").get_json()["data"][0]["name"] == "Quotes"
    assert admin.post(f"{API}/pinterest/connect").status_code == 403
    assert admin.delete(f"{API}/pinterest/account").status_code == 403
    chief = as_role("editor_in_chief")
    assert chief.get(f"{API}/posts").status_code == 200
    assert _pin(chief, media_asset_id=1, destination_url=f"{SITE}/about").status_code == 403
    editor = as_role("editor")
    for path in ("accounts", "posts", "pinterest/boards", "instagram/media"):
        assert editor.get(f"{API}/{path}").status_code == 403, path
    assert _pin(editor, media_asset_id=1).status_code == 403
    assert editor.post(f"{API}/instagram/import", {}).status_code == 403
    assert owner.delete(f"{API}/pinterest/account").status_code == 200
    assert not owner.get(f"{API}/accounts").get_json()["data"][0]["connected"]


def test_tokens_are_refreshed_before_they_expire(fake, app, as_role):
    _connect(as_role("super_admin"))
    with app.app_context():
        row = db.session.scalar(db.select(SocialAccount))
        row.access_expires_at = datetime.now(UTC) + timedelta(hours=2)
        db.session.commit()
        _, token = accounts.access_token("pinterest")
        db.session.commit()
        assert token == "pina_REFRESHED"
        expires = accounts._aware(row.access_expires_at)
        assert expires > datetime.now(UTC) + timedelta(days=20)
    assert fake.calls[-1][2]["form"] == {
        "grant_type": "refresh_token",
        "refresh_token": PIN_REFRESH,
    }


# ---- Pins ----------------------------------------------------------------------------------


def test_a_pin_from_a_quote_collection_links_to_its_canonical_url(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api)
    image = _photo(api)
    quote = _collection(api, app)
    _publish(api, quote)
    with app.app_context():
        assert db.session.query(SocialPost).count() == 0  # publishing on TPA posts nothing
    res = _pin(api, media_asset_id=image, article_id=quote["id"],
               destination_url="https://elsewhere.example/ignored", alt_text="A quote card")  # fmt: skip
    assert res.status_code == 201, res.get_json()
    post = res.get_json()["data"]
    canonical = f"{SITE}/quotes/{quote['slug']}"
    assert post["status"] == "published" and post["destination_url"] == canonical
    assert post["external_id"] == "p1"
    assert post["external_url"] == "https://www.pinterest.com/pin/p1/"
    sent = fake.pins[0]
    assert sent["link"] == canonical and sent["board_id"] == "b1"
    assert sent["title"] == "30 quotes about confidence" and sent["alt_text"] == "A quote card"
    source = sent["media_source"]
    assert source["source_type"] == "image_url"
    assert source["url"].startswith(f"{SITE}/media/") and source["url"].endswith(".jpg")
    with app.app_context():
        actions = list(db.session.scalars(db.select(AuditLog.action)))
        assert "social.post_requested" in actions and "social.post_published" in actions
    history = api.get(f"{API}/posts?view=published&article_id={quote['id']}").get_json()
    assert history["meta"]["total"] == 1
    # The same image, board and link again needs an explicit confirmation.
    again = _pin(api, media_asset_id=image, article_id=quote["id"])
    assert again.status_code == 409 and len(fake.pins) == 1
    assert (
        _pin(api, media_asset_id=image, article_id=quote["id"], allow_repeat=True).status_code
        == 201
    )


def test_article_pins_and_destination_validation(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api)
    image = _photo(api)
    with app.app_context():
        from app.models import Article

        article = db.session.scalar(
            db.select(Article).where(
                Article.status == "published", Article.content_type == "article"
            )
        )
        draft = db.session.scalar(db.select(Article).where(Article.status != "published"))
        article_id, slug, draft_id = article.id, article.slug, draft.id if draft else None
    res = _pin(api, media_asset_id=image, article_id=article_id)
    assert res.get_json()["data"]["destination_url"] == f"{SITE}/articles/{slug}"
    with app.app_context():
        media_path = db.session.get(MediaAsset, image).public_url
    bad = {
        "http://thinkpositivealways.com/about": "https",
        "https://evil.example/quotes/x": "website",
        f"{SITE}{media_path}": "image file",
        f"{SITE}/admin/social": "image file",
        "https://user:pw@thinkpositivealways.com/": "https",
        "": "Choose",
    }
    for url, word in bad.items():
        res = _pin(api, media_asset_id=image, destination_url=url)
        assert res.status_code == 400, url
        assert word in res.get_json()["error"]["details"]["destination_url"][0], url
    if draft_id:
        res = _pin(api, media_asset_id=image, article_id=draft_id)
        assert "article_id" in res.get_json()["error"]["details"]
    res = _pin(api, media_asset_id=image, destination_url=f"{SITE}/about", board_id="nope")
    assert res.status_code == 400 and "board_id" in res.get_json()["error"]["details"]
    res = _pin(api, media_asset_id=999999, destination_url=f"{SITE}/about")
    assert "media_asset_id" in res.get_json()["error"]["details"]
    res = _pin(api, media_asset_id=image, destination_url=f"{SITE}/about", title="<b>x</b>")
    assert "title" in res.get_json()["error"]["details"]
    assert len(fake.pins) == 1


def test_scheduling_queue_cancel_and_no_duplicate_schedules(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api)
    image = _photo(api)
    when = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    res = _pin(api, media_asset_id=image, destination_url=f"{SITE}/about", scheduled_at=when)
    assert res.status_code == 201 and res.get_json()["data"]["status"] == "scheduled"
    post_id = res.get_json()["data"]["id"]
    dup = _pin(api, media_asset_id=image, destination_url=f"{SITE}/about", scheduled_at=when)
    assert dup.status_code == 409
    past = _pin(api, media_asset_id=_photo(api, seed=2), destination_url=f"{SITE}/about",
                scheduled_at="2020-01-01T00:00:00Z")  # fmt: skip
    assert "scheduled_at" in past.get_json()["error"]["details"]
    with app.app_context():
        assert posts.run_due()["published"] == [] and not fake.pins  # not due yet
        post = db.session.get(SocialPost, post_id)
        post.scheduled_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
        assert posts.run_due()["published"] == [post_id]
        assert posts.run_due()["published"] == [] and len(fake.pins) == 1  # sent once
    second = _pin(api, media_asset_id=_photo(api, seed=3), destination_url=f"{SITE}/about",
                  scheduled_at=when)  # fmt: skip
    second_id = second.get_json()["data"]["id"]
    queue = api.get(f"{API}/posts?view=queue").get_json()
    assert [p["id"] for p in queue["data"]] == [second_id] and queue["data"][0]["can_cancel"]
    assert api.post(f"{API}/posts/{second_id}/cancel").get_json()["data"]["status"] == "cancelled"
    assert api.post(f"{API}/posts/{second_id}/cancel").status_code == 409
    assert api.post(f"{API}/posts/{post_id}/retry").status_code == 409  # published: no retry
    with app.app_context():
        db.session.get(SocialPost, second_id).scheduled_at = datetime.now(UTC) - timedelta(1)
        db.session.commit()
        posts.run_due()
    assert len(fake.pins) == 1  # a cancelled post is never sent


def test_an_uncertain_failure_is_checked_before_resending(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api)
    image = _photo(api)
    fake.pin_status, fake.pin_saves_on_error = 503, True  # Pinterest saved it, then errored
    res = _pin(api, media_asset_id=image, destination_url=f"{SITE}/about")
    post = res.get_json()["data"]
    assert post["status"] == "checking" and post["external_id"] is None
    fake.pin_status = 201
    with app.app_context():
        row = db.session.get(SocialPost, post["id"])
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
        assert posts.run_due()["published"] == [post["id"]]
        assert db.session.get(SocialPost, post["id"]).external_id == "p1"
    assert len(fake.pins) == 1 and fake.count("POST", "/v5/pins") == 1  # found, not re-sent


def test_rate_limits_wait_and_definite_failures_can_be_retried(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api)
    image = _photo(api)
    fake.pin_status = 429
    post = _pin(api, media_asset_id=image, destination_url=f"{SITE}/about").get_json()["data"]
    assert (
        post["status"] == "scheduled"
        and post["next_attempt_at"]
        and "rate limit" in post["last_error"]
    )
    with app.app_context():
        assert posts.run_due()["published"] == []  # waits for Retry-After
        assert fake.count("POST", "/v5/pins") == 1
        row = db.session.get(SocialPost, post["id"])
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
        fake.pin_status = 400
        assert posts.run_due()["failed"] == [post["id"]]
    failed = api.get(f"{API}/posts?view=failed").get_json()["data"]
    assert failed[0]["can_retry"] and "nope" in failed[0]["last_error"]
    fake.pin_status = 201
    retried = api.post(f"{API}/posts/{post['id']}/retry").get_json()["data"]
    assert retried["status"] == "published" and len(fake.pins) == 1


def test_an_expired_connection_fails_clearly_and_asks_to_reconnect(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api)
    image = _photo(api)
    when = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    post = _pin(api, media_asset_id=image, destination_url=f"{SITE}/about", scheduled_at=when)
    post_id = post.get_json()["data"]["id"]
    fake.unauthorized = True
    with app.app_context():
        db.session.get(SocialPost, post_id).scheduled_at = datetime.now(UTC) - timedelta(1)
        db.session.commit()
        assert posts.run_due()["failed"] == [post_id]
    account = api.get(f"{API}/accounts").get_json()["data"][0]
    assert not account["connected"] and account["account"]["status"] == "expired"
    assert api.post(f"{API}/posts/{post_id}/retry").status_code == 400
    assert api.get(f"{API}/pinterest/boards").status_code == 400
    fake.unauthorized = False
    assert _connect(api)["connected"]
    assert api.post(f"{API}/posts/{post_id}/retry").get_json()["data"]["status"] == "published"


# ---- Instagram -----------------------------------------------------------------------------


def _ig_row():
    return db.session.scalar(db.select(SocialAccount).where(SocialAccount.platform == "instagram"))


def _ig_start(api):
    url = api.post(f"{API}/instagram/connect").get_json()["data"]["authorize_url"]
    return url, urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]


def _logged(app):
    return json.dumps([e.details for e in db.session.scalars(db.select(AuditLog))])


def test_instagram_needs_the_unified_login_configuration(seeded, as_role):
    seeded.config["INSTAGRAM_CONFIG_ID"] = ""
    api = as_role("super_admin")
    rows = {a["platform"]: a for a in api.get(f"{API}/accounts").get_json()["data"]}
    assert rows["instagram"]["setup"] == {"ready": False, "missing": ["INSTAGRAM_CONFIG_ID"]}
    assert rows["pinterest"]["setup"]["ready"]
    assert api.post(f"{API}/instagram/connect").status_code == 400


def test_instagram_unified_login_connects_with_a_non_expiring_token(fake, app, as_role):
    api = as_role("super_admin")
    url, state = _ig_start(api)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert url.startswith("https://www.facebook.com/v27.0/dialog/oauth?")
    assert query["client_id"] == ["test-instagram-app"]
    assert query["config_id"] == ["test-config-id"] and query["response_type"] == ["code"]
    assert query["redirect_uri"] == [f"{SITE}/admin/integrations/instagram/callback"]
    assert "scope" not in query and "override_default_response_type" not in query
    assert "secret" not in url
    # CSRF: the signed state is still required and bound to the platform.
    for bad in ("", "forged", state[:-2] + "xx"):
        res = api.post(f"{API}/instagram/callback", {"code": "good", "state": bad})
        assert res.status_code == 400, bad
    assert (
        api.post(f"{API}/pinterest/callback", {"code": "good", "state": state}).status_code == 400
    )
    assert not any("graph.facebook.com" in c[1] for c in fake.calls)
    body = _connect(api, "instagram")
    account = body["account"]
    assert body["connected"] and account["username"] == "thinkpositivealways"
    assert account["external_id"] == "178" and account["access_expires_at"] is None
    assert account["scopes"] == ["instagram_basic", "instagram_content_publish"]
    assert account["missing_scopes"] == []
    assert body["scopes_requested"] == ["instagram_basic", "instagram_content_publish"]
    exchange = next(c for c in fake.calls if c[1].endswith("/oauth/access_token"))
    assert exchange[0] == "GET" and exchange[1].startswith("https://graph.facebook.com/v27.0/")
    assert exchange[2]["params"]["redirect_uri"] == query["redirect_uri"][0]
    hosts = {urllib.parse.urlparse(c[1]).hostname for c in fake.calls}
    assert not hosts & {"graph.instagram.com", "api.instagram.com", "www.instagram.com"}
    listing = api.get(f"{API}/accounts").get_data(as_text=True)
    assert IG_TOKEN not in listing and "test-instagram-secret" not in listing
    with app.app_context():
        row = _ig_row()
        assert IG_TOKEN not in row.access_token_enc
        assert crypto.unseal(row.access_token_enc) == IG_TOKEN
        assert row.refresh_token_enc is None and row.access_expires_at is None
        logged = _logged(app)
        assert IG_TOKEN not in logged and "test-instagram-secret" not in logged
        entry = db.session.scalar(
            db.select(AuditLog).where(AuditLog.action == "social.account_connected")
        )
        assert entry.details["grant_type"] == "system_user" and entry.details["expires"] is False


def test_the_override_parameter_is_sent_only_when_configured(fake, app, as_role):
    api = as_role("super_admin")
    app.config["INSTAGRAM_OVERRIDE_RESPONSE_TYPE"] = True
    url, _ = _ig_start(api)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["override_default_response_type"] == ["true"]
    assert query["config_id"] == ["test-config-id"]


def test_a_non_expiring_instagram_token_is_never_refreshed(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api, "instagram")
    before = len(fake.calls)
    with app.app_context():
        assert accounts.refresh_due() == {"refreshed": [], "failed": []}
        _, token = accounts.access_token("instagram")
        assert token == IG_TOKEN
        assert posts.run_due()["tokens"] == {"refreshed": [], "failed": []}
    assert len(fake.calls) == before  # no refresh or exchange request of any kind
    assert not any("refresh_access_token" in c[1] for c in fake.calls)
    assert not any((c[2]["params"] or {}).get("grant_type") for c in fake.calls)


def test_an_expiring_user_token_is_extended_and_renewed_with_the_facebook_exchange(
    fake, app, as_role
):
    api = as_role("super_admin")
    fake.fb_token_type, fake.fb_expires_in = "USER", 3600  # a short-lived user token
    body = _connect(api, "instagram")
    assert body["account"]["access_expires_at"] is not None
    with app.app_context():
        row = _ig_row()
        assert crypto.unseal(row.access_token_enc) == "EAAG_EXTENDED"
        assert accounts._aware(row.access_expires_at) > datetime.now(UTC) + timedelta(days=50)
        # Close to expiry: renewed through fb_exchange_token, never graph.instagram.com.
        row.access_token_enc = crypto.seal("EAAG_OLD")
        row.access_expires_at = datetime.now(UTC) + timedelta(days=2)
        db.session.commit()
        assert accounts.refresh_due() == {"refreshed": ["instagram"], "failed": []}
        db.session.commit()
        renewal = fake.calls[-1]
        assert renewal[2]["params"]["fb_exchange_token"] == "EAAG_OLD"
        assert renewal[1] == "https://graph.facebook.com/v27.0/oauth/access_token"
        # A renewal that fails for now does not block publishing with the valid token.
        row = _ig_row()
        row.access_expires_at = datetime.now(UTC) + timedelta(days=2)
        db.session.commit()
        fake.fb_extend_status = 500
        account, token = accounts.access_token("instagram")
        db.session.commit()
        assert token == "EAAG_EXTENDED" and account.status == "connected"
        # Once it has actually expired the account asks to be reconnected.
        row = _ig_row()
        row.access_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
        with pytest.raises(http.SocialError) as caught:
            accounts.access_token("instagram")
        db.session.commit()
        assert caught.value.reconnect and _ig_row().status == "expired"


def test_instagram_token_exchange_failures_are_reported_without_secrets(fake, app, as_role):
    api = as_role("super_admin")
    _, state = _ig_start(api)
    res = api.post(f"{API}/instagram/callback", {"code": "used-code-123", "state": state})
    assert res.status_code == 400
    message = res.get_json()["error"]["message"]
    assert "Meta refused the authorisation" in message and "expired" in message
    assert "used-code-123" not in message and "test-instagram-secret" not in message
    denied = api.post(
        f"{API}/instagram/callback",
        {"error": "access_denied", "error_description": "Permissions error", "state": state},
    )
    assert denied.status_code == 400
    with app.app_context():
        assert _ig_row() is None
        logged = _logged(app)
        assert "used-code-123" not in logged and "test-instagram-secret" not in logged
        actions = set(db.session.scalars(db.select(AuditLog.action)))
        assert "social.connect_failed" in actions


def test_the_exchange_is_retried_without_redirect_uri_when_meta_rejects_it(fake, as_role):
    api = as_role("super_admin")
    fake.fb_redirect_error = True
    assert _connect(api, "instagram")["connected"]
    exchanges = [c[2]["params"] for c in fake.calls if c[1].endswith("/oauth/access_token")]
    assert len(exchanges) == 2
    assert "redirect_uri" in exchanges[0] and "redirect_uri" not in exchanges[1]


def test_a_token_for_another_app_is_refused(fake, app, as_role):
    api = as_role("super_admin")
    fake.fb_app_id = "some-other-app"
    _, state = _ig_start(api)
    res = api.post(f"{API}/instagram/callback", {"code": "good", "state": state})
    assert res.status_code == 400 and "different Meta app" in res.get_json()["error"]["message"]
    with app.app_context():
        assert _ig_row() is None


@pytest.mark.parametrize(
    ("setup", "expected_id"),
    [
        ({"fb_assigned": [{"id": "178", "username": "thinkpositivealways"}]}, "178"),
        # Nothing assigned: the ids named in the token's granular permissions.
        (
            {
                "fb_assigned": [],
                "fb_granular": [
                    {"scope": "pages_show_list", "target_ids": ["999"]},
                    {"scope": "instagram_basic", "target_ids": ["178"]},
                ],
            },
            "178",
        ),
        # Nothing assigned or named: an account linked to a Facebook Page.
        (
            {
                "fb_assigned": [],
                "fb_pages": [{"id": "55"}, {"instagram_business_account": {"id": "178"}}],
            },
            "178",
        ),
        # Meta lists nothing but an administrator configured the account id.
        ({"fb_assigned": [], "config": "178"}, "178"),
        # Several granted: the configured username decides.
        (
            {
                "fb_assigned": [{"id": "400"}, {"id": "178"}],
                "fb_profiles": {"178": "thinkpositivealways", "400": "another"},
                "config": "@ThinkPositiveAlways",
            },
            "178",
        ),
        # Meta's token inspection is unavailable: the account is still found.
        ({"fb_debug": False}, "178"),
    ],
)
def test_the_instagram_account_is_discovered_and_verified(fake, app, as_role, setup, expected_id):
    api = as_role("super_admin")
    setup = dict(setup)
    app.config["INSTAGRAM_ACCOUNT_ID"] = setup.pop("config", "")
    for key, value in setup.items():
        setattr(fake, key, value)
    body = _connect(api, "instagram")
    assert body["account"]["external_id"] == expected_id
    assert body["account"]["username"] == "thinkpositivealways"
    assert not any(c[1].endswith("/me") for c in fake.calls)  # the old /me shape is not used
    if not fake.fb_debug:
        assert body["account"]["scopes"] == [] and body["account"]["missing_scopes"] == []


@pytest.mark.parametrize(
    ("setup", "words"),
    [
        # No Instagram professional account was granted.
        ({"fb_assigned": []}, "did not grant access to an Instagram professional account"),
        # Listed, but not readable with this token (not eligible / no permission).
        ({"fb_profiles": {}}, "did not grant access to an Instagram professional account"),
        # Several accounts and nothing to choose between them.
        (
            {
                "fb_assigned": [{"id": "400"}, {"id": "178"}],
                "fb_profiles": {"178": "thinkpositivealways", "400": "another"},
            },
            "several Instagram accounts (@another, @thinkpositivealways)",
        ),
        # The configuration did not include the basic permission.
        ({"fb_scopes": ["instagram_content_publish"]}, "instagram_basic permission was not"),
    ],
)
def test_ineligible_or_ambiguous_instagram_accounts_are_not_connected(
    fake, app, as_role, setup, words
):
    api = as_role("super_admin")
    for key, value in setup.items():
        setattr(fake, key, value)
    _, state = _ig_start(api)
    res = api.post(f"{API}/instagram/callback", {"code": "good", "state": state})
    assert res.status_code == 400, res.get_json()
    assert words in res.get_json()["error"]["message"]
    with app.app_context():
        assert _ig_row() is None


def test_a_missing_publish_permission_is_shown_on_the_account(fake, as_role):
    api = as_role("super_admin")
    fake.fb_scopes = ["instagram_basic"]
    body = _connect(api, "instagram")
    assert body["connected"]
    assert body["account"]["missing_scopes"] == ["instagram_content_publish"]


def test_a_revoked_instagram_token_asks_to_reconnect(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api, "instagram")
    square = _photo(api, 1200, 1200)
    fake.fb_token_revoked = True
    assert api.get(f"{API}/instagram/media").status_code == 400
    res = api.post(
        f"{API}/posts", {"platform": "instagram", "text": "Hi", "media_asset_id": square}
    )
    assert res.status_code == 400  # the account is no longer connected
    account = api.get(f"{API}/accounts").get_json()["data"][1]
    assert not account["connected"] and account["account"]["status"] == "expired"
    fake.fb_token_revoked = False
    assert _connect(api, "instagram")["connected"]
    assert api.get(f"{API}/instagram/media").status_code == 200


def test_instagram_permissions_are_enforced(fake, as_role):
    _connect(as_role("super_admin"), "instagram")
    admin = as_role("administrator")
    assert admin.get(f"{API}/instagram/media").status_code == 200
    assert admin.post(f"{API}/instagram/connect").status_code == 403
    assert (
        admin.post(f"{API}/instagram/callback", {"code": "good", "state": "x"}).status_code == 403
    )
    assert admin.delete(f"{API}/instagram/account").status_code == 403
    chief = as_role("editor_in_chief")
    assert chief.get(f"{API}/instagram/media").status_code == 403
    res = chief.post(f"{API}/posts", {"platform": "instagram", "text": "x", "media_asset_id": 1})
    assert res.status_code == 403


def test_instagram_media_is_listed_and_imported_once(fake, app, as_role):
    api = as_role("super_admin")
    assert api.get(f"{API}/instagram/media").status_code == 400  # not connected yet
    _connect(api, "instagram")
    listing = api.get(f"{API}/instagram/media").get_json()["data"]
    image, video = listing["items"]
    assert image["supported"] and image["preview_url"] and not image["imported"]
    assert not video["supported"] and video["preview_url"] is None
    base = {"external_id": "1790001", "alt_text": "A sunrise quote card"}
    res = api.post(f"{API}/instagram/import", base)
    assert "ownership_confirmed" in res.get_json()["error"]["details"]
    res = api.post(f"{API}/instagram/import", {**base, "ownership_confirmed": True, "alt_text": ""})
    assert "alt_text" in res.get_json()["error"]["details"]
    video_import = api.post(
        f"{API}/instagram/import", {**base, "external_id": "1790002", "ownership_confirmed": True}
    )
    assert video_import.status_code == 400
    unknown = api.post(
        f"{API}/instagram/import", {**base, "external_id": "555", "ownership_confirmed": True}
    )
    assert unknown.status_code == 400
    res = api.post(f"{API}/instagram/import", {**base, "ownership_confirmed": True})
    assert res.status_code == 201, res.get_json()
    asset = res.get_json()["data"]
    with app.app_context():
        row = db.session.get(MediaAsset, asset["id"])
        assert row.credit == "@thinkpositivealways on Instagram"
        assert row.source_url == "https://www.instagram.com/p/AAA111/"
        assert row.caption.startswith("Start ‹b›small‹/b›.") and row.alt_text == base["alt_text"]
        assert row.is_managed and "cdninstagram" not in (row.public_url or "")
        assert row.public_url.startswith("/media/")  # served from TPA, not Instagram
        record = db.session.scalar(db.select(SocialImport))
        assert record.external_id == "1790001" and record.media_asset_id == row.id
        assert record.ownership_confirmed
    again = api.post(f"{API}/instagram/import", {**base, "ownership_confirmed": True})
    assert again.status_code == 409
    assert again.get_json()["error"]["details"]["media_asset_id"] == asset["id"]
    assert api.get(f"{API}/instagram/media").get_json()["data"]["items"][0]["imported"]
    # Usable in the Quotes editor between numbered quotes like any Media Library image.
    body = [
        {"type": "list", "ordered": True, "items": [f"Quote {i} — Author" for i in range(1, 6)]},
        {"type": "image", "media_id": asset["id"]},
        {"type": "list", "ordered": True, "start": 6, "items": ["Quote 6 — Author"]},
    ]
    assert _collection(api, app, body=body)["id"]


@pytest.mark.parametrize(
    ("media_url", "content_type"),
    [
        ("https://169.254.169.254/latest/meta-data", "image/jpeg"),
        ("http://scontent.cdninstagram.com/a.jpg", "image/jpeg"),
        ("https://cdninstagram.com.evil.example/a.jpg", "image/jpeg"),
        ("https://scontent.cdninstagram.com:8443/a.jpg", "image/jpeg"),
        ("https://scontent.cdninstagram.com/a.jpg", "text/html"),
    ],
)
def test_imports_refuse_unsafe_or_non_image_sources(fake, app, as_role, media_url, content_type):
    api = as_role("super_admin")
    _connect(api, "instagram")
    fake.ig_media[0]["media_url"] = media_url
    fake.image_type = content_type
    res = api.post(
        f"{API}/instagram/import",
        {"external_id": "1790001", "alt_text": "x", "ownership_confirmed": True},
    )
    assert res.status_code == 400, res.get_json()
    with app.app_context():
        assert db.session.query(SocialImport).count() == 0


def test_imports_refuse_private_addresses_other_accounts_and_big_files(
    fake, app, as_role, monkeypatch
):
    api = as_role("super_admin")
    _connect(api, "instagram")
    payload = {"external_id": "1790001", "alt_text": "x", "ownership_confirmed": True}
    monkeypatch.setattr(http, "_resolve", lambda host: ["10.0.0.5"])
    assert api.post(f"{API}/instagram/import", payload).status_code == 400
    monkeypatch.setattr(http, "_resolve", lambda host: ["157.240.1.1"])
    fake.ig_media[0]["username"] = "someone_else"
    res = api.post(f"{API}/instagram/import", payload)
    assert "own posts" in res.get_json()["error"]["message"]
    fake.ig_media[0]["username"] = "thinkpositivealways"
    fake.image = make_png(40, 40)[:20]  # not a real image
    fake.image_type = "image/png"
    assert api.post(f"{API}/instagram/import", payload).status_code == 400
    assert http.media_url_problem("https://scontent-lhr.xx.fbcdn.net/v/a.jpg") is None


def test_instagram_single_image_post_is_published_and_tracked(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api, "instagram")
    square = _photo(api, 1200, 1200)
    tall = _photo(api, 1000, 1800, seed=5)
    caption = "Start small. Keep going.\n\n#courage #positivity"
    base = {"platform": "instagram", "text": caption}
    res = api.post(f"{API}/posts", {**base, "media_asset_id": tall})
    assert "aspect ratio" in res.get_json()["error"]["details"]["media_asset_id"][0]
    res = api.post(f"{API}/posts", {**base, "media_asset_id": square,
                                    "destination_url": f"{SITE}/about"})  # fmt: skip
    assert "no clickable link" in res.get_json()["error"]["details"]["destination_url"][0]
    res = api.post(f"{API}/posts", {**base, "media_asset_id": square, "text": ""})
    assert "text" in res.get_json()["error"]["details"]
    too_many = " ".join(f"#tag{i}" for i in range(31))
    res = api.post(f"{API}/posts", {**base, "media_asset_id": square, "text": too_many})
    assert "30 hashtags" in res.get_json()["error"]["details"]["text"][0]
    fake.container_status = "IN_PROGRESS"
    res = api.post(f"{API}/posts", {**base, "media_asset_id": square})
    assert res.status_code == 201, res.get_json()
    post = res.get_json()["data"]
    assert post["status"] == "scheduled" and post["destination_url"] is None  # still processing
    container = next(c for c in fake.calls if c[0] == "POST" and c[1].endswith("/178/media"))
    assert container[2]["form"]["caption"] == caption
    assert container[2]["form"]["image_url"].startswith(f"{SITE}/media/")
    assert container[2]["form"]["image_url"].endswith(".jpg")
    fake.container_status = "FINISHED"
    with app.app_context():
        row = db.session.get(SocialPost, post["id"])
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
        assert posts.run_due()["published"] == [post["id"]]
        assert posts.run_due()["published"] == []
    done = api.get(f"{API}/posts/{post['id']}").get_json()["data"]
    assert done["external_id"] == "m777"
    assert done["external_url"] == "https://www.instagram.com/p/NEW777/"
    assert fake.count("POST", "/178/media_publish") == 1
    assert sum(1 for c in fake.calls if c[0] == "POST" and c[1].endswith("/178/media")) == 1


def test_instagram_processing_errors_are_reported(fake, app, as_role):
    api = as_role("super_admin")
    _connect(api, "instagram")
    fake.container_status = "ERROR"
    res = api.post(
        f"{API}/posts",
        {"platform": "instagram", "text": "Caption", "media_asset_id": _photo(api, 1200, 1200)},
    )
    post = res.get_json()["data"]
    assert post["status"] == "failed" and "could not process" in post["last_error"]
    assert fake.count("POST", "/178/media_publish") == 0


def test_posting_requires_a_connected_account(fake, as_role):
    api = as_role("super_admin")
    res = _pin(api, media_asset_id=_photo(api), destination_url=f"{SITE}/about")
    assert res.status_code == 400 and "Connect Pinterest" in res.get_json()["error"]["message"]

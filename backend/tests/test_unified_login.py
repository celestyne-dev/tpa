"""Batch 08.1: one public login entry, two separate authentication systems.

Customers sign in at /login (customer API), staff at /admin/login (admin API). The
browser chooses the context explicitly; the server never guesses the account type from a
password match, never reveals that an email belongs to staff, and keeps sessions, CSRF
tokens and rate limits independent.
"""

from app.extensions import db
from app.models import Customer
from app.services import navigation_service, seo_service
from app.services.mail import MemoryBackend

from .conftest import PASSWORD, Api, Shopper, csrf, login, make_user, register_customer

SHARED = "same.person@example.org"
STAFF_PASSWORD = "Staff-Only-Passphrase-42"


def _customer_login(client, email, password, **kw):
    return client.post("/api/v1/account/login", json={"email": email, "password": password}, **kw)


def _both_accounts(app, *, staff_roles=("editor",), staff_password=STAFF_PASSWORD):
    register_customer(app, SHARED, verify=True, test_account=False)
    make_user(app, SHARED, list(staff_roles), password=staff_password)


def test_same_email_uses_the_selected_context_only(seeded):
    _both_accounts(seeded)
    browser = seeded.test_client()

    # Each system accepts only its own password; the other one is a generic failure.
    staff_pw_as_customer = _customer_login(browser, SHARED, STAFF_PASSWORD)
    unknown_customer = _customer_login(browser, "nobody@example.org", STAFF_PASSWORD)
    assert staff_pw_as_customer.status_code == unknown_customer.status_code == 401
    assert staff_pw_as_customer.get_json() == unknown_customer.get_json()
    assert browser.get_cookie("tpa_customer") is None

    customer_pw_as_staff = login(browser, SHARED, PASSWORD)
    unknown_staff = login(browser, "nobody@example.org", PASSWORD)
    assert customer_pw_as_staff.status_code == unknown_staff.status_code == 401
    assert customer_pw_as_staff.get_json() == unknown_staff.get_json()
    assert browser.get_cookie("access_token_cookie") is None

    # Customer context → customer session only.
    ok = _customer_login(browser, SHARED, PASSWORD)
    assert ok.status_code == 200
    assert "roles" not in ok.get_json()["data"]["customer"]  # nothing hints at staff access
    assert browser.get("/api/v1/account/me").status_code == 200
    assert browser.get("/api/v1/admin/auth/me").status_code == 401
    assert browser.get("/api/v1/admin/dashboard").status_code == 401


def test_same_password_in_both_systems_still_signs_into_one(seeded):
    _both_accounts(seeded, staff_password=PASSWORD)
    staff_browser = seeded.test_client()
    res = login(staff_browser, SHARED, PASSWORD)
    assert res.status_code == 200 and res.get_json()["data"]["user"]["roles"] == ["editor"]
    assert staff_browser.get("/api/v1/admin/auth/me").status_code == 200
    assert staff_browser.get("/api/v1/account/me").status_code == 401
    assert staff_browser.get_cookie("tpa_customer") is None

    customer_browser = seeded.test_client()
    assert _customer_login(customer_browser, SHARED, PASSWORD).status_code == 200
    assert customer_browser.get("/api/v1/admin/auth/me").status_code == 401
    assert customer_browser.get_cookie("access_token_cookie") is None


def test_rate_limits_are_independent_per_system(seeded):
    _both_accounts(seeded)
    browser = seeded.test_client()
    for _ in range(5):  # RATELIMIT_LOGIN is 5 per minute per client address
        assert login(browser, SHARED, "wrong-password").status_code == 401
    assert login(browser, SHARED, STAFF_PASSWORD).status_code == 429
    # The customer login keeps its own budget for the same address and email…
    assert _customer_login(browser, SHARED, PASSWORD).status_code == 200
    # …and exhausting it does not unlock or affect the staff limit.
    other = seeded.test_client()
    for _ in range(5):
        assert _customer_login(other, SHARED, "wrong-password").status_code in (401, 429)
    assert _customer_login(other, SHARED, PASSWORD).status_code == 429
    assert login(browser, SHARED, STAFF_PASSWORD).status_code == 429


def test_logout_in_one_system_leaves_the_other_alone(seeded):
    _both_accounts(seeded)
    browser = seeded.test_client()
    assert login(browser, SHARED, STAFF_PASSWORD).status_code == 200
    assert _customer_login(browser, SHARED, PASSWORD).status_code == 200
    staff, shopper = Api(browser), Shopper(browser)

    assert shopper.post("/api/v1/account/logout").status_code == 200
    assert browser.get("/api/v1/account/me").status_code == 401
    assert browser.get("/api/v1/admin/auth/me").status_code == 200

    assert _customer_login(browser, SHARED, PASSWORD).status_code == 200
    assert staff.post("/api/v1/admin/auth/logout").status_code == 200
    assert browser.get("/api/v1/admin/auth/me").status_code == 401
    assert browser.get("/api/v1/account/me").status_code == 200


def test_csrf_tokens_and_origins_do_not_cross_systems(seeded):
    _both_accounts(seeded)
    browser = seeded.test_client()
    assert login(browser, SHARED, STAFF_PASSWORD).status_code == 200
    assert _customer_login(browser, SHARED, PASSWORD).status_code == 200
    customer_token = browser.get_cookie("tpa_customer_csrf").value
    admin_token = csrf(browser)["X-CSRF-TOKEN"]
    assert customer_token != admin_token

    # The customer CSRF value never authorises an admin mutation (in either header).
    for headers in ({"X-Customer-CSRF": customer_token}, {"X-CSRF-TOKEN": customer_token}):
        change = browser.post(
            "/api/v1/admin/auth/change-password",
            json={"current_password": STAFF_PASSWORD, "new_password": "Another-Long-Pass-77"},
            headers=headers,
        )
        assert change.status_code in (401, 403), change.get_json()
    assert login(seeded.test_client(), SHARED, STAFF_PASSWORD).status_code == 200  # unchanged
    # …and the admin CSRF value never authorises a customer mutation.
    res = browser.patch(
        "/api/v1/account/me", json={"display_name": "X"}, headers={"X-Customer-CSRF": admin_token}
    )
    assert res.status_code == 403
    # Both sign-in endpoints refuse untrusted browser origins.
    evil = {"Origin": "https://evil.example"}
    assert _customer_login(seeded.test_client(), SHARED, PASSWORD, headers=evil).status_code == 403
    staff_evil = seeded.test_client().post(
        "/api/v1/admin/auth/login",
        json={"email": SHARED, "password": STAFF_PASSWORD},
        headers=evil,
    )
    assert staff_evil.status_code == 403


def test_limited_staff_get_only_their_permissions(seeded):
    make_user(seeded, "writer@example.org", ["editor"])
    browser = seeded.test_client()
    me = login(browser, "writer@example.org").get_json()["data"]["user"]
    assert "users.manage" not in me["permissions"] and "storage.view" not in me["permissions"]
    assert "articles.view" in me["permissions"]
    assert browser.get("/api/v1/admin/articles").status_code == 200
    for path in ("/api/v1/admin/users", "/api/v1/admin/storage", "/api/v1/admin/orders"):
        assert browser.get(path).status_code == 403, path

    make_user(seeded, "owner@example.org", ["super_admin"])
    owner = seeded.test_client()
    assert login(owner, "owner@example.org").status_code == 200
    for path in ("/api/v1/admin/users", "/api/v1/admin/storage", "/api/v1/admin/orders"):
        assert owner.get(path).status_code == 200, path


def test_recovery_never_reveals_staff_accounts(seeded):
    make_user(seeded, "staff.only@example.org", ["editor"])
    client = seeded.test_client()
    MemoryBackend.outbox.clear()
    staff_only = client.post(
        "/api/v1/account/password-reset", json={"email": "staff.only@example.org"}
    )
    unknown = client.post("/api/v1/account/password-reset", json={"email": "ghost@example.org"})
    assert staff_only.status_code == unknown.status_code == 200
    assert staff_only.get_json() == unknown.get_json()
    assert MemoryBackend.outbox == []  # the customer flow never touches staff accounts
    with seeded.app_context():
        assert (
            db.session.scalar(db.select(Customer).where(Customer.email == "staff.only@example.org"))
            is None
        )
    # Staff passwords are reset by an administrator; there is no public request endpoint.
    for path in ("/api/v1/admin/auth/password-reset", "/api/v1/admin/auth/password-reset/request"):
        assert client.post(path, json={"email": "staff.only@example.org"}).status_code in (404, 405)


def test_staff_login_link_is_a_default_footer_link_without_warnings(seeded, client):
    legal = client.get("/api/v1/site").get_json()["data"]["navigation"]["legal"]
    assert {"label": "Staff login", "url": "/admin/login"}.items() <= legal[0].items()
    with seeded.app_context():
        items = [{"link_type": "internal", "url": u} for u in ("/admin/login", "/login")]
        assert navigation_service.link_warnings(items) == []
        assert seo_service.broken_links(["/admin/login", "/login", "/account/settings"]) == []

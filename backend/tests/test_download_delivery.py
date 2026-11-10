"""Batch 15: download links vs. the purchase allowance.

The confirmed incident: one browser download produced five requests within seconds, which
used up the link, and the allowance (1) had already been used when the link was created,
so the customer could never get the file. Link uses and the allowance are now separate:
retries, resumed (Range) and parallel requests never use the allowance twice, refused
requests never use it, and a new link can always be requested while access is valid.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from app.extensions import db
from app.models import DownloadEvent, DownloadGrant, Entitlement, ProductFileVersion, SiteSetting
from app.services.commerce.downloads import _is_continuation
from app.storage.private_files import get_private_storage

from .conftest import register_customer
from .test_commerce_checkout import _library_file, _paid_order, shop  # noqa: F401


def _limit(app, value):
    with app.app_context():
        db.session.add(SiteSetting(key="payments.download_limit", value=value))
        db.session.commit()


def _link(shopper, item, version):
    res = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]["url"]


def _count(app, item):
    with app.app_context():
        return db.session.get(Entitlement, item["id"]).download_count


def _served(app):
    with app.app_context():
        return [
            e.reason
            for e in db.session.scalars(
                db.select(DownloadEvent)
                .where(DownloadEvent.status == "served")
                .order_by(DownloadEvent.id)
            )
        ]


def _age_downloads(app, hours=2):
    """Move every delivery back in time, past the retry window."""
    with app.app_context():
        for event in db.session.scalars(db.select(DownloadEvent)):
            event.created_at = datetime.now(UTC) - timedelta(hours=hours)
        db.session.commit()


def _bought(shop, client, limit=None):  # noqa: F811
    if limit is not None:
        _limit(shop["app"], limit)
    _paid_order(shop, client)
    item, version = _library_file(shop["shopper"])
    return shop["shopper"], item, version


def test_range_header_classification():
    assert _is_continuation(None) is False
    assert _is_continuation("bytes=0-") is False
    assert _is_continuation("bytes=0-1023") is False
    assert _is_continuation("bytes=1024-") is True
    assert _is_continuation("bytes=-500") is True  # suffix range
    assert _is_continuation("items=1-2") is True  # unknown: the finite cap applies


def test_creating_a_link_never_uses_the_allowance_delivery_does_once(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client, limit=1)
    app = shop["app"]
    for _ in range(3):  # links that are never used cost nothing
        url = _link(shopper, item, version)
    assert _count(app, item) == 0
    res = shopper.get(url)
    assert res.status_code == 200 and res.data.startswith(b"%PDF")
    assert _count(app, item) == 1
    assert _served(app) == ["counted"]


def test_guest_download_uses_the_allowance_on_delivery(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client, limit=1)
    app = shop["app"]
    url = _link(shopper, item, version)
    with app.app_context():
        db.session.scalar(db.select(DownloadGrant)).guest = True  # as from a guest access link
        db.session.commit()
    other = app.test_client()  # guest grants need no session
    assert other.get(url).status_code == 200
    assert other.get(url).status_code == 200  # the browser asking again
    assert _count(app, item) == 1
    assert _served(app) == ["counted", "retry"]


def test_the_incident_five_requests_then_a_new_link(shop, client):  # noqa: F811
    """Five requests in seconds, the link used up, then a new link: the customer still gets
    the file and has used one download."""
    shopper, item, version = _bought(shop, client, limit=1)
    app = shop["app"]
    url = _link(shopper, item, version)
    for _ in range(5):
        assert shopper.get(url).status_code == 200
    used_up = shopper.get(url)
    assert used_up.status_code == 410
    assert used_up.get_json()["error"]["code"] == "download_link_used_up"
    assert _count(app, item) == 1
    again = _link(shopper, item, version)  # not "limit reached": within the retry window
    assert shopper.get(again).status_code == 200
    assert _count(app, item) == 1
    assert _served(app) == ["counted"] + ["retry"] * 5


def test_interrupted_download_resumes_with_ranges(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client, limit=1)
    app = shop["app"]
    url = _link(shopper, item, version)
    whole = shopper.get(url).data
    first = shopper.get(url, headers={"Range": "bytes=0-9"})
    assert first.status_code == 206 and first.data == whole[:10]
    rest = shopper.get(url, headers={"Range": "bytes=10-"})
    assert rest.status_code == 206 and first.data + rest.data == whole
    assert rest.headers["Content-Disposition"].startswith("attachment;")
    assert _count(app, item) == 1
    # The link expires mid-download: a new link resumes it without using another download.
    with app.app_context():
        db.session.scalar(db.select(DownloadGrant)).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db.session.commit()
    assert shopper.get(url, headers={"Range": "bytes=10-"}).status_code == 410
    again = _link(shopper, item, version)
    assert shopper.get(again, headers={"Range": "bytes=10-"}).status_code == 206
    assert _count(app, item) == 1


def test_range_requests_have_their_own_finite_cap(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client)
    app = shop["app"]
    app.config.update(DOWNLOAD_LINK_MAX_USES=2, DOWNLOAD_LINK_MAX_RANGE_REQUESTS=3)
    url = _link(shopper, item, version)
    assert shopper.get(url).status_code == 200  # start 1
    # Parallel / resumed parts do not use up the link's starts...
    for start in (5, 10, 15):
        assert shopper.get(url, headers={"Range": f"bytes={start}-"}).status_code == 206
    assert shopper.get(url, headers={"Range": "bytes=0-"}).status_code == 206  # start 2
    # ...but both are finite.
    for headers in ({}, {"Range": "bytes=20-"}):
        res = shopper.get(url, headers=headers)
        assert res.status_code == 410
        assert res.get_json()["error"]["code"] == "download_link_used_up"
    assert _count(app, item) == 1


def test_expired_link_is_reported_as_expired_and_costs_nothing(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client, limit=1)
    app = shop["app"]
    url = _link(shopper, item, version)
    with app.app_context():
        db.session.scalar(db.select(DownloadGrant)).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db.session.commit()
    res = shopper.get(url)
    assert res.status_code == 410 and res.get_json()["error"]["code"] == "download_link_expired"
    assert _count(app, item) == 0
    # The browser navigated to the link: a readable page, not JSON.
    page = shopper.get(url, headers={"Sec-Fetch-Mode": "navigate", "Accept": "text/html"})
    assert page.status_code == 410 and page.mimetype == "text/html"
    text = page.get_data(as_text=True)
    assert "This download link has expired" in text and "/account/library" in text
    assert page.headers["Cache-Control"] == "private, no-store"
    # A new link works and uses the one download.
    assert shopper.get(_link(shopper, item, version)).status_code == 200
    assert _count(app, item) == 1


def test_missing_file_is_refused_without_using_anything(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client, limit=1)
    app = shop["app"]
    url = _link(shopper, item, version)
    with app.app_context():
        grant = db.session.scalar(db.select(DownloadGrant))
        key = db.session.get(ProductFileVersion, grant.file_version_id).storage_key
        path = get_private_storage().path(key)
    data = path.read_bytes()
    path.unlink()
    res = shopper.get(url)
    assert res.status_code == 503
    assert res.get_json()["error"]["code"] == "download_file_unavailable"
    with app.app_context():
        assert db.session.scalar(db.select(DownloadGrant)).use_count == 0
        reasons = [e.reason for e in db.session.scalars(db.select(DownloadEvent))]
        assert "file_missing" in reasons
    assert _count(app, item) == 0
    path.write_bytes(data)
    assert shopper.get(url).status_code == 200  # the same link still works afterwards
    assert _count(app, item) == 1


def test_purchase_limit_counts_deliveries_outside_the_retry_window(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client, limit=2)
    app = shop["app"]
    assert shopper.get(_link(shopper, item, version)).status_code == 200
    assert shopper.get(_link(shopper, item, version)).status_code == 200  # a retry
    assert _count(app, item) == 1
    _age_downloads(app)  # a download on another day
    assert shopper.get(_link(shopper, item, version)).status_code == 200
    assert _count(app, item) == 2
    # Within the window of the second download, a new link is still possible and free...
    late = _link(shopper, item, version)
    _age_downloads(app)
    # ...but once the window has passed, the used-up allowance applies, both to new links
    # and to a link created earlier.
    res = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert res.status_code == 403 and res.get_json()["error"]["code"] == "download_limit_reached"
    res = shopper.get(late)
    assert res.status_code == 403 and res.get_json()["error"]["code"] == "download_limit_reached"
    assert _count(app, item) == 2  # never more than the limit


def test_other_accounts_and_anonymous_visitors_get_nothing(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client, limit=1)
    app = shop["app"]
    url = _link(shopper, item, version)
    thief = register_customer(app, "thief@example.com")
    assert thief.get(url).status_code == 403
    assert client.get(url).status_code == 403
    res = thief.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert res.status_code == 404
    assert _count(app, item) == 0
    assert shopper.get(url).status_code == 200  # the owner's link was not used up by them


def test_revoked_entitlement_blocks_issued_links_without_using_the_allowance(
    shop,  # noqa: F811
    client,
    as_role,
):
    shopper, item, version = _bought(shop, client, limit=1)
    app = shop["app"]
    url = _link(shopper, item, version)
    support = as_role("orders_manager")
    assert (
        support.post(
            f"/api/v1/admin/entitlements/{item['id']}/revoke", {"reason": "Chargeback"}
        ).status_code
        == 200
    )
    assert shopper.get(url).status_code == 403
    assert shopper.get(url, headers={"Range": "bytes=10-"}).status_code == 403
    assert _count(app, item) == 0


def test_concurrent_requests_count_one_delivery(shop, client):  # noqa: F811
    shopper, item, version = _bought(shop, client, limit=3)
    app = shop["app"]
    url = _link(shopper, item, version)
    with app.app_context():
        db.session.scalar(db.select(DownloadGrant)).guest = True  # no session to share
        db.session.commit()
    results, barrier = [], threading.Barrier(5)

    def worker(n):
        c = app.test_client()
        barrier.wait()
        headers = {"Range": f"bytes={n * 3}-"} if n % 2 else {}
        results.append(c.get(url, headers=headers).status_code)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 200, 200, 206, 206], results
    with app.app_context():
        postgres = db.engine.dialect.name == "postgresql"
    count = _count(app, item)
    # PostgreSQL locks the entitlement row: exactly one delivery is counted. The in-memory
    # SQLite used by quick local runs shares one connection between threads, so only the
    # hard guarantee is checked there: never more than the allowance.
    assert count == 1 if postgres else 1 <= count <= 3

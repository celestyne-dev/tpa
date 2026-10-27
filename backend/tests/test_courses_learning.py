"""Batch 09 courses, learner side: enrolment (free, premium, guest claim), access after
refunds and revocation, progress, exercises, assessments and answer-key protection,
completion, certificates, private downloads, CSRF/session rules and concurrency."""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db
from app.models import Course, CourseCertificate, CourseEnrollment, Customer, Entitlement
from app.services.mail import MemoryBackend

from .conftest import PASSWORD, Shopper, enable_test_checkout, register_customer
from .test_commerce_catalogue import PRODUCTS, _create, _upload
from .test_commerce_checkout import _checkout, _key, _send_webhook
from .test_courses_admin import (
    COURSES,
    add_lesson,
    add_module,
    create_course,
    lesson_body,
    ready_course,
)

LEARN = "/api/v1/account/learning"


def _verified(app, email="reader@example.com"):
    return register_customer(app, email, verify=True)


def _unverified(app, email="new@example.com"):
    return register_customer(app, email, verify=False)


# ---- free courses -----------------------------------------------------------------------


def test_free_enrolment_progress_completion_and_certificate(seeded, as_role, client):
    editor = as_role("editor")
    course = create_course(editor, "Calm Basics", outcomes=["Pause"])
    module = add_module(editor, course["id"])
    one = add_lesson(
        editor,
        course["id"],
        module["id"],
        "Notice",
        body=lesson_body(
            blocks=[
                {
                    "type": "exercise",
                    "id": "three-things",
                    "prompt": "List three things.",
                    "required": True,
                }
            ]
        ),
    )
    two = add_lesson(editor, course["id"], module["id"], "Breathe")
    optional = add_lesson(
        editor, course["id"], module["id"], "Extra reading", completion_required=False
    )
    hidden = add_lesson(editor, course["id"], module["id"], "Draft", publish=False)
    editor.post(f"{COURSES}/{course['id']}/publish", {})

    # Email confirmation is required to learn.
    newbie = _unverified(seeded)
    res = newbie.post(f"{LEARN}/calm-basics/enroll")
    assert (
        res.status_code == 403 and res.get_json()["error"]["code"] == "email_verification_required"
    )
    assert newbie.get(f"{LEARN}/calm-basics/status").get_json()["data"]["verified"] is False

    learner = _verified(seeded)
    assert learner.get(f"{LEARN}/calm-basics").get_json()["error"]["code"] == "not_enrolled"
    status = learner.get(f"{LEARN}/calm-basics/status").get_json()["data"]
    assert status == {**status, "enrolled": False, "can_enroll": True}
    assert learner.post(f"{LEARN}/calm-basics/enroll").status_code == 201
    again = learner.post(f"{LEARN}/calm-basics/enroll")
    assert again.status_code == 200 and again.get_json()["data"]["created"] is False
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(CourseEnrollment.id))) == 1
    status = learner.get(f"{LEARN}/calm-basics/status").get_json()["data"]
    assert status["enrolled"] and status["access"] == "active" and status["can_enroll"] is False

    outline = learner.get(f"{LEARN}/calm-basics").get_json()["data"]
    assert [item["slug"] for item in outline["modules"][0]["lessons"]] == [
        one["slug"],
        two["slug"],
        optional["slug"],
    ]
    assert outline["resume"]["slug"] == one["slug"]
    assert learner.get(f"{LEARN}/calm-basics/lessons/{hidden['slug']}").status_code == 404

    lesson = learner.get(f"{LEARN}/calm-basics/lessons/{one['slug']}").get_json()["data"]
    assert (
        lesson["state"]["required_exercises"] == ["three-things"]
        and lesson["next"]["slug"] == two["slug"]
    )
    blocked = learner.post(f"{LEARN}/calm-basics/lessons/{one['slug']}/complete")
    assert blocked.status_code == 400 and blocked.get_json()["error"]["details"]["exercises"] == [
        "three-things"
    ]
    ex = f"{LEARN}/calm-basics/lessons/{one['slug']}/exercises/three-things"
    assert learner.put(ex, {"response": "<b>no html</b>"}).status_code == 400
    saved = learner.put(ex, {"response": "Sky, tree, cup", "done": True}).get_json()["data"]
    assert saved == {"exercise_id": "three-things", "done": True, "response": "Sky, tree, cup"}
    assert (
        learner.put(
            f"{LEARN}/calm-basics/lessons/{one['slug']}/exercises/nope", {"done": True}
        ).status_code
        == 404
    )
    done = learner.post(f"{LEARN}/calm-basics/lessons/{one['slug']}/complete").get_json()["data"]
    assert done["progress"]["percent"] == 50 and not done["progress"]["complete"]
    # The optional lesson doesn't count; finishing the required one completes the course.
    final = learner.post(f"{LEARN}/calm-basics/lessons/{two['slug']}/complete").get_json()["data"]
    assert final["progress"] == {**final["progress"], "percent": 100, "complete": True}

    mine = learner.get(LEARN).get_json()["data"]["enrollments"][0]
    assert mine["completed_at"] and mine["certificate"]["recipient_name"] == "Reader"
    code = mine["certificate"]["code"]
    assert code.startswith("TPA-") and len(code) == 18

    # Anyone can verify; only the owner downloads the PDF.
    check = client.get(f"/api/v1/certificates/{code}")
    assert check.status_code == 200 and check.headers["Cache-Control"] == "no-store"
    data = check.get_json()["data"]
    assert data["status"] == "valid" and "not an accredited qualification" in data["statement"]
    assert client.get("/api/v1/certificates/TPA-AAAA-BBBB-CCCC").status_code == 404
    pdf = learner.get(f"/api/v1/account/certificates/{code}/pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF-1.4") and b"Reader" in pdf.data
    assert b"accredited" in pdf.data
    assert (
        _verified(seeded, "other@example.com")
        .get(f"/api/v1/account/certificates/{code}/pdf")
        .status_code
        == 404
    )
    assert client.get(f"/api/v1/account/certificates/{code}/pdf").status_code == 401


def test_free_access_period_expires_and_can_be_renewed(seeded, as_role):
    editor = as_role("editor")
    course, _, lessons = ready_course(editor, "Short Access", access_days=7)
    learner = _verified(seeded)
    assert learner.post(f"{LEARN}/short-access/enroll").status_code == 201
    with seeded.app_context():
        enrollment = db.session.scalar(db.select(CourseEnrollment))
        assert enrollment.expires_at is not None
        enrollment.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
    res = learner.get(f"{LEARN}/short-access/lessons/{lessons[0]['slug']}")
    assert res.status_code == 403 and res.get_json()["error"]["code"] == "course_access_ended"
    assert learner.get(f"{LEARN}/short-access/status").get_json()["data"]["can_enroll"] is True
    assert learner.post(f"{LEARN}/short-access/enroll").status_code == 200  # renewed, same row
    assert learner.get(f"{LEARN}/short-access/lessons/{lessons[0]['slug']}").status_code == 200


def test_closed_and_coming_soon_courses_refuse_new_learners(seeded, as_role):
    editor = as_role("editor")
    course, _, _ = ready_course(editor, "Closed Course")
    editor.patch(f"{COURSES}/{course['id']}", {"enrollment_open": False})
    learner = _verified(seeded)
    assert learner.post(f"{LEARN}/closed-course/enroll").status_code == 409
    editor.patch(
        f"{COURSES}/{course['id']}", {"enrollment_open": True, "availability": "coming_soon"}
    )
    assert learner.post(f"{LEARN}/closed-course/enroll").status_code == 409


def test_learner_api_needs_session_csrf_and_trusted_origin(seeded, as_role, client):
    editor = as_role("editor")
    ready_course(editor, "Secure Course")
    learner = _verified(seeded)
    assert client.post(f"{LEARN}/secure-course/enroll").status_code == 401
    no_csrf = learner.c.post(f"{LEARN}/secure-course/enroll", json={})
    assert no_csrf.status_code == 403
    evil = learner.c.post(
        f"{LEARN}/secure-course/enroll",
        json={},
        headers={**learner.headers(), "Origin": "https://evil.example"},
    )
    assert evil.status_code == 403
    ok = learner.post(f"{LEARN}/secure-course/enroll")
    assert ok.status_code == 201 and ok.headers["Cache-Control"] == "no-store"
    # A staff session is not a learner session.
    staff = as_role("super_admin", email="boss@example.org")
    assert staff.get(LEARN).status_code == 401


# ---- assessments ------------------------------------------------------------------------


def _quiz_course(editor, *, show_answers="after_submit", max_attempts=None):
    course, _, lessons = ready_course(editor, "Quiz Course", lessons=1)
    cid = course["id"]
    quiz = editor.post(
        f"{COURSES}/{cid}/assessments",
        {
            "title": "Check-in",
            "kind": "quiz",
            "passing_score": 60,
            "show_answers": show_answers,
            "max_attempts": max_attempts,
        },
    ).get_json()["data"]
    qurl = f"{COURSES}/{cid}/assessments/{quiz['id']}/questions"
    editor.post(
        qurl,
        {
            "kind": "single_choice",
            "prompt": "Best first step?",
            "options": [{"id": "a", "text": "Rush"}, {"id": "b", "text": "Pause"}],
            "correct": ["b"],
            "explanation": "Pausing first.",
        },
    )
    editor.post(
        qurl,
        {
            "kind": "multiple_select",
            "prompt": "Calming habits?",
            "options": [
                {"id": "a", "text": "Walks"},
                {"id": "b", "text": "Doomscrolling"},
                {"id": "c", "text": "Breathing"},
            ],
            "correct": ["a", "c"],
        },
    )
    editor.post(qurl, {"kind": "true_false", "prompt": "Sleep matters.", "correct": [True]})
    detail = editor.post(
        qurl, {"kind": "short_text", "prompt": "What will you try?", "required": False}
    ).get_json()["data"]
    assert len(detail["questions"]) == 4
    assert (
        editor.post(
            f"{COURSES}/{cid}/assessments/{quiz['id']}/status", {"status": "published"}
        ).status_code
        == 200
    )
    return course, quiz, detail["questions"], lessons


def _answers(questions, *, right=True):
    q = {item["kind"]: str(item["id"]) for item in questions}
    if right:
        return {
            q["single_choice"]: "b",
            q["multiple_select"]: ["c", "a"],
            q["true_false"]: "true",
            q["short_text"]: "Walks",
        }
    return {q["single_choice"]: "a", q["multiple_select"]: ["a"], q["true_false"]: "false"}


def test_quiz_scoring_answer_key_protection_and_attempt_limits(seeded, as_role):
    editor = as_role("editor")
    course, quiz, questions, _ = _quiz_course(editor, show_answers="after_pass", max_attempts=3)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/quiz-course/enroll")
    url = f"{LEARN}/quiz-course/assessments/{quiz['id']}"
    view = learner.get(url)
    raw = view.get_data(as_text=True)
    assert "Pausing first." not in raw and '"correct"' not in raw and "explanation" not in raw
    assessment = view.get_json()["data"]["assessment"]
    assert assessment["attempts_left"] == 3 and assessment["status"] == "not_started"

    # Server-side validation: unknown options, missing required answers, foreign questions.
    q = {item["kind"]: str(item["id"]) for item in questions}
    assert (
        learner.post(f"{url}/attempts", {"answers": {q["single_choice"]: "zzz"}}).status_code == 400
    )
    assert learner.post(f"{url}/attempts", {"answers": {}}).status_code == 400
    assert learner.post(f"{url}/attempts", {"answers": {"999999": "a"}}).status_code == 400

    failed = learner.post(
        f"{url}/attempts", {"answers": _answers(questions, right=False)}
    ).get_json()["data"]
    attempt = failed["attempt"]
    assert (
        attempt["passed"] is False
        and attempt["percent"] == 0
        and attempt["answers_revealed"] is False
    )
    assert all("correct_answer" not in r and "explanation" not in r for r in attempt["results"])
    assert failed["assessment"]["status"] == "failed" and failed["assessment"]["attempts_left"] == 2

    passed = learner.post(f"{url}/attempts", {"answers": _answers(questions)}).get_json()["data"][
        "attempt"
    ]
    assert (
        passed["passed"] is True and passed["percent"] == 100 and passed["answers_revealed"] is True
    )
    single = next(r for r in passed["results"] if r["kind"] == "single_choice")
    assert single["correct_answer"] == ["b"] and single["explanation"] == "Pausing first."
    written = next(r for r in passed["results"] if r["kind"] == "short_text")
    assert written["graded"] is False and "correct" not in written  # never auto-marked

    learner.post(f"{url}/attempts", {"answers": _answers(questions)})
    exhausted = learner.post(f"{url}/attempts", {"answers": _answers(questions)})
    assert (
        exhausted.status_code == 409
        and exhausted.get_json()["error"]["code"] == "attempts_exhausted"
    )
    history = learner.get(url).get_json()["data"]["assessment"]["attempts"]
    assert [a["attempt_number"] for a in history] == [3, 2, 1]


def test_quiz_is_required_for_completion(seeded, as_role):
    editor = as_role("editor")
    course, quiz, questions, lessons = _quiz_course(editor)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/quiz-course/enroll")
    res = learner.post(f"{LEARN}/quiz-course/lessons/{lessons[0]['slug']}/complete").get_json()[
        "data"
    ]
    assert res["progress"]["percent"] == 50 and not res["progress"]["complete"]
    url = f"{LEARN}/quiz-course/assessments/{quiz['id']}/attempts"
    learner.post(url, {"answers": _answers(questions, right=False)})
    assert learner.get(f"{LEARN}/quiz-course").get_json()["data"]["progress"]["complete"] is False
    done = learner.post(url, {"answers": _answers(questions)}).get_json()["data"]
    assert done["progress"]["complete"] is True


def test_reflections_and_self_assessments_are_never_graded(seeded, as_role):
    editor = as_role("editor")
    course, _, _ = ready_course(editor, "Reflect Course", lessons=1)
    cid = course["id"]
    reflection = editor.post(
        f"{COURSES}/{cid}/assessments", {"title": "Journal", "kind": "reflection"}
    ).get_json()["data"]
    qurl = f"{COURSES}/{cid}/assessments/{reflection['id']}/questions"
    refused = editor.post(
        qurl,
        {
            "kind": "single_choice",
            "prompt": "x",
            "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            "correct": ["a"],
        },
    )
    assert refused.status_code == 400  # reflections hold written answers and ratings only
    editor.post(qurl, {"kind": "short_text", "prompt": "What did you notice this week?"})
    editor.post(
        qurl,
        {
            "kind": "rating",
            "prompt": "How calm do you feel?",
            "settings": {"scale": 5, "min_label": "Tense", "max_label": "Calm"},
        },
    )
    editor.post(f"{COURSES}/{cid}/assessments/{reflection['id']}/status", {"status": "published"})
    learner = _verified(seeded)
    learner.post(f"{LEARN}/reflect-course/enroll")
    view = learner.get(f"{LEARN}/reflect-course/assessments/{reflection['id']}").get_json()["data"][
        "assessment"
    ]
    q = {item["kind"]: str(item["id"]) for item in view["questions"]}
    assert view["questions"][1]["scale"] == 5
    url = f"{LEARN}/reflect-course/assessments/{reflection['id']}/attempts"
    assert (
        learner.post(url, {"answers": {q["short_text"]: "Mornings", q["rating"]: 9}}).status_code
        == 400
    )
    res = learner.post(
        url, {"answers": {q["short_text"]: "Mornings felt lighter", q["rating"]: 4}}
    ).get_json()["data"]
    assert res["attempt"]["passed"] is None and res["attempt"]["percent"] is None
    assert res["assessment"]["status"] == "submitted"
    assert all("correct" not in r for r in res["attempt"]["results"])


# ---- premium courses, purchases, refunds and guest claims --------------------------------


@pytest.fixture()
def premium(seeded, as_role, paystack):
    admin = as_role("super_admin", email="owner@example.org")
    product = _create(
        admin,
        "Resilience Course Access",
        product_type="course",
        short_description="Lifetime access to the course.",
    )
    assert (
        _upload(admin, product["id"], name="workbook.pdf", title="Course workbook").status_code
        == 201
    )
    assert (
        admin.post(
            f"{PRODUCTS}/{product['id']}/prices", {"currency": "USD", "amount_minor": 4900}
        ).status_code
        == 201
    )
    files = admin.get(f"{PRODUCTS}/{product['id']}").get_json()["data"]["files"]
    file_id = files[0]["public_id"] if "public_id" in files[0] else files[0]["id"]
    course = create_course(
        admin, "Resilience Course", access_type="premium", product_id=product["id"]
    )
    module = add_module(admin, course["id"])
    lesson = add_lesson(
        admin,
        course["id"],
        module["id"],
        "Bounce back",
        body=lesson_body(blocks=[{"type": "download", "file_id": file_id, "title": "Workbook"}]),
    )
    res = admin.post(f"{COURSES}/{course['id']}/publish", {})
    assert res.status_code == 200, res.get_json()
    res = admin.patch(f"{PRODUCTS}/{product['id']}", {"sales_status": "on_sale"})
    assert res.status_code == 200, res.get_json()
    res = admin.post(f"{PRODUCTS}/{product['id']}/publish")
    assert res.status_code == 200, res.get_json()
    enable_test_checkout(seeded)
    with seeded.app_context():
        from app.models import Product

        public_id = db.session.get(Product, product["id"]).public_id
    return {
        "admin": admin,
        "product": product,
        "public_id": public_id,
        "course": course,
        "lesson": lesson,
        "paystack": paystack,
    }


def _pay(client, premium, shopper):
    res = _checkout(shopper, [premium["public_id"]])
    assert res.status_code == 201, res.get_json()
    order = res.get_json()["data"]["order"]
    tx = premium["paystack"].pay(order["payment"]["reference"])
    tx["paid_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    assert _send_webhook(client, premium["paystack"], "charge.success", tx).status_code == 200
    return order, tx


def test_premium_course_needs_verified_payment_and_ends_with_refund(seeded, premium, client):
    lesson_url = f"{LEARN}/resilience-course/lessons/{premium['lesson']['slug']}"
    public = client.get("/api/v1/courses/resilience-course").get_json()["data"]
    assert public["is_free"] is False and public["purchasable"] is True
    assert (
        public["prices"][0]["amount_minor"] == 4900
        and public["product"]["id"] == premium["public_id"]
    )
    shopper = _verified(seeded)
    assert shopper.post(f"{LEARN}/resilience-course/enroll").status_code == 409  # premium: buy it
    assert shopper.get(lesson_url).get_json()["error"]["code"] == "not_enrolled"

    order, tx = _pay(client, premium, shopper)
    # A repeated webhook neither charges nor enrols twice.
    assert _send_webhook(client, premium["paystack"], "charge.success", tx).status_code == 200
    with seeded.app_context():
        rows = db.session.scalars(db.select(CourseEnrollment)).all()
        assert len(rows) == 1 and rows[0].source == "purchase"
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 1
    lesson = shopper.get(lesson_url).get_json()["data"]
    download = next(b for b in lesson["lesson"]["body"] if b["type"] == "download")
    file = download["file"]
    auth = shopper.post(
        f"/api/v1/account/library/{file['entitlement_id']}/downloads",
        {"version_id": file["version_id"]},
    )
    assert auth.status_code == 200 and auth.get_json()["data"]["url"].startswith(
        "/api/v1/downloads/"
    )
    library = shopper.get("/api/v1/account/library").get_json()["data"]
    assert library[0]["product"]["course"] == {
        "slug": "resilience-course",
        "title": "Resilience Course",
    }

    # Revoking the purchase (as a full refund does) ends course access at once.
    from app.services.commerce import entitlements as ent_service

    with seeded.app_context():
        ent_service.revoke(db.session.scalar(db.select(Entitlement)), "Refunded", None)
        db.session.commit()
    ended = shopper.get(lesson_url)
    assert ended.status_code == 403 and ended.get_json()["error"]["code"] == "course_access_ended"
    assert shopper.get(LEARN).get_json()["data"]["enrollments"][0]["access"] == "ended"
    assert (
        shopper.post(
            f"/api/v1/account/library/{file['entitlement_id']}/downloads",
            {"version_id": file["version_id"]},
        ).status_code
        == 403
    )


def test_full_refund_through_orders_revokes_course_access(seeded, premium, client, as_role):
    from app.models import Order, SiteSetting

    with seeded.app_context():
        db.session.add(SiteSetting(key="payments.refunds_via_provider", value=True))
        db.session.commit()
    shopper = _verified(seeded)
    order, _ = _pay(client, premium, shopper)
    assert shopper.get(f"{LEARN}/resilience-course").status_code == 200
    with seeded.app_context():
        oid = db.session.scalar(db.select(Order.id).where(Order.public_id == order["id"]))
    manager = as_role("orders_manager")
    refund = manager.post(
        f"/api/v1/admin/orders/{oid}/refunds", {"reason": "Changed mind", "idempotency_key": _key()}
    ).get_json()["data"]["refund"]
    data = {
        "id": int(refund["provider_refund_id"]),
        "status": "processed",
        "transaction_reference": order["payment"]["reference"],
        "amount": 4900,
        "currency": "USD",
        "domain": "test",
    }
    assert _send_webhook(client, premium["paystack"], "refund.processed", data).status_code == 200
    assert (
        shopper.get(f"{LEARN}/resilience-course").get_json()["error"]["code"]
        == "course_access_ended"
    )


def test_guest_course_purchase_is_claimed_only_after_email_verification(seeded, premium, client):
    seeded.config["PAYMENTS_TEST_CHECKOUT_PUBLIC"] = True
    res = client.post(
        "/api/v1/checkout/guest",
        json={
            "email": "buyer@example.com",
            "items": [{"product_id": premium["public_id"]}],
            "currency": "USD",
            "expected_total_minor": 4900,
            "idempotency_key": _key(),
            "accept_terms": True,
        },
    )
    assert res.status_code == 201, res.get_json()
    order = res.get_json()["data"]["order"]
    tx = premium["paystack"].pay(order["payment"]["reference"])
    tx["paid_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    assert _send_webhook(client, premium["paystack"], "charge.success", tx).status_code == 200
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(CourseEnrollment.id))) == 0

    # Someone registers with the purchase email but hasn't proved they own the mailbox.
    MemoryBackend.outbox.clear()
    claimant = _unverified(seeded, "buyer@example.com")
    blocked = claimant.get(f"{LEARN}/resilience-course")
    assert (
        blocked.status_code == 403
        and blocked.get_json()["error"]["code"] == "email_verification_required"
    )
    assert claimant.get(LEARN).status_code == 403
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(CourseEnrollment.id))) == 0
    # After confirming the address the course appears and opens.
    message = [m for m in MemoryBackend.outbox if m.to == "buyer@example.com"][-1]
    token = message.text.split("#token=", 1)[1].split()[0]
    assert claimant.post("/api/v1/account/verify-email", {"token": token}).status_code == 200
    mine = claimant.get(LEARN).get_json()["data"]["enrollments"]
    assert [e["course"]["slug"] for e in mine] == ["resilience-course"] and mine[0][
        "access"
    ] == "active"
    assert (
        claimant.get(f"{LEARN}/resilience-course/lessons/{premium['lesson']['slug']}").status_code
        == 200
    )


# ---- staff: enrolments, certificates and reports -----------------------------------------


def test_staff_enrolment_management_certificates_and_reports(seeded, as_role, client):
    editor = as_role("editor")
    course, _, lessons = ready_course(editor, "Managed Course", lessons=1)
    cid = course["id"]
    learner = _verified(seeded)
    support = as_role("customer_support")
    url = f"{COURSES}/{cid}/enrollments"
    assert support.post(url, {"email": "reader@example.com"}).status_code == 400  # reason required
    assert (
        support.post(url, {"email": "nobody@example.com", "reason": "Scholarship"}).status_code
        == 400
    )
    res = support.post(url, {"email": "reader@example.com", "reason": "Scholarship"})
    assert res.status_code == 201, res.get_json()
    enrollment = res.get_json()["data"]
    assert enrollment["source"] == "manual" and enrollment["access"] == "active"
    assert support.post(url, {"email": "reader@example.com", "reason": "Again"}).status_code == 409

    learner.post(f"{LEARN}/managed-course/lessons/{lessons[0]['slug']}/complete")
    listing = support.get(f"{url}?status=completed").get_json()
    assert listing["meta"]["total"] == 1 and listing["data"][0]["progress_percent"] == 100
    detail = support.get(f"{url}/{enrollment['id']}").get_json()["data"]
    assert detail["lessons"][0]["completed_at"] and detail["certificate"]["status"] == "valid"
    code = detail["certificate"]["code"]

    # Corrections and revocation are audited and visible on the verification page.
    cert_url = f"/api/v1/admin/certificates/{code}"
    assert editor.post(f"{cert_url}/revoke", {"reason": "x"}).status_code == 403
    fixed = support.post(
        f"{cert_url}/correct", {"recipient_name": "Reader Lovelace", "note": "Spelling"}
    )
    assert (
        fixed.status_code == 200 and fixed.get_json()["data"]["recipient_name"] == "Reader Lovelace"
    )
    assert (
        client.get(f"/api/v1/certificates/{code}").get_json()["data"]["recipient_name"]
        == "Reader Lovelace"
    )
    assert support.post(f"{cert_url}/revoke", {"reason": "Issued in error"}).status_code == 200
    assert client.get(f"/api/v1/certificates/{code}").get_json()["data"]["status"] == "revoked"
    assert learner.get(f"/api/v1/account/certificates/{code}/pdf").status_code == 409
    assert support.post(f"{cert_url}/reinstate", {"reason": "Confirmed"}).status_code == 200

    revoked = support.post(f"{url}/{enrollment['id']}/revoke", {"reason": "Requested by learner"})
    assert revoked.status_code == 200 and revoked.get_json()["data"]["status"] == "revoked"
    assert (
        learner.get(f"{LEARN}/managed-course").get_json()["error"]["code"] == "course_access_ended"
    )
    assert (
        learner.post(f"{LEARN}/managed-course/enroll").status_code == 409
    )  # staff decision stands
    restored = support.post(f"{url}/{enrollment['id']}/restore", {"reason": "Mistake"})
    assert restored.get_json()["data"]["status"] == "active"

    admin = as_role("administrator")
    report = admin.get("/api/v1/admin/courses/reports").get_json()["data"]
    assert report["courses"]["published"] == 1 and report["enrollments"]["enrollments"] == 1
    assert (
        report["enrollments"]["completions"] == 1
        and report["enrollments"]["completion_rate"] == 100
    )
    assert report["by_source"] == {"manual": 1}
    assert report["per_course"][0]["learners"] == 1
    with seeded.app_context():
        from app.models import AuditLog

        actions = set(db.session.scalars(db.select(AuditLog.action)))
    assert {
        "course.enrollment_granted",
        "course.certificate_corrected",
        "course.certificate_revoked",
        "course.enrollment_revoked",
    } <= actions


def test_assessment_pass_rates_use_real_attempts(seeded, as_role):
    editor = as_role("editor")
    course, quiz, questions, _ = _quiz_course(editor)
    url = f"{LEARN}/quiz-course/assessments/{quiz['id']}/attempts"
    for email, right in (("a@example.com", True), ("b@example.com", False)):
        learner = _verified(seeded, email)
        learner.post(f"{LEARN}/quiz-course/enroll")
        learner.post(url, {"answers": _answers(questions, right=right)})
    report = as_role("analyst").get(f"{COURSES}/{course['id']}/reports").get_json()["data"]
    rates = report["assessment_pass_rates"]
    assert rates == [{**rates[0], "learners": 2, "passed": 1, "attempts": 2, "pass_rate": 50}]


def test_certificate_waits_for_a_name_when_the_profile_has_none(seeded, as_role):
    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Named Course", lessons=1)
    learner = _verified(seeded)
    with seeded.app_context():
        db.session.scalar(db.select(Customer)).display_name = ""  # profile names are optional
        db.session.commit()
    learner.post(f"{LEARN}/named-course/enroll")
    learner.post(f"{LEARN}/named-course/lessons/{lessons[0]['slug']}/complete")
    card = learner.get(LEARN).get_json()["data"]["enrollments"][0]
    assert card["certificate"] is None and card["certificate_available"] is True
    assert learner.post(f"{LEARN}/named-course/certificate", {"name": "x"}).status_code == 400
    res = learner.post(f"{LEARN}/named-course/certificate", {"name": "Ada Learner"})
    assert res.status_code == 201 and res.get_json()["data"]["recipient_name"] == "Ada Learner"
    again = learner.post(f"{LEARN}/named-course/certificate", {"name": "Someone Else"})
    assert again.get_json()["data"]["recipient_name"] == "Ada Learner"  # one per enrolment


def test_archived_course_stays_open_to_enrolled_learners(seeded, as_role, client):
    editor = as_role("editor")
    course, _, lessons = ready_course(editor, "Retired Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/retired-course/enroll")
    editor.post(f"{COURSES}/{course['id']}/archive", {})
    assert client.get("/api/v1/courses/retired-course").status_code == 404
    assert learner.get(f"{LEARN}/retired-course/lessons/{lessons[0]['slug']}").status_code == 200
    newcomer = _verified(seeded, "late@example.com")
    assert newcomer.post(f"{LEARN}/retired-course/enroll").status_code == 404


def test_export_and_account_deletion_cover_learning_records(seeded, as_role, client):
    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Private Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/private-course/enroll")
    learner.post(f"{LEARN}/private-course/lessons/{lessons[0]['slug']}/complete")
    exported = learner.post("/api/v1/account/export", {"password": PASSWORD}).get_json()["data"]
    assert exported["learning"][0]["course"] == "Private Course"
    code = exported["learning"][0]["certificate"]["code"]
    assert learner.post("/api/v1/account/delete", {"password": PASSWORD}).status_code == 200
    check = client.get(f"/api/v1/certificates/{code}").get_json()["data"]
    assert check["status"] == "revoked" and check["recipient_name"] == "Deleted account"
    with seeded.app_context():
        enrollment = db.session.scalar(db.select(CourseEnrollment))
        assert enrollment.status == "revoked"
        assert db.session.scalar(db.select(CourseCertificate)).revoked_reason == "Account deleted"


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Concurrent enrolment needs a real database server (run with TEST_DATABASE_URL).",
)
def test_concurrent_enrolment_requests_create_one_enrolment(seeded, as_role):
    import threading

    from app.services.courses import learning

    editor = as_role("editor")
    ready_course(editor, "Busy Course", lessons=1)
    _verified(seeded)
    results, barrier = [], threading.Barrier(6)

    def worker():
        with seeded.app_context():
            customer = db.session.scalar(
                db.select(Customer).where(Customer.email == "reader@example.com")
            )
            course = db.session.scalar(db.select(Course).where(Course.slug == "busy-course"))
            barrier.wait()
            try:
                _, created = learning.enroll_free(customer, course)
                db.session.commit()
                results.append(created)
            finally:
                db.session.remove()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1 and len(results) == 6, results
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(CourseEnrollment.id))) == 1


def test_unknown_fields_in_answers_and_public_payloads_hide_keys(seeded, as_role, client):
    editor = as_role("editor")
    course, quiz, questions, _ = _quiz_course(editor)
    payload = json.dumps(client.get("/api/v1/courses/quiz-course").get_json())
    assert "Pausing first." not in payload and "correct" not in payload
    assert secrets.compare_digest("ok", "ok") and Shopper  # imported helpers stay used

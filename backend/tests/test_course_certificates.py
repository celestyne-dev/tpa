"""Automatic certificates of completion: completion rules, the completion award, automatic
issuance, the PDF, public verification, revocation and controlled reissuance, ownership of
downloads, issuance emails (failures and retries) and admin views."""

from __future__ import annotations

import io
import os
import threading

import pytest
from pypdf import PdfReader

from app.extensions import db
from app.models import AuditLog, CourseCertificate, CourseEnrollment, Customer
from app.services import mail
from app.services.mail import MemoryBackend

from .test_courses_admin import COURSES, add_lesson, add_module, create_course, ready_course
from .test_courses_learning import LEARN, _answers, _quiz_course, _verified

ADMIN_CERTS = "/api/v1/admin/certificates"


def _text(data: bytes) -> str:
    return " ".join(PdfReader(io.BytesIO(data)).pages[0].extract_text().split())


def _card(learner, slug):
    cards = learner.get(LEARN).get_json()["data"]["enrollments"]
    return next(c for c in cards if c["course"]["slug"] == slug)


def _complete(learner, slug, lesson):
    res = learner.post(f"{LEARN}/{slug}/lessons/{lesson['slug']}/complete")
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _certificate_mail(email="reader@example.com"):
    return [
        m
        for m in MemoryBackend.outbox
        if m.to == email and "certificate of completion" in m.subject
    ]


def _count(app, model=CourseCertificate):
    with app.app_context():
        return db.session.scalar(db.select(db.func.count(model.id)))


def _actions(app):
    with app.app_context():
        return list(db.session.scalars(db.select(AuditLog.action)))


# ---- completion rules ---------------------------------------------------------------------


def test_enrolment_alone_and_a_course_without_lessons_never_complete(seeded, as_role):
    editor = as_role("editor")
    course, quiz, questions, lessons = _quiz_course(editor)
    learner = _verified(seeded)
    assert learner.post(f"{LEARN}/quiz-course/enroll").status_code == 201
    card = _card(learner, "quiz-course")
    assert card["completed_at"] is None and card["certificate"] is None
    assert card["certificate_status"] == "in_progress" and card["certificate_available"] is False
    assert card["progress"]["has_requirements"] and not card["progress"]["complete"]
    assert {item["type"] for item in card["progress"]["outstanding"]} == {"lesson", "assessment"}
    assert learner.post(f"{LEARN}/quiz-course/certificate", {}).status_code == 409

    # Every lesson unpublished: passing the only remaining requirement (the quiz) must not
    # complete the course or issue a certificate.
    res = editor.post(
        f"{COURSES}/{course['id']}/lessons/{lessons[0]['id']}/status", {"status": "draft"}
    )
    assert res.status_code == 200, res.get_json()
    done = learner.post(
        f"{LEARN}/quiz-course/assessments/{quiz['id']}/attempts",
        {"answers": _answers(questions)},
    ).get_json()["data"]
    assert done["progress"]["has_requirements"] is False and done["progress"]["complete"] is False
    card = _card(learner, "quiz-course")
    assert card["completed_at"] is None and card["certificate"] is None
    assert _count(seeded) == 0 and not _certificate_mail()


def test_optional_lessons_dont_count_and_outstanding_requirements_are_listed(seeded, as_role):
    editor = as_role("editor")
    course = create_course(editor, "Steady Ground", outcomes=["Pause"])
    module = add_module(editor, course["id"])
    one = add_lesson(editor, course["id"], module["id"], "First step")
    two = add_lesson(editor, course["id"], module["id"], "Second step")
    extra = add_lesson(editor, course["id"], module["id"], "Bonus", completion_required=False)
    assert editor.post(f"{COURSES}/{course['id']}/publish", {}).status_code == 200
    learner = _verified(seeded)
    learner.post(f"{LEARN}/steady-ground/enroll")

    state = _complete(learner, "steady-ground", extra)["progress"]
    assert state["completed_lessons"] == 0 and state["required_lessons"] == 2
    assert [i["slug"] for i in state["outstanding"]] == [one["slug"], two["slug"]]
    state = _complete(learner, "steady-ground", one)["progress"]
    assert state["outstanding"] == [{"type": "lesson", "slug": two["slug"], "title": "Second step"}]
    assert _card(learner, "steady-ground")["certificate_status"] == "in_progress"
    assert _count(seeded) == 0

    # The last required lesson: the completion award and the certificate, automatically.
    state = _complete(learner, "steady-ground", two)["progress"]
    assert state["complete"] and state["outstanding"] == []
    card = _card(learner, "steady-ground")
    assert card["completed_at"] and card["certificate_status"] == "issued"
    certificate = card["certificate"]
    assert certificate["recipient_name"] == "Reader" and not certificate["revoked"]
    assert certificate["verify_url"].endswith(f"/certificates/{certificate['code']}")

    # One email, with the download link and the verification address.
    (message,) = _certificate_mail()
    assert "Steady Ground" in message.subject
    assert "/learn/steady-ground" in message.text and certificate["code"] in message.text
    assert certificate["verify_url"] in message.text

    # Repeated completion events change nothing: one award, one certificate, one email.
    with seeded.app_context():
        enrollment = db.session.scalar(db.select(CourseEnrollment))
        completed_at = enrollment.completed_at
        assert enrollment.completion_snapshot["recorded"] == "at_completion"
        assert enrollment.completion_snapshot["counts"]["lessons"] == 2
    for lesson in (two, one, extra):
        _complete(learner, "steady-ground", lesson)
    assert learner.post(f"{LEARN}/steady-ground/certificate", {}).status_code == 201
    assert _count(seeded) == 1 and len(_certificate_mail()) == 1
    with seeded.app_context():
        assert db.session.scalar(db.select(CourseEnrollment)).completed_at == completed_at
        cert = db.session.scalar(db.select(CourseCertificate))
        assert cert.email_status == "sent" and cert.email_attempts == 1 and cert.emailed_at
        assert cert.course_slug == "steady-ground" and cert.completed_at == completed_at
    actions = _actions(seeded)
    assert actions.count("course.completed") == 1
    assert actions.count("course.certificate_issued") == 1


def test_a_failed_quiz_blocks_the_certificate_and_a_pass_issues_it(seeded, as_role):
    editor = as_role("editor")
    _, quiz, questions, lessons = _quiz_course(editor)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/quiz-course/enroll")
    _complete(learner, "quiz-course", lessons[0])
    url = f"{LEARN}/quiz-course/assessments/{quiz['id']}/attempts"
    failed = learner.post(url, {"answers": _answers(questions, right=False)}).get_json()["data"]
    assert failed["progress"]["complete"] is False
    (item,) = failed["progress"]["outstanding"]
    assert item["type"] == "assessment" and item["state"] == "failed"
    assert item["passing_score"] == 60 and item["best_percent"] < 60
    assert _card(learner, "quiz-course")["certificate"] is None and _count(seeded) == 0

    passed = learner.post(url, {"answers": _answers(questions)}).get_json()["data"]
    assert passed["progress"]["complete"] is True
    card = _card(learner, "quiz-course")
    assert card["certificate_status"] == "issued" and card["certificate"]["code"]
    with seeded.app_context():
        snapshot = db.session.scalar(db.select(CourseEnrollment)).completion_snapshot
    assert snapshot["assessments"][0]["passing_score"] == 60
    assert snapshot["assessments"][0]["best_percent"] >= 60


def test_requirements_edited_after_completion_keep_the_award(seeded, as_role):
    editor = as_role("editor")
    course, module, lessons = ready_course(editor, "Edited Course", lessons=1)
    early = _verified(seeded)
    early.post(f"{LEARN}/edited-course/enroll")
    _complete(early, "edited-course", lessons[0])
    code = _card(early, "edited-course")["certificate"]["code"]

    # A new required lesson: completed learners keep their completion and certificate;
    # learners who haven't finished must do it.
    new = add_lesson(editor, course["id"], module["id"], "New material")
    card = _card(early, "edited-course")
    assert card["completed_at"] and card["certificate"]["code"] == code
    assert card["certificate_status"] == "issued"
    assert card["progress"]["complete"] is False  # shown honestly against today's rules
    late = _verified(seeded, "late@example.com")
    late.post(f"{LEARN}/edited-course/enroll")
    assert _complete(late, "edited-course", lessons[0])["progress"]["complete"] is False
    assert _card(late, "edited-course")["certificate"] is None
    _complete(late, "edited-course", new)
    assert _card(late, "edited-course")["certificate_status"] == "issued"


def test_completions_recorded_before_awards_existed_are_rechecked(seeded, as_role):
    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Legacy Course", lessons=2)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/legacy-course/enroll")
    with seeded.app_context():  # what an older release could have recorded
        from datetime import UTC, datetime

        enrollment = db.session.scalar(db.select(CourseEnrollment))
        enrollment.completed_at = datetime.now(UTC)
        enrollment.completion_snapshot = None
        db.session.commit()
    card = _card(learner, "legacy-course")
    assert card["certificate_status"] == "requirements_changed" and card["certificate"] is None
    refused = learner.post(f"{LEARN}/legacy-course/certificate", {})
    assert refused.status_code == 409 and "requirements" in refused.get_json()["error"]["message"]
    for lesson in lessons:
        _complete(learner, "legacy-course", lesson)
    assert _card(learner, "legacy-course")["certificate_status"] == "available"
    assert learner.post(f"{LEARN}/legacy-course/certificate", {}).status_code == 201
    with seeded.app_context():
        snapshot = db.session.scalar(db.select(CourseEnrollment)).completion_snapshot
    assert snapshot["recorded"] == "re-checked"


def test_courses_without_certificates_dont_issue_them(seeded, as_role):
    editor = as_role("editor")
    course, _, lessons = ready_course(editor, "No Certificate", lessons=1)
    editor.patch(f"{COURSES}/{course['id']}", {"certificate_enabled": False})
    learner = _verified(seeded)
    learner.post(f"{LEARN}/no-certificate/enroll")
    _complete(learner, "no-certificate", lessons[0])
    card = _card(learner, "no-certificate")
    assert card["completed_at"] and card["certificate_status"] == "not_offered"
    assert _count(seeded) == 0 and not _certificate_mail()
    assert learner.post(f"{LEARN}/no-certificate/certificate", {}).status_code == 409
    # Turned on later: the recorded completion qualifies, on request.
    editor.patch(f"{COURSES}/{course['id']}", {"certificate_enabled": True})
    assert _card(learner, "no-certificate")["certificate_status"] == "available"
    assert learner.post(f"{LEARN}/no-certificate/certificate", {}).status_code == 201


def test_required_quizzes_need_a_meaningful_passing_score(seeded, as_role):
    editor = as_role("editor")
    course, _, _ = ready_course(editor, "Weak Rules", lessons=1)
    cid = course["id"]
    url = f"{COURSES}/{cid}/assessments"

    # A required quiz at 0% is refused when created or edited ...
    bad = editor.post(url, {"title": "Anything goes", "kind": "quiz", "passing_score": 0})
    assert bad.status_code == 400
    assert "at least 1%" in bad.get_json()["error"]["details"]["passing_score"][0]
    quiz = editor.post(url, {"title": "Check", "kind": "quiz", "passing_score": 50}).get_json()[
        "data"
    ]
    qurl = f"{url}/{quiz['id']}"
    assert editor.patch(qurl, {"passing_score": 0}).status_code == 400
    # ... but an optional quiz or a practice exam may use 0% (it never counts).
    optional = editor.post(
        url,
        {
            "title": "Warm-up",
            "kind": "quiz",
            "passing_score": 0,
            "required_for_completion": False,
        },
    )
    assert optional.status_code == 201, optional.get_json()
    assert (
        editor.post(
            url, {"title": "Practice", "kind": "quiz", "passing_score": 0, "practice": True}
        ).status_code
        == 201
    )
    # Making a 0% optional quiz required is refused too.
    oid = optional.get_json()["data"]["id"]
    assert editor.patch(f"{url}/{oid}", {"required_for_completion": True}).status_code == 400


def test_a_zero_percent_required_quiz_from_before_never_qualifies(seeded, as_role):
    """Quizzes saved before the rule (passing score 0) can't be published, block course
    publication and never count towards completion or a certificate."""
    from app.models import Assessment

    editor = as_role("editor")
    course, quiz, questions, lessons = _quiz_course(editor)
    with seeded.app_context():  # what an older release allowed
        db.session.get(Assessment, quiz["id"]).passing_score = 0
        db.session.commit()
    readiness = editor.get(f"{COURSES}/{course['id']}").get_json()["data"]["readiness"]
    assert any("at least 1%" in issue for issue in readiness["issues"])
    res = editor.post(
        f"{COURSES}/{course['id']}/assessments/{quiz['id']}/status", {"status": "draft"}
    )
    assert res.status_code == 200
    res = editor.post(
        f"{COURSES}/{course['id']}/assessments/{quiz['id']}/status", {"status": "published"}
    )
    assert res.status_code == 400 and "at least 1%" in res.get_json()["error"]["message"]
    with seeded.app_context():
        db.session.get(Assessment, quiz["id"]).status = "published"
        db.session.commit()

    learner = _verified(seeded)
    learner.post(f"{LEARN}/quiz-course/enroll")
    _complete(learner, "quiz-course", lessons[0])
    url = f"{LEARN}/quiz-course/assessments/{quiz['id']}/attempts"
    state = learner.post(url, {"answers": _answers(questions, right=False)}).get_json()["data"]
    assert state["progress"]["complete"] is False
    (item,) = state["progress"]["outstanding"]
    assert item["state"] == "needs_passing_score"
    state = learner.post(url, {"answers": _answers(questions)}).get_json()["data"]
    assert state["progress"]["complete"] is False
    assert learner.post(f"{LEARN}/quiz-course/certificate", {}).status_code == 409
    assert _card(learner, "quiz-course")["certificate"] is None and _count(seeded) == 0

    # Once staff set a real passing score, the learner's passing attempt counts.
    assert (
        editor.patch(
            f"{COURSES}/{course['id']}/assessments/{quiz['id']}", {"passing_score": 60}
        ).status_code
        == 200
    )
    state = learner.get(f"{LEARN}/quiz-course").get_json()["data"]["progress"]
    assert state["complete"] is True


def test_certificates_are_never_issued_without_every_requirement(seeded, as_role, client):
    """Every route to a certificate re-checks the requirements on the server."""
    from app.services.courses import certificates, learning
    from app.utils.errors import ConflictError

    editor = as_role("editor")
    course, quiz, questions, lessons = _quiz_course(editor)
    support = as_role("customer_support")
    # Manual enrolment by staff, then everything except passing the quiz.
    learner = _verified(seeded)
    res = support.post(
        f"{COURSES}/{course['id']}/enrollments",
        {"email": "reader@example.com", "reason": "Scholarship"},
    )
    assert res.status_code == 201, res.get_json()
    assert learner.post(f"{LEARN}/quiz-course/certificate", {}).status_code == 409
    _complete(learner, "quiz-course", lessons[0])
    url = f"{LEARN}/quiz-course/assessments/{quiz['id']}/attempts"
    learner.post(url, {"answers": _answers(questions, right=False)})
    for name in (None, "Reader"):  # with or without a chosen name
        body = {} if name is None else {"name": name}
        assert learner.post(f"{LEARN}/quiz-course/certificate", body).status_code == 409
    with seeded.app_context():
        enrollment = db.session.scalar(db.select(CourseEnrollment))
        assert enrollment.completed_at is None
        with pytest.raises(ConflictError):
            certificates.issue(enrollment, "Reader")
        assert certificates.issue_on_completion(enrollment) is None
        # Recomputing progress doesn't complete it either.
        assert learning.recompute(enrollment)["complete"] is False
        db.session.commit()
    assert _count(seeded) == 0
    assert _card(learner, "quiz-course")["certificate_status"] == "in_progress"
    assert not _certificate_mail()


# ---- concurrency --------------------------------------------------------------------------


def test_a_second_issue_returns_the_same_certificate(seeded, as_role):
    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Once Only", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/once-only/enroll")
    _complete(learner, "once-only", lessons[0])
    with seeded.app_context():
        from app.services.courses import certificates

        enrollment = db.session.scalar(db.select(CourseEnrollment))
        first = certificates.active_for(enrollment.id)
        # Racing a concurrent request: the partial unique index refuses the second valid
        # certificate and the existing one is returned.
        again = certificates._create(enrollment, "Reader")
        assert again.id == first.id
        assert certificates.issue(enrollment).id == first.id
        db.session.commit()
    assert _count(seeded) == 1


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Concurrent issuance needs a real database server (run with TEST_DATABASE_URL).",
)
def test_concurrent_issuance_requests_create_one_certificate(seeded, as_role):
    from app.services.courses import certificates

    editor = as_role("editor")
    course, _, lessons = ready_course(editor, "Busy Certificates", lessons=1)
    editor.patch(f"{COURSES}/{course['id']}", {"certificate_enabled": False})
    learner = _verified(seeded)
    learner.post(f"{LEARN}/busy-certificates/enroll")
    _complete(learner, "busy-certificates", lessons[0])
    editor.patch(f"{COURSES}/{course['id']}", {"certificate_enabled": True})
    codes, errors, barrier = [], [], threading.Barrier(6)

    def worker():
        with seeded.app_context():
            enrollment = db.session.scalar(db.select(CourseEnrollment))
            barrier.wait()
            try:
                codes.append(certificates.issue(enrollment).code)
                db.session.commit()
            except Exception as err:  # noqa: BLE001
                errors.append(err)
            finally:
                db.session.remove()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(set(codes)) == 1 and len(codes) == 6
    assert _count(seeded) == 1


# ---- the PDF ------------------------------------------------------------------------------


def test_pdf_has_the_required_content_and_unicode_names():
    from datetime import UTC, datetime

    from app.services.courses.certificate_pdf import CertificateContent, render

    url = "https://thinkpositivealways.com/certificates/TPA-7K3M-Q9XD-4HWB"
    content = CertificateContent(
        recipient_name="Nguyễn Thị Hương Giang",
        course_title="Navigating Toxic Workplaces Without Losing Yourself",
        code="TPA-7K3M-Q9XD-4HWB",
        issued_at=datetime(2026, 11, 24, tzinfo=UTC),
        completed_at=datetime(2026, 11, 23, tzinfo=UTC),
        verify_url=url,
        signatory_name="Celestine N",
        signatory_title="Founder",
        statement="Not an accredited qualification.",
    )
    data = render(content)
    assert data.startswith(b"%PDF-1.4") and len(PdfReader(io.BytesIO(data)).pages) == 1
    text = _text(data)
    for expected in (
        "T H I N K",
        "Certificate of Completion",
        "Nguyễn Thị Hương Giang",
        "Navigating Toxic Workplaces Without Losing Yourself",
        "23 November 2026",
        "Issued 24 November 2026",
        "TPA-7K3M-Q9XD-4HWB",
        "Celestine N",
        "Founder",
        url,
        "Not an accredited qualification.",
    ):
        assert expected in text, expected
    assert url.encode() in data  # the QR code and the printed address are links
    page = PdfReader(io.BytesIO(data)).pages[0]
    assert len(page.get("/Annots") or []) == 2

    # Cyrillic and Greek print exactly; scripts the font can't shape point to the page.
    cyrillic = _text(
        render(CertificateContent(**{**content.__dict__, "recipient_name": "Анна Ωμέγα"}))
    )
    assert "Анна Ωμέγα" in cyrillic and "exactly as registered" not in cyrillic
    arabic = _text(render(CertificateContent(**{**content.__dict__, "recipient_name": "ليلى"})))
    assert "exactly as registered" in arabic and "verification address" in arabic
    # Without an approved signatory, the issuing organisation signs.
    plain = _text(
        render(
            CertificateContent(**{**content.__dict__, "signatory_name": "", "signatory_title": ""})
        )
    )
    assert "Issuing organisation" in plain


def test_signatory_comes_from_settings_and_is_snapshotted(seeded, as_role, client):
    admin = as_role("super_admin")
    res = admin.patch(
        "/api/v1/admin/settings",
        {
            "values": {
                "certificates.signatory_name": "Celestine N",
                "certificates.signatory_title": "Founder",
            }
        },
    )
    assert res.status_code == 200, res.get_json()
    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Signed Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/signed-course/enroll")
    _complete(learner, "signed-course", lessons[0])
    code = _card(learner, "signed-course")["certificate"]["code"]
    admin.patch(
        "/api/v1/admin/settings", {"values": {"certificates.signatory_name": "Someone Else"}}
    )
    data = client.get(f"/api/v1/certificates/{code}").get_json()["data"]
    assert data["signatory_name"] == "Celestine N" and data["signatory_title"] == "Founder"
    pdf = learner.get(f"/api/v1/account/certificates/{code}/pdf")
    assert pdf.status_code == 200 and "Celestine N" in _text(pdf.data)
    assert pdf.headers["Cache-Control"] == "private, no-store"


# ---- verification, ownership, revocation and reissuance ---------------------------------


def test_verification_revocation_and_controlled_reissuance(seeded, as_role, client):
    editor = as_role("editor")
    course, _, lessons = ready_course(editor, "Verified Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/verified-course/enroll")
    _complete(learner, "verified-course", lessons[0])
    code = _card(learner, "verified-course")["certificate"]["code"]

    check = client.get(f"/api/v1/certificates/{code}")
    data = check.get_json()["data"]
    assert data["status"] == "valid" and data["recipient_name"] == "Reader"
    assert data["course_title"] == "Verified Course" and data["completed_at"]
    payload = check.get_data(as_text=True)
    assert "reader@example.com" not in payload
    assert not {"id", "enrollment_id", "customer_id", "email"} & set(data)
    assert check.headers["Cache-Control"] == "no-store"

    # Downloads: only the owner, never anonymous.
    other = _verified(seeded, "other@example.com")
    assert other.get(f"/api/v1/account/certificates/{code}/pdf").status_code == 404
    assert client.get(f"/api/v1/account/certificates/{code}/pdf").status_code == 401
    assert learner.get(f"/api/v1/account/certificates/{code}/pdf").status_code == 200

    support = as_role("customer_support")
    url = f"{ADMIN_CERTS}/{code}"
    assert editor.post(f"{url}/reissue", {"reason": "x"}).status_code == 403
    assert support.post(f"{url}/reissue", {}).status_code == 400  # a reason is required
    assert support.post(f"{url}/revoke", {"reason": "Issued in error"}).status_code == 200
    assert client.get(f"/api/v1/certificates/{code}").get_json()["data"]["status"] == "revoked"
    assert learner.get(f"/api/v1/account/certificates/{code}/pdf").status_code == 409
    card = _card(learner, "verified-course")
    assert card["certificate_status"] == "revoked" and card["certificate"]["revoked"]

    # A revoked certificate is never replaced or restored automatically.
    _complete(learner, "verified-course", lessons[0])
    assert learner.post(f"{LEARN}/verified-course/certificate", {}).status_code == 409
    assert _count(seeded) == 1

    # Controlled reissuance: a new code that records what it replaces.
    sent_before = len(_certificate_mail())
    res = support.post(
        f"{url}/reissue", {"reason": "Name corrected", "recipient_name": "Reader Ng"}
    )
    assert res.status_code == 200, res.get_json()
    new = res.get_json()["data"]
    assert new["code"] != code and new["status"] == "valid" and new["replaces_code"] == code
    assert new["recipient_name"] == "Reader Ng" and new["reissue_reason"] == "Name corrected"
    old = client.get(f"/api/v1/certificates/{code}").get_json()["data"]
    assert old["status"] == "revoked" and old["replaced"] is True
    assert new["code"] not in str(old)
    assert support.post(f"{url}/reinstate", {"reason": "Undo"}).status_code == 409
    assert support.post(f"{url}/reissue", {"reason": "Again"}).status_code == 409
    card = _card(learner, "verified-course")
    assert card["certificate"]["code"] == new["code"] and card["certificate_status"] == "issued"
    assert learner.get(f"/api/v1/account/certificates/{new['code']}/pdf").status_code == 200
    assert other.get(f"/api/v1/account/certificates/{new['code']}/pdf").status_code == 404
    (reissued,) = _certificate_mail()[sent_before:]
    assert "replaces your earlier certificate" in reissued.text and new["code"] in reissued.text

    # Admin detail: completion record and the full certificate history.
    with seeded.app_context():
        enrollment_id = db.session.scalar(db.select(CourseEnrollment.id))
    detail = support.get(f"{COURSES}/{course['id']}/enrollments/{enrollment_id}").get_json()["data"]
    assert detail["certificate"]["code"] == new["code"]
    assert [c["code"] for c in detail["certificates"]] == [code, new["code"]]
    assert detail["completion"]["recorded"] == "at_completion"
    assert detail["completion"]["certificate_status"] == "issued"
    actions = _actions(seeded)
    assert {
        "course.certificate_issued",
        "course.certificate_revoked",
        "course.certificate_reissued",
    } <= set(actions)


def test_deleted_accounts_make_certificates_unavailable(seeded, as_role, client):
    from .conftest import PASSWORD

    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Gone Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/gone-course/enroll")
    _complete(learner, "gone-course", lessons[0])
    code = _card(learner, "gone-course")["certificate"]["code"]
    assert learner.post("/api/v1/account/delete", {"password": PASSWORD}).status_code == 200
    data = client.get(f"/api/v1/certificates/{code}").get_json()["data"]
    assert data["status"] == "unavailable"
    assert data["recipient_name"] is None and data["course_title"] is None
    support = as_role("customer_support")
    assert support.post(f"{ADMIN_CERTS}/{code}/reinstate", {"reason": "x"}).status_code == 409
    assert support.post(f"{ADMIN_CERTS}/{code}/reissue", {"reason": "x"}).status_code == 409


# ---- email --------------------------------------------------------------------------------


def test_email_failure_keeps_the_completion_and_retries_send_once(seeded, as_role, monkeypatch):
    from app.cli import courses_cli  # noqa: F401  (registered command)

    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Mail Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/mail-course/enroll")

    def broken(self, message):
        raise mail.MailDeliveryError()

    monkeypatch.setattr(MemoryBackend, "send", broken)
    result = _complete(learner, "mail-course", lessons[0])
    assert result["progress"]["complete"] is True
    monkeypatch.undo()
    card = _card(learner, "mail-course")
    assert card["completed_at"] and card["certificate_status"] == "issued"
    with seeded.app_context():
        cert = db.session.scalar(db.select(CourseCertificate))
        assert cert.email_status == "failed" and cert.email_attempts == 1
    assert not _certificate_mail()

    runner = seeded.test_cli_runner()
    out = runner.invoke(args=["courses", "send-certificate-emails"])
    assert out.exit_code == 0, out.output
    assert len(_certificate_mail()) == 1
    out = runner.invoke(args=["courses", "send-certificate-emails"])  # nothing left to send
    assert out.exit_code == 0 and len(_certificate_mail()) == 1
    with seeded.app_context():
        from app.services.courses import certificates

        cert = db.session.scalar(db.select(CourseCertificate))
        assert cert.email_status == "sent" and cert.email_attempts == 2
        assert certificates.notify(cert.id) is None  # already sent: never twice
        code = cert.code
    assert len(_certificate_mail()) == 1

    # Staff can send it again on request, once per request.
    support = as_role("customer_support")
    res = support.post(f"{ADMIN_CERTS}/{code}/resend-email", {})
    assert res.status_code == 200, res.get_json()
    assert len(_certificate_mail()) == 2
    assert "course.certificate_email_requested" in _actions(seeded)


def test_unconfigured_email_is_recorded_and_not_retried(seeded, as_role):
    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Quiet Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/quiet-course/enroll")
    seeded.config["MAIL_BACKEND"] = "none"
    try:
        _complete(learner, "quiet-course", lessons[0])
        with seeded.app_context():
            from app.services.courses import certificates

            cert = db.session.scalar(db.select(CourseCertificate))
            assert cert.email_status == "not_configured" and cert.revoked_at is None
            assert certificates.retry_emails() == {}
            enrollment = db.session.scalar(db.select(CourseEnrollment))
            assert enrollment.completed_at is not None
    finally:
        seeded.config["MAIL_BACKEND"] = "memory"


def test_customers_cannot_reach_staff_certificate_actions(seeded, as_role, client):
    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Guarded Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/guarded-course/enroll")
    _complete(learner, "guarded-course", lessons[0])
    code = _card(learner, "guarded-course")["certificate"]["code"]
    for action in ("revoke", "reissue", "resend-email"):
        assert client.post(f"{ADMIN_CERTS}/{code}/{action}", json={"reason": "x"}).status_code in (
            401,
            403,
        )
    with seeded.app_context():
        assert db.session.scalar(db.select(CourseCertificate)).revoked_at is None
        assert db.session.scalar(db.select(Customer.display_name)) == "Reader"


def test_emails_stuck_sending_are_recovered_once_and_sent_once(seeded, as_role):
    from datetime import UTC, datetime, timedelta

    from app.services.courses import certificates

    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Stuck Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/stuck-course/enroll")
    seeded.config["MAIL_BACKEND"] = "none"  # issue it without delivering the email
    try:
        _complete(learner, "stuck-course", lessons[0])
    finally:
        seeded.config["MAIL_BACKEND"] = "memory"
    assert not _certificate_mail()

    def stick(minutes_ago):
        with seeded.app_context():
            cert = db.session.scalar(db.select(CourseCertificate))
            cert.email_status = "sending"
            cert.email_claimed_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
            cert.email_attempts = 1
            db.session.commit()
            return cert.code

    support = as_role("customer_support")

    # A send in progress (claimed just now) is left alone: no recovery, no second send.
    code = stick(1)
    with seeded.app_context():
        assert certificates.recover_stale_sends() == 0
        assert certificates.retry_emails() == {}
    assert support.post(f"{ADMIN_CERTS}/{code}/resend-email", {}).status_code == 409
    assert not _certificate_mail()

    # A send that died (claimed long ago) is recovered once and sent once.
    stick(60)
    detail = support.get(f"{COURSES}/{_course_id(seeded)}/enrollments/{_enrollment_id(seeded)}")
    assert detail.get_json()["data"]["certificate"]["email_stuck"] is True
    with seeded.app_context():
        counts = certificates.retry_emails()
        assert counts == {"recovered": 1, "sent": 1}
        assert certificates.retry_emails() == {}  # nothing left; never re-sent
        assert certificates.recover_stale_sends() == 0
        cert = db.session.scalar(db.select(CourseCertificate))
        assert cert.email_status == "sent" and cert.email_attempts == 2
        assert cert.email_claimed_at is None and cert.emailed_at is not None
    assert len(_certificate_mail()) == 1

    # Two runners recovering the same stuck row: only the first wins.
    stick(60)
    with seeded.app_context():
        stale = db.session.scalar(db.select(CourseCertificate))
        claim = stale.email_claimed_at
        assert certificates.recover_stale_sends() == 1
        # The second runner saw the same stale claim; its conditional update now misses.
        db.session.execute(
            db.update(CourseCertificate)
            .where(CourseCertificate.id == stale.id)
            .values(email_status="sending", email_claimed_at=datetime.now(UTC))
        )
        db.session.commit()
        missed = db.session.execute(
            db.update(CourseCertificate)
            .where(
                CourseCertificate.id == stale.id,
                CourseCertificate.email_status == "sending",
                CourseCertificate.email_claimed_at == claim,
            )
            .values(email_status="failed")
        )
        assert missed.rowcount == 0
        db.session.rollback()

    # Staff may force a resend of a stuck row, once.
    code = stick(60)
    assert support.post(f"{ADMIN_CERTS}/{code}/resend-email", {}).status_code == 200
    assert len(_certificate_mail()) == 2


def test_recovery_respects_the_retry_limit(seeded, as_role):
    from datetime import UTC, datetime, timedelta

    from app.services.courses import certificates

    editor = as_role("editor")
    _, _, lessons = ready_course(editor, "Limit Course", lessons=1)
    learner = _verified(seeded)
    learner.post(f"{LEARN}/limit-course/enroll")
    seeded.config["MAIL_BACKEND"] = "none"
    try:
        _complete(learner, "limit-course", lessons[0])
    finally:
        seeded.config["MAIL_BACKEND"] = "memory"
    with seeded.app_context():
        cert = db.session.scalar(db.select(CourseCertificate))
        cert.email_status = "sending"
        cert.email_attempts = certificates.EMAIL_RETRY_LIMIT
        cert.email_claimed_at = datetime.now(UTC) - timedelta(hours=2)
        db.session.commit()
        assert certificates.retry_emails() == {"recovered": 1}
        cert = db.session.scalar(db.select(CourseCertificate))
        assert cert.email_status == "failed"  # visible to staff, not retried endlessly
    assert not _certificate_mail()


def _course_id(app):
    with app.app_context():
        return db.session.scalar(db.select(CourseEnrollment.course_id))


def _enrollment_id(app):
    with app.app_context():
        return db.session.scalar(db.select(CourseEnrollment.id))


def test_only_settings_managers_set_the_certificate_signatory(seeded, as_role):
    editor = as_role("editor")  # may publish courses, but not change site settings
    assert editor.get("/api/v1/admin/settings").status_code == 403
    res = editor.patch(
        "/api/v1/admin/settings", {"values": {"certificates.signatory_name": "Someone"}}
    )
    assert res.status_code == 403
    groups = as_role("super_admin").get("/api/v1/admin/settings").get_json()["data"]["groups"]
    assert "Certificates" in {g["name"] for g in groups}

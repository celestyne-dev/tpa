"""Explicit management commands (nothing runs automatically at startup).

flask --app wsgi admin create-superadmin --email you@example.com --name "Your Name"
flask --app wsgi admin sync-roles
flask --app wsgi rbac sync
flask --app wsgi seed sample-content
flask --app wsgi cms seed-defaults
flask --app wsgi content publish-due
flask --app wsgi content fix-topic-slug OLD NEW [--dry-run]
flask --app wsgi publish worker
flask --app wsgi media prune
"""

from __future__ import annotations

import re
import subprocess
import sys

import click
from flask import Flask, current_app
from flask.cli import AppGroup
from sqlalchemy import select

from .auth.passwords import password_problems
from .auth.permissions import RoleName
from .auth.rbac import sync_rbac
from .auth.roles import active_super_admin_count, sync_roles
from .extensions import db
from .models import User

admin_cli = AppGroup("admin", help="Administrator account management.")
seed_cli = AppGroup("seed", help="Development data imports.")
cms_cli = AppGroup("cms", help="CMS defaults.")
content_cli = AppGroup("content", help="Content publication tasks.")
rbac_cli = AppGroup("rbac", help="Roles and permissions.")


@rbac_cli.command("sync")
def rbac_sync_command():
    """Synchronise the permission catalogue, built-in roles and templates (idempotent).

    Never deletes users, roles or assignments. Built-in roles are reset to their
    definitions; templates and custom roles keep their edits (minus any grant
    that is no longer allowed).
    """
    counts = sync_rbac()
    db.session.commit()
    click.echo(", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in counts.items()))


@admin_cli.command("sync-roles")
def sync_roles_command():
    """Create the built-in roles and templates if they are missing (idempotent)."""
    created = sync_roles()
    db.session.commit()
    click.echo(f"Roles ready ({created} created).")


@admin_cli.command("reset-mfa")
@click.argument("email")
@click.option("--yes", is_flag=True, help="Don't ask for confirmation.")
def reset_mfa(email: str, yes: bool):
    """Turn off two-step sign-in for one administrator (lost phone and recovery codes).

    Run on the server by someone with shell access; signs the person out everywhere and
    is recorded in the audit log. They set it up again after signing in.
    """
    from .auth.session import revoke_all_sessions
    from .services import audit_service

    user = db.session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise click.ClickException("No administrator with that email.")
    if not user.mfa_salt and not user.mfa_pending_salt:
        click.echo("Two-step sign-in is not on for this account; nothing changed.")
        return
    if not yes:
        click.confirm(f"Turn off two-step sign-in for {user.email}?", abort=True)
    user.mfa_salt = user.mfa_pending_salt = user.mfa_enabled_at = None
    user.mfa_last_step = None
    user.mfa_recovery_codes = None
    revoke_all_sessions(user)
    audit_service.record("auth.mfa_reset", "user", user.id, details={"by": "server command"})
    db.session.commit()
    click.echo(f"Two-step sign-in turned off for {user.email}; all sessions signed out.")


@admin_cli.command("create-superadmin")
@click.option("--email", required=True, help="Email address used to sign in.")
@click.option("--name", "display_name", required=True, help="Display name.")
@click.option(
    "--password-stdin",
    is_flag=True,
    help="Read the password from standard input instead of an interactive prompt.",
)
def create_superadmin(email: str, display_name: str, password_stdin: bool):
    """Bootstrap the first super administrator. Refuses if one already exists."""
    from .services.admin.user_admin import create_user

    sync_roles()
    if active_super_admin_count() > 0:
        raise click.ClickException(
            "An active super administrator already exists. Add further administrators from "
            "the admin dashboard (Users)."
        )
    email = email.strip().lower()
    if db.session.scalar(select(User.id).where(User.email == email)):
        raise click.ClickException("An account with this email already exists.")
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    problems = password_problems(password, email=email)
    if problems:
        raise click.ClickException("Password rejected: " + " ".join(problems))
    user = create_user(
        {
            "email": email,
            "display_name": display_name,
            "password": password,
            "roles": [RoleName.SUPER_ADMIN.value],
        },
        actor=None,
    )
    db.session.commit()
    click.echo(f"Super administrator created: {user.email} (id {user.id}).")


@seed_cli.command("sample-content")
@click.option("--allow-production", is_flag=True, help="Required to run in production.")
def seed_sample(allow_production: bool):
    """Import the six sample articles and eight topics (idempotent; never overwrites)."""
    from .services.seed_service import seed_sample_content

    if not current_app.config.get("ALLOW_SAMPLE_SEED") and not allow_production:
        raise click.ClickException(
            "Sample content is not seeded in production. Pass --allow-production to override."
        )
    counts = seed_sample_content()
    db.session.commit()
    click.echo("Sample content: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


@cms_cli.command("seed-defaults")
def seed_defaults():
    """Create editable default navigation menus and homepage sections (only if missing)."""
    from .services.seed_service import seed_cms_defaults

    counts = seed_cms_defaults()
    db.session.commit()
    click.echo("CMS defaults: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


def _publish_due_locked() -> dict:
    """Run the scheduler under an exclusive lock so overlapping timers never collide."""
    import fcntl
    from pathlib import Path

    from .services.publication_service import publish_due_scheduled

    lock_dir = Path(current_app.config["PUBLISH_RELEASES_DIR"]).parent
    lock_dir.mkdir(parents=True, exist_ok=True)
    with open(lock_dir / ".publish-due.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"published": [], "failed": [], "skipped": True}
        result = publish_due_scheduled()
        db.session.commit()
        return result


@content_cli.command("publish-due")
def publish_due():
    """Publish scheduled articles and pages whose time has passed (idempotent; queues a rebuild).

    Also queues one rebuild when a section visibility window or an announcement starts or ends.
    """
    result = _publish_due_locked()
    if result.get("skipped"):
        click.echo("Another scheduler run is in progress; skipped.")
    elif result["published"]:
        click.echo(
            f"Published {len(result['published'])} scheduled article(s)/page(s): "
            + ", ".join(result["published"])
            + ". A site rebuild has been queued."
        )
    else:
        click.echo("No scheduled articles or pages are due.")
    if result.get("boundary_rebuild"):
        click.echo("A scheduled section or announcement changed visibility; a rebuild was queued.")
    if result.get("failed"):
        click.echo(f"{len(result['failed'])} item(s) failed; see the audit log.", err=True)
        sys.exit(1)


@content_cli.command("fix-topic-slug")
@click.argument("old_slug")
@click.argument("new_slug")
@click.option("--dry-run", is_flag=True, help="Show what would change and roll back.")
def fix_topic_slug_command(old_slug: str, new_slug: str, dry_run: bool):
    """Correct a topic's slug in place (e.g. elationships-and-connection to
    relationships-and-connection): same topic and articles, a 301 from the old URL,
    menu links updated. Safe to run twice; refuses if both slugs exist."""
    from .services.topic_links import fix_topic_slug
    from .utils.errors import APIError

    try:
        result = fix_topic_slug(old_slug, new_slug)
    except APIError as exc:
        db.session.rollback()
        click.echo(f"Not changed: {exc.message}", err=True)
        sys.exit(1)
    if dry_run:
        db.session.rollback()
        click.echo(f"Dry run (rolled back): {result}")
        return
    db.session.commit()
    click.echo(f"Done: {result}")


publish_cli = AppGroup("publish", help="Static site publishing jobs.")


@publish_cli.command("worker")
@click.option("--once", is_flag=True, help="Process at most one due job, then exit.")
@click.option("--interval", default=5, show_default=True, help="Seconds between polls.")
@click.option(
    "--no-scheduler",
    is_flag=True,
    help="Do not publish due scheduled articles (when a separate timer does it).",
)
def publish_worker(once: bool, interval: int, no_scheduler: bool):
    """Run queued site builds one at a time (systemd: tpa-publish-worker.service)."""
    import signal
    import time

    from .services import publishing
    from .services.site_builder import LocalReleaseBuilder

    stop = {"flag": False}

    def _stop(*_):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    click.echo(f"Publishing worker {publishing.worker_id()} started.")
    while not stop["flag"]:
        if not no_scheduler:
            try:
                _publish_due_locked()
            except Exception:  # never let the scheduler stop the worker
                db.session.rollback()
                current_app.logger.exception("Scheduled publishing failed")
        try:
            from .services.commerce.product_files import scan_pending

            if scan_pending():
                db.session.commit()
        except Exception:  # never let scanning stop the worker
            db.session.rollback()
            current_app.logger.exception("Product file scanning failed")
        job = publishing.claim_next()
        if job is not None:
            click.echo(f"Building job {job.id} ({', '.join(job.reasons[:5])})...")
            job = publishing.run_job(job, LocalReleaseBuilder())
            click.echo(f"Job {job.id}: {job.status}" + (f" — {job.error}" if job.error else ""))
        db.session.remove()
        if once:
            break
        for _ in range(max(1, interval) * 5):
            if stop["flag"]:
                break
            time.sleep(0.2)
    click.echo("Publishing worker stopped.")


@publish_cli.command("request")
@click.option("--reason", default="manual_cli", show_default=True)
def publish_request(reason: str):
    """Queue a site rebuild now (picked up by the worker)."""
    from .services.publishing import request_build

    job = request_build(reason, None, trigger="manual")
    db.session.commit()
    click.echo(f"Queued publishing job {job.id}.")


@publish_cli.command("status")
def publish_status():
    """Show the latest publishing jobs."""
    from .services.publishing import list_jobs

    jobs, _ = list_jobs({"page": 1, "page_size": 10})
    for job in jobs:
        click.echo(
            f"#{job['id']:<5} {job['status']:<10} attempts={job['attempts']} "
            f"created={job['created_at']} release={job['release'] or '-'} {job['error'] or ''}"
        )


media_cli = AppGroup("media", help="Media library maintenance.")


@media_cli.command("prune")
@click.option("--days", type=int, default=None, help="Override MEDIA_SUPERSEDED_RETENTION_DAYS.")
def media_prune(days: int | None):
    """Delete superseded image variants older than the retention period."""
    from .services.admin.media_admin import prune_superseded

    result = prune_superseded(days)
    db.session.commit()
    click.echo(
        f"Removed {result['variants_removed']} superseded file(s), "
        f"freed {result['bytes_freed'] / 1024:.0f} KB."
    )


@media_cli.command("generate-preset")
@click.argument("preset")
@click.option("--all", "all_assets", is_flag=True, help="Every active uploaded image.")
@click.option("--id", "asset_ids", type=int, multiple=True, help="Specific media ids.")
def media_generate_preset(preset: str, all_assets: bool, asset_ids: tuple[int, ...]):
    """Generate an on-demand preset (e.g. ebook_cover) from the retained originals."""
    from .services.admin.media_admin import generate_preset

    count = generate_preset(preset, None if all_assets else list(asset_ids))
    db.session.commit()
    click.echo(f"Generated '{preset}' for {count} image(s).")


@media_cli.command("verify")
def media_verify():
    """Check that every current variant file exists in storage."""
    from .services.admin.media_admin import verify_files

    missing = verify_files()
    if missing:
        for key in missing[:50]:
            click.echo(f"missing: {key}")
        click.echo(f"{len(missing)} file(s) missing.", err=True)
        sys.exit(1)
    click.echo("All media files are present.")


commerce_cli = AppGroup("commerce", help="Digital products, orders and payments.")


@commerce_cli.command("expire-orders")
def commerce_expire_orders():
    """Cancel unpaid orders past their expiry time (the worker also does this)."""
    from .services.commerce.payments import expire_orders

    count = expire_orders()
    db.session.commit()
    click.echo(f"Cancelled {count} expired unpaid order(s).")


@commerce_cli.command("scan-files")
def commerce_scan_files():
    """Run the configured malware scanner on product files awaiting a scan."""
    from .services.commerce.product_files import scan_pending, scanner_configured

    if not scanner_configured():
        click.echo("PRODUCT_FILES_SCAN_COMMAND is not set; nothing to scan.")
        return
    counts = scan_pending(limit=100)
    db.session.commit()
    click.echo(", ".join(f"{k}={v}" for k, v in counts.items()))


@commerce_cli.command("payments-status")
def commerce_payments_status():
    """Show payment configuration and checkout readiness (never prints secrets)."""
    from .payments.config import effective_mode, provider_status, readiness

    status = provider_status()
    click.echo(
        f"Provider: {status['label']} | key: "
        f"{status['key_mode'] or 'not configured'} | effective checkout mode: {effective_mode()}"
    )
    for check in readiness()["checks"]:
        click.echo(f"[{'x' if check['ok'] else ' '}] ({check['required_for']}) {check['label']}")


@commerce_cli.command("seed-catalogue")
def commerce_seed_catalogue():
    """Create the starter categories, collection and coming-soon titles (only if missing)."""
    from .services.seed_service import seed_commerce_catalogue

    counts = seed_commerce_catalogue()
    db.session.commit()
    click.echo("Catalogue: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


memberships_cli = AppGroup("memberships", help="Membership subscriptions (Paystack test mode).")


@memberships_cli.command("reconcile")
@click.option(
    "--no-provider", is_flag=True, help="Skip Paystack status checks (time-based rules only)."
)
def memberships_reconcile(no_provider: bool):
    """Start grace periods, end expired or cancelled memberships, retry early webhooks.

    Idempotent; it can shorten or end access but never extends paid access.
    """
    from .services.memberships.lifecycle import reconcile

    counts = reconcile(check_provider=not no_provider)
    click.echo("Memberships: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


analytics_cli = AppGroup("analytics", help="First-party website analytics.")


@analytics_cli.command("maintain")
def analytics_maintain():
    """Roll up completed days, then apply retention (raw rows, rollups, daily salts)."""
    from .services.analytics.rollup import maintain

    counts = maintain()
    click.echo("Analytics: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


newsletter_cli = AppGroup("newsletter", help="The Positive Reset: email queue, automations.")


@newsletter_cli.command("worker")
@click.option("--once", is_flag=True, help="Run a single pass, then exit.")
@click.option("--interval", default=10, show_default=True, help="Seconds between passes.")
def newsletter_worker(once: bool, interval: int):
    """Send queued email, run automations and scheduled campaigns (tpa-email-worker)."""
    import signal
    import time

    from .services.newsletter import queue
    from .services.newsletter.worker import run_cycle

    stop = {"flag": False}

    def _stop(*_):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    worker = queue.worker_id()
    click.echo(f"Email worker {worker} started.")
    while not stop["flag"]:
        result = run_cycle(worker=worker)
        delivery = result.get("delivery")
        if isinstance(delivery, dict) and delivery.get("sent"):
            click.echo(f"Processed {delivery['sent']} message(s): {delivery['statuses']}")
        db.session.remove()
        if once:
            break
        for _ in range(max(1, interval) * 5):
            if stop["flag"]:
                break
            time.sleep(0.2)
    click.echo("Email worker stopped.")


@newsletter_cli.command("status")
def newsletter_status():
    """Show sending mode, readiness and queue counts (never prints credentials)."""
    from sqlalchemy import func, select

    from .models import EmailMessage
    from .services.newsletter import config as email_config

    click.echo(
        f"Sending mode: {email_config.sending_mode()} | backend: {email_config.backend_name()} "
        f"(configured: {email_config.backend_configured()}) | signup open: "
        f"{email_config.signup_open()}"
    )
    for check in email_config.readiness()["checks"]:
        click.echo(f"[{'x' if check['ok'] else ' '}] {check['label']}")
    rows = db.session.execute(
        select(EmailMessage.status, func.count()).group_by(EmailMessage.status)
    ).all()
    click.echo("Queue: " + (", ".join(f"{s}={n}" for s, n in rows) or "empty"))


@newsletter_cli.command("seed-defaults")
def newsletter_seed_defaults():
    """Add the starter email templates and (draft) automations that are missing."""
    from .services.newsletter.starter import ensure_automations, ensure_templates

    templates = ensure_templates()
    automations = ensure_automations()
    db.session.commit()
    click.echo(f"Added {templates} template(s) and {automations} automation(s).")


storage_cli = AppGroup("storage", help="VPS file storage: folders, health and cleanup.")


@storage_cli.command("init")
def storage_init():
    """Create the storage folders (media, premium resources, temp) with safe permissions."""
    from .services.storage_health import init_layout

    for path in init_layout():
        click.echo(f"ok: {path}")


@storage_cli.command("check")
@click.option("--json", "as_json", is_flag=True, help="Print the full report as JSON.")
@click.option("--quick", is_flag=True, help="Skip the file integrity scan.")
def storage_check(as_json: bool, quick: bool):
    """Report disk space, permissions, missing files and backup status.

    Exit code: 0 ok, 1 warnings, 2 critical problems (for monitoring).
    """
    import json

    from .services.storage_health import report

    data = report(integrity=not quick)
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        for area in data["areas"]:
            disk = area["disk"] or {}
            click.echo(
                f"{area['label']}: {area['path']} (mode {area['mode']}, "
                f"{disk.get('free_percent', '?')}% free)"
            )
        for w in data["warnings"]:
            click.echo(f"[{w['level']}] {w['message']}")
        click.echo(f"status: {data['status']}")
    sys.exit({"ok": 0, "warning": 1, "critical": 2}[data["status"]])


@storage_cli.command("cleanup-temp")
def storage_cleanup_temp():
    """Remove abandoned temporary uploads older than UPLOAD_TEMP_MAX_AGE_HOURS."""
    from .services.storage_health import cleanup_temp

    click.echo(f"Removed {cleanup_temp()} stale temporary file(s).")


deploy_cli = AppGroup("deploy", help="Deployment checks (no changes are made).")


@deploy_cli.command("check")
@click.option("--json", "as_json", is_flag=True, help="Print the results as JSON.")
@click.option("--no-database", is_flag=True, help="Skip the database connection and revision.")
def deploy_check(as_json: bool, no_database: bool):
    """Check production settings before (re)starting services. Never prints secrets.

    Exit code: 0 ok, 1 warnings, 2 errors.
    """
    import json

    from .services.deploy_check import run_checks, summary

    results = run_checks(database=not no_database)
    status = summary(results)
    if as_json:
        click.echo(json.dumps({"status": status, "results": results}, indent=2))
    else:
        for r in results:
            click.echo(f"[{r['level']:7}] {r['check']}: {r['message']}")
        click.echo(f"status: {status}")
    sys.exit({"ok": 0, "warning": 1, "error": 2}[status])


monitor_cli = AppGroup("monitor", help="Lightweight monitoring (no changes are made).")


@monitor_cli.command("errors")
@click.option("--unit", default="tpa-api.service", show_default=True, help="systemd unit.")
@click.option(
    "--cursor-file",
    default="/var/lib/tpa/state/error-alert.cursor",
    show_default=True,
    help="Where journalctl keeps its place between runs.",
)
@click.option("--since", "first_since", default="-15min", show_default=True,
              help="How far back the first run looks (no cursor yet).")  # fmt: skip
def monitor_errors(unit: str, cursor_file: str, first_since: str):
    """Email a summary of new unhandled API errors to ERROR_ALERT_EMAIL.

    Exit code: 0 no new errors or alert sent; 1 errors found but no alert could be sent
    (no ERROR_ALERT_EMAIL or delivery failed); 2 the journal couldn't be read.
    """
    from .services import error_alerts, mail

    try:
        lines = error_alerts.read_journal(unit, cursor_file, first_since)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as err:
        click.echo(f"Could not read the journal for {unit}: {err}", err=True)
        sys.exit(2)
    summary = error_alerts.summarise(lines)
    if summary.count == 0:
        click.echo("No new unhandled API errors.")
        return
    cfg = current_app.config
    tier = cfg.get("TPA_ENVIRONMENT") or ""
    text = error_alerts.message_text(
        summary, unit=unit, tier=tier, release=cfg.get("RELEASE_ID", "unknown")
    )
    click.echo(text)
    to = (cfg.get("ERROR_ALERT_EMAIL") or "").strip()
    if not to:
        click.echo("ERROR_ALERT_EMAIL is not set: nothing was emailed.", err=True)
        sys.exit(1)
    subject = f"[TPA {tier or 'server'}] {summary.count} unhandled API error(s)"
    try:
        method = mail.send(mail.EmailMessage(to=to, subject=subject, text=text))
    except mail.MailNotConfiguredError:
        click.echo("Email delivery is not configured (MAIL_BACKEND): nothing was sent.", err=True)
        sys.exit(1)
    except mail.MailDeliveryError:
        click.echo("The alert email could not be delivered.", err=True)
        sys.exit(1)
    click.echo(f"Alert sent ({method}).")


legacy_cli = AppGroup("legacy", help="Legacy website SEO migration (Batch 12.4A).")


class _Undo(Exception):
    """Rolls a validation savepoint back."""


EXPORT_FIELDS = (
    "path", "kind", "slug", "title", "status", "indexable", "author", "published_at",
    "source", "original_url", "original_slug",
)  # fmt: skip


@legacy_cli.command("export-cms")
@click.option("--out", required=True, type=click.Path(dir_okay=False), help="CSV to write.")
def legacy_export_cms(out: str):
    """Write the new site's live public URLs (read-only) for `python -m legacy_migration map`."""
    from legacy_migration.core import path_key, write_csv

    from .models import Article
    from .services.article_service import published_filter
    from .services.seo_service import article_path, sitemap_entries

    rows: dict[str, dict] = {}
    for entry in sitemap_entries():
        key = path_key(entry["path"])
        rows[key] = {"path": key, "kind": entry["type"], "status": "live", "indexable": "yes"}
    for article in db.session.scalars(select(Article).where(published_filter())):
        key = article_path(article.slug)
        row = rows.setdefault(key, {"path": key, "status": "live", "indexable": "no"})
        row.update(
            kind="article",
            slug=article.slug,
            title=article.title,
            author=article.author.display_name if article.author else "",
            published_at=(article.first_published_at or article.published_at).isoformat(),
            source=article.source,
            original_url=article.original_url or "",
            original_slug=article.original_slug or "",
        )
    for row in rows.values():
        if row.get("kind") == "topic":
            row["slug"] = row["path"].rsplit("/", 1)[-1]
    count = write_csv(out, EXPORT_FIELDS, sorted(rows.values(), key=lambda r: r["path"]))
    click.echo(f"Wrote {count} live public URL(s) to {out}.")


@legacy_cli.command("import-redirects")
@click.argument("mapping_csv", type=click.Path(exists=True, dir_okay=False))
@click.option("--apply", "apply_changes", is_flag=True, help="Write (default: dry run).")
@click.option("--actor-email", default="", help="Administrator recorded in the audit log.")
def legacy_import_redirects(mapping_csv: str, apply_changes: bool, actor_email: str):
    """Create CMS 301 redirects for approved REDIRECT_301 rows.

    Never overwrites: a path that already has a redirect, or is a live article or page on
    the new site, is skipped. The mapping must validate without errors first.
    """
    from legacy_migration.core import path_key, read_csv, truthy
    from legacy_migration.mapping import validate

    from .models import Redirect
    from .services import redirect_service
    from .services.seo_service import sitemap_entries
    from .utils.errors import ConflictError, ValidationError

    rows = read_csv(mapping_csv)
    errors = [p for p in validate([dict(r) for r in rows]) if p["severity"] == "error"]
    if errors:
        for p in errors[:20]:
            click.echo(f"error {p['code']}: {p['legacy_path']} {p['message']}", err=True)
        raise click.ClickException(f"The mapping has {len(errors)} error(s); nothing imported.")
    actor = None
    if actor_email:
        actor = db.session.scalar(select(User).where(User.email == actor_email.lower()))
        if actor is None:
            raise click.ClickException(f"No user {actor_email}.")
    existing = set(db.session.scalars(select(Redirect.source_path)))
    live = {path_key(e["path"]) for e in sitemap_entries()}
    counts = {"created": 0, "skipped_existing": 0, "skipped_live_page": 0, "not_approved": 0}
    failed, pending = [], []
    for row in rows:
        if (row.get("action") or "").upper() != "REDIRECT_301":
            continue
        if not truthy(row.get("approved")):
            counts["not_approved"] += 1
            continue
        source = path_key(row["legacy_path"])
        if source in existing:
            counts["skipped_existing"] += 1
            continue
        if source in live:
            counts["skipped_live_page"] += 1
            continue
        data = {
            "source_path": source,
            "destination": path_key(row["target_path"]),
            "status_code": 301,
            "note": f"Legacy migration: {row.get('reason', '')}"[:300],
        }
        # Pass 1: validate inside a savepoint that is always rolled back (nothing kept).
        try:
            with db.session.begin_nested():
                redirect_service.create_redirect(data, actor, origin="import")
                raise _Undo
        except _Undo:
            existing.add(source)
            pending.append(data)
            counts["created"] += 1
        except (ValidationError, ConflictError) as exc:
            detail = getattr(exc, "details", None) or {}
            failed.append((source, "; ".join(m for v in detail.values() for m in v) or str(exc)))
    db.session.rollback()
    if apply_changes and not failed:
        # Pass 2: every row validated, so write them all in one transaction.
        for data in pending:
            redirect_service.create_redirect(data, actor, origin="import")
        db.session.commit()
    for source, message in failed:
        click.echo(f"failed {source}: {message}", err=True)
    mode = "Applied" if apply_changes and not failed else "Dry run (nothing written)"
    click.echo(f"{mode}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    if failed:
        raise click.ClickException(f"{len(failed)} redirect(s) failed validation; nothing written.")


_LINK_FIELDS = ("href", "url", "button_href", "link", "path", "cta_href")
_TEXT_LINKS = re.compile(r"""\]\(((?:https?://|/)[^)\s]*)\)|href=["']([^"']+)["']""")


def _links_in(value, found: list[str]) -> list[str]:
    """Every link in CMS JSON: link fields, Markdown links and HTML hrefs in text."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _LINK_FIELDS and isinstance(item, str) and item.strip():
                found.append(item.strip())
            else:
                _links_in(item, found)
    elif isinstance(value, list):
        for item in value:
            _links_in(item, found)
    elif isinstance(value, str) and ("](" in value or "href=" in value):
        found += [a or b for a, b in _TEXT_LINKS.findall(value)]
    return found


@legacy_cli.command("check-links")
@click.argument("cleanup_csv", type=click.Path(exists=True, dir_okay=False))
@click.option("--legacy-host", multiple=True, default=("thinkpositivealways.com",))
def legacy_check_links(cleanup_csv: str, legacy_host: tuple[str, ...]):
    """Report navigation and internal links that point at legacy URLs (read-only).

    A link is reported when its path is in the cleanup decisions with any outcome other
    than KEEP_200 (redirected, retired, left to 404 or unresolved). Exit code 1 if any.
    """
    from urllib.parse import urlsplit

    from legacy_migration.core import path_key, read_csv, same_site

    from .cms.defaults import DEFAULT_MENUS
    from .models import Article, Page, Topic
    from .services.article_service import published_filter
    from .services.navigation_service import menu_tree

    decisions = {}
    for row in read_csv(cleanup_csv):
        key = row.get("path_key") or path_key(row.get("legacy_path", ""))
        outcome = row.get("effective_class") or row.get("action", "")
        if key and outcome not in ("KEEP_200", "KEEP"):
            decisions.setdefault(key, (outcome, row.get("effective_target", "")))
    hosts = [urlsplit(current_app.config.get("SITE_URL", "")).netloc, *legacy_host]
    sources: list[tuple[str, object]] = [
        (f"menu:{key}", menu_tree(key, visible_only=False)) for key in DEFAULT_MENUS
    ]
    sources += [
        (f"article:{a.slug}", a.body)
        for a in db.session.scalars(select(Article).where(published_filter()))
    ]
    sources += [
        (f"page:{p.published_path}", p.published_snapshot)
        for p in db.session.scalars(select(Page).where(Page.status == "published"))
    ]
    sources += [(f"topic:{t.slug}", t.intro) for t in db.session.scalars(select(Topic))]
    findings = []
    for where, content in sources:
        for href in _links_in(content, []):
            parts = urlsplit(href)
            if parts.scheme and not (parts.scheme in ("http", "https") and same_site(href, hosts)):
                continue  # external, mailto: ...
            if not parts.scheme and not href.startswith("/"):
                continue
            key = path_key(parts.path or "/")
            if key in decisions:
                outcome, target = decisions[key]
                fix = f" -> link to {target}" if target else " -> remove the link"
                findings.append(f"{where}: {href} is {outcome}{fix}")
    for line in dict.fromkeys(findings):
        click.echo(line)
    click.echo(f"{len(set(findings))} link(s) to legacy URLs.")
    if findings:
        sys.exit(1)


def register_cli(app: Flask) -> None:
    for group in (
        admin_cli,
        seed_cli,
        cms_cli,
        content_cli,
        rbac_cli,
        publish_cli,
        media_cli,
        commerce_cli,
        memberships_cli,
        analytics_cli,
        newsletter_cli,
        storage_cli,
        deploy_cli,
        monitor_cli,
        legacy_cli,
    ):
        app.cli.add_command(group)

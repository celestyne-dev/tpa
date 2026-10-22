"""Explicit management commands (nothing runs automatically at startup).

flask --app wsgi admin create-superadmin --email you@example.com --name "Your Name"
flask --app wsgi admin sync-roles
flask --app wsgi rbac sync
flask --app wsgi seed sample-content
flask --app wsgi cms seed-defaults
flask --app wsgi content publish-due
"""

from __future__ import annotations

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


@content_cli.command("publish-due")
def publish_due():
    """Publish scheduled articles whose time has passed. Rebuild the site afterwards."""
    from .services.publication_service import publish_due_scheduled

    slugs = publish_due_scheduled()
    db.session.commit()
    if slugs:
        click.echo(f"Published {len(slugs)} scheduled article(s): {', '.join(slugs)}")
        click.echo("Run ./scripts/build-production.sh to refresh the static site.")
    else:
        click.echo("No scheduled articles are due.")


def register_cli(app: Flask) -> None:
    for group in (admin_cli, seed_cli, cms_cli, content_cli, rbac_cli):
        app.cli.add_command(group)

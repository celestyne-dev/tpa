"""Batch 08: the backup and restore scripts, run for real against PostgreSQL.

Backs up a migrated database plus image and premium-file folders, sends an
age-encrypted copy "off the server", then restores that copy into a new database and
new folders and compares everything. Also checks that damaged backups are refused and
that retention keeps daily/weekly/monthly copies. Needs TEST_DATABASE_URL (a server
where the role may create databases), pg_dump/pg_restore and age.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "deploy" / "backup" / "tpa-backup.sh"
RESTORE = ROOT / "deploy" / "backup" / "tpa-restore.sh"
MIGRATIONS = str(ROOT / "backend" / "migrations")
PG_BIN = next(
    (p for p in ("/usr/lib/postgresql/16/bin", "/usr/lib/postgresql/17/bin") if Path(p).is_dir()),
    "",
)
URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not URL.startswith("postgresql") or not shutil.which("age") or not shutil.which("flock"),
    reason="Needs TEST_DATABASE_URL (PostgreSQL), age and flock.",
)


def _db_url(name: str) -> str:
    parts = urlsplit(URL)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _psql(url: str, sql: str) -> str:
    psql = str(Path(PG_BIN) / "psql") if PG_BIN else "psql"
    return subprocess.run(
        [psql, "-Atq", "-c", sql, url], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def databases():
    suffix = secrets.token_hex(4)
    names = [f"tpa_bk_src_{suffix}", f"tpa_bk_dst_{suffix}"]
    for name in names:
        _psql(URL, f'CREATE DATABASE "{name}"')
    yield [_db_url(n) for n in names]
    for name in names:
        _psql(URL, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _run(cmd, env, check=True):
    return subprocess.run(
        [str(c) for c in cmd],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=check,
    )


def test_backup_encrypted_offsite_copy_and_full_restore(databases, tmp_path):
    from flask_migrate import upgrade

    from app import create_app
    from app.extensions import db

    source, target = databases
    app = create_app(
        "testing", {"SQLALCHEMY_DATABASE_URI": source, "SQLALCHEMY_ENGINE_OPTIONS": {}}
    )
    with app.app_context():
        upgrade(directory=MIGRATIONS)
        db.session.execute(
            db.text(
                "INSERT INTO site_settings (key, value, updated_at) "
                "VALUES ('site.name', '\"TPA backup test\"', now())"
            )
        )
        db.session.commit()
        db.engine.dispose()
    tables = _psql(
        source,
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'",
    )

    media = tmp_path / "media"
    resources = tmp_path / "resources" / "private"
    (media / "public" / "abc" / "v1").mkdir(parents=True)
    (media / "public" / "abc" / "v1" / "cover-640.webp").write_bytes(os.urandom(4096))
    (media / "private" / "abc").mkdir(parents=True)
    (media / "private" / "abc" / "original.jpg").write_bytes(os.urandom(8192))
    (resources / "ebooks" / "f1" / "v1").mkdir(parents=True)
    (resources / "ebooks" / "f1" / "v1" / "a1b2.pdf").write_bytes(b"%PDF-1.4\n" + os.urandom(20000))
    (resources / "templates" / "f2" / "v3").mkdir(parents=True)
    (resources / "templates" / "f2" / "v3" / "c3d4.xlsx").write_bytes(os.urandom(5000))

    key = tmp_path / "backup.key"
    subprocess.run(["age-keygen", "-o", str(key)], check=True, capture_output=True)
    recipients = tmp_path / "recipients.txt"
    public = subprocess.run(
        ["age-keygen", "-y", str(key)], check=True, capture_output=True, text=True
    ).stdout
    recipients.write_text(public)
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    backups = tmp_path / "backups"
    env = {
        "DATABASE_URL": source,
        "BACKUP_DIR": str(backups),
        "MEDIA_ROOT": str(media),
        "PRODUCT_FILES_ROOT": str(resources),
        "BACKUP_MIN_FREE_MB": "1",
        "BACKUP_AGE_RECIPIENTS_FILE": str(recipients),
        "BACKUP_OFFSITE_COMMAND": f"cp {{file}} {offsite}/",
        "PG_BIN": PG_BIN,
    }
    result = _run([BACKUP, tmp_path / "no-config.env"], env)
    assert "ok" in result.stdout, result.stderr
    status = json.loads((backups / "status.json").read_text())
    assert status["status"] == "ok" and status["verified"] and status["offsite"]
    latest = backups / "latest"
    meta = json.loads((latest / "meta.json").read_text())
    assert meta["alembic_revision"] == _psql(source, "SELECT version_num FROM alembic_version")
    assert oct((backups).stat().st_mode)[-3:] == "700"
    assert not list((backups / "encrypted").glob("*.age"))  # sent away, not kept locally
    encrypted = next(offsite.glob("*.tar.age"))
    assert not encrypted.read_bytes().startswith(b"%PDF")  # really encrypted

    # A damaged backup is refused before anything is touched.
    damaged = tmp_path / "damaged"
    shutil.copytree(latest, damaged)
    with (damaged / "resources.tar").open("r+b") as handle:
        handle.seek(1024)
        handle.write(b"tampered")
    bad = _run([RESTORE, "--from", damaged, "--verify-only"], {"PG_BIN": PG_BIN}, check=False)
    assert bad.returncode != 0 and "damaged" in (bad.stdout + bad.stderr)

    # Without --yes nothing is restored.
    refused = _run(
        [RESTORE, "--from", encrypted, "--identity", key, "--database", target],
        {"PG_BIN": PG_BIN},
        check=False,
    )
    assert refused.returncode != 0 and "--yes" in refused.stdout + refused.stderr
    assert (
        _psql(target, "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        == "0"
    )

    # Disaster recovery: restore the off-server copy into a new database and new folders.
    new_media = tmp_path / "restored" / "media"
    new_resources = tmp_path / "restored" / "resources" / "private"
    restored = _run(
        [
            RESTORE,
            "--from",
            encrypted,
            "--identity",
            key,
            "--database",
            target,
            "--media-root",
            new_media,
            "--resources-root",
            new_resources,
            "--yes",
        ],
        {"PG_BIN": PG_BIN},
    )
    assert "Restore finished" in restored.stdout, restored.stderr
    assert (
        _psql(target, "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        == tables
    )
    assert _psql(target, "SELECT value FROM site_settings WHERE key = 'site.name'") == (
        '"TPA backup test"'
    )
    assert _psql(target, "SELECT version_num FROM alembic_version") == meta["alembic_revision"]
    assert _psql(target, "SELECT count(*) FROM permissions") == _psql(
        source, "SELECT count(*) FROM permissions"
    )
    assert _tree_digest(new_media) == _tree_digest(media)
    assert _tree_digest(new_resources) == _tree_digest(resources)
    assert oct(new_resources.stat().st_mode)[-3:] == "750"

    # Restoring again keeps the previous folders beside the new ones.
    _run(
        [RESTORE, "--from", latest, "--resources-root", new_resources, "--yes"],
        {"PG_BIN": PG_BIN},
    )
    kept = list(new_resources.parent.glob("private.before-restore-*"))
    assert len(kept) == 1 and _tree_digest(kept[0]) == _tree_digest(resources)


def test_backup_failure_is_recorded_and_retention_keeps_daily_weekly_monthly(databases, tmp_path):
    source, _ = databases
    backups = tmp_path / "backups"
    backups.mkdir()
    # Old backups: 10 consecutive days plus older month-end copies.
    old = [f"2026-09-{d:02d}T030000Z" for d in range(1, 31)] + [
        "2026-08-31T030000Z",
        "2026-07-31T030000Z",
    ]
    for name in old:
        (backups / name).mkdir()
    media = tmp_path / "media"
    resources = tmp_path / "resources"
    media.mkdir()
    resources.mkdir()
    env = {
        "DATABASE_URL": source,
        "BACKUP_DIR": str(backups),
        "MEDIA_ROOT": str(media),
        "PRODUCT_FILES_ROOT": str(resources),
        "BACKUP_MIN_FREE_MB": "1",
        "BACKUP_KEEP_DAILY": "3",
        "BACKUP_KEEP_WEEKLY": "2",
        "BACKUP_KEEP_MONTHLY": "3",
        "PG_BIN": PG_BIN,
    }
    _run([BACKUP, tmp_path / "none.env"], env)
    kept = sorted(p.name for p in backups.iterdir() if p.is_dir() and p.name[0].isdigit())
    newest = kept[-1]
    assert newest.startswith("20") and newest not in old
    # 3 newest (today + 30th + 29th), weekly picks and month ends for 3 months.
    assert "2026-09-30T030000Z" in kept and "2026-09-29T030000Z" in kept
    assert "2026-08-31T030000Z" in kept
    assert "2026-07-31T030000Z" not in kept  # beyond 3 months of monthly copies
    assert "2026-09-10T030000Z" not in kept
    assert len(kept) <= 3 + 2 + 3

    # A failing dump is reported as failed and leaves no partial backup.
    env["DATABASE_URL"] = _db_url("tpa_does_not_exist_" + secrets.token_hex(3))
    failed = _run([BACKUP, tmp_path / "none.env"], env, check=False)
    assert failed.returncode != 0
    status = json.loads((backups / "status.json").read_text())
    assert status["status"] == "failed" and "failed" in status["message"]
    assert not list(backups.glob("*.partial"))

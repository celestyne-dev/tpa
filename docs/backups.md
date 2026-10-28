# Backups and disaster recovery (Batch 08)

Primary storage is the Hostinger VPS: the PostgreSQL database, images and premium files
all live there. Backups protect against mistakes, damaged files and losing the server.

| What                                                                                         | Where it lives                        | How it is backed up                                        |
| -------------------------------------------------------------------------------------------- | ------------------------------------- | ---------------------------------------------------------- |
| Database (content, orders, customers, entitlements, courses, learner progress, certificates) | PostgreSQL                            | `pg_dump` custom format, verified with `pg_restore --list` |
| Public images (optimised) and image originals                                                | `MEDIA_ROOT`                          | `media.tar`                                                |
| Premium files and course worksheets (all versions)                                           | `PRODUCT_FILES_ROOT`                  | `resources.tar`                                            |
| Configuration and secrets                                                                    | `backend/.env`, `/etc/tpa/backup.env` | **not** in backups: keep them in a password manager        |
| Redis, temporary uploads, built site releases                                                | —                                     | not needed (rebuilt or transient)                          |

## 1. The backup job

`deploy/backup/tpa-backup.sh` (systemd: `tpa-backup.service` + `tpa-backup.timer`,
nightly) creates `BACKUP_DIR/<UTC time>/` with `db.dump`, `media.tar`, `resources.tar`,
`SHA256SUMS` and `meta.json` (database revision, sizes), then:

1. **Checks space first.** It refuses to start unless the backup folder has room for the
   files plus `BACKUP_MIN_FREE_MB`.
2. **Verifies the backup**: checksums, `pg_restore --list` and tar listings. A backup that
   fails verification is deleted and reported as failed.
3. **Makes an encrypted off-server copy** (optional, recommended): the backup is
   encrypted with **age** public keys (or GPG) and sent by `BACKUP_OFFSITE_COMMAND`, for
   example `rclone` to any storage provider or `rsync` over SSH to another server. Only
   public keys are on the VPS; the secret key is kept offline. This copy exists for
   disaster recovery only; primary storage stays on Hostinger.
4. **Applies retention**: the newest `BACKUP_KEEP_DAILY` backups, plus the newest of each
   of the last `BACKUP_KEEP_WEEKLY` weeks and `BACKUP_KEEP_MONTHLY` months.
5. **Records the result** in `BACKUP_STATUS_FILE`: time, size, verified, off-server copy,
   ok or failed. `/admin/storage` shows it and warns when the last backup failed or is
   older than `BACKUP_MAX_AGE_HOURS` (36 by default); `flask storage check` does the same.

The database password is passed to `pg_dump`, `psql` and `pg_restore` through
`PGPASSWORD` (`deploy/backup/tpa-pg-env.sh`), never as part of a command-line URL,
because other local users can read command lines with `ps`. The same applies to the
restore script's `--database`. A lock prevents overlapping runs. Everything is created with owner-only permissions
(`umask 077`; the backup folder is `0700`). Backups and secrets are never committed to
Git.

### Setup

```bash
sudo install -d -m 0700 /etc/tpa /var/backups/tpa
sudo cp /var/www/tpa/deploy/backup/backup.env.example /etc/tpa/backup.env
sudo chmod 600 /etc/tpa/backup.env      # set DATABASE_URL and paths

# Encryption key pair for off-server copies. Do this on YOUR computer, not the VPS:
age-keygen -o tpa-backup.key            # SECRET: store offline (password manager + paper)
age-keygen -y tpa-backup.key            # prints the public key, e.g. age1...
# On the VPS: put the public key(s) in /etc/tpa/backup-recipients.txt and set
#   BACKUP_AGE_RECIPIENTS_FILE=/etc/tpa/backup-recipients.txt
#   BACKUP_OFFSITE_COMMAND=rclone copy {file} offsite:tpa-backups/

sudo cp /var/www/tpa/deploy/systemd/tpa-backup.{service,timer}.example /etc/systemd/system/
# (rename without .example)
sudo systemctl daemon-reload && sudo systemctl enable --now tpa-backup.timer
sudo systemctl start tpa-backup.service && journalctl -u tpa-backup -n 50
```

Add `BACKUP_STATUS_FILE=/var/lib/tpa/backup-status.json` to `backend/.env` too.

**Recovery objectives (with the defaults):** at most about 24 hours of data can be lost
(one nightly backup; run the job more often if orders come in steadily). Recovery takes
roughly as long as copying the files back plus `pg_restore`, typically well under an
hour for a small library.

## 2. Monitoring and storage

- `/admin/storage` → Backups card and findings; `flask storage check` hourly.
- `du -sh /var/backups/tpa/*` to see backup sizes; a separate disk or volume for
  `BACKUP_DIR` protects against a full system disk.
- Off-server storage: check the provider's usage, and that new files arrive daily.

## 3. Restoring

`deploy/backup/tpa-restore.sh` verifies before it changes anything and changes nothing
without `--yes`.

```bash
# Check a backup (local folder or encrypted copy):
sudo /var/www/tpa/deploy/backup/tpa-restore.sh --from /var/backups/tpa/latest --verify-only
sudo /var/www/tpa/deploy/backup/tpa-restore.sh --from tpa-2026-10-27T031000Z.tar.age \
  --identity ~/tpa-backup.key --verify-only
```

**Recommended (safest):** restore the database into a **new** database, check it, then
point `DATABASE_URL` at it.

```bash
sudo -u postgres createdb --owner tpa tpa_restored
sudo systemctl stop tpa-api tpa-publish-worker tpa-email-worker
sudo /var/www/tpa/deploy/backup/tpa-restore.sh --from /var/backups/tpa/latest \
  --database postgresql://tpa:…@127.0.0.1/tpa_restored \
  --media-root /var/lib/tpa/media --resources-root /var/lib/tpa/resources/private --yes
sudo chown -R tpa:www-data /var/lib/tpa/media /var/lib/tpa/resources/private
# set DATABASE_URL=…/tpa_restored in backend/.env, then:
cd /var/www/tpa/backend && set -a && . ./.env && set +a
.venv/bin/flask --app wsgi db upgrade && .venv/bin/flask --app wsgi storage check
sudo systemctl start tpa-api tpa-publish-worker tpa-email-worker
```

The file folders are extracted beside the targets and swapped in; the previous folders
are kept as `*.before-restore-<time>` until you remove them. Restoring onto the live
database (`--database` pointing at it) runs `pg_restore --clean` in one transaction.

**Disaster recovery (new VPS):** follow `docs/hostinger-vps.md` up to step 6, copy the
latest encrypted backup and your secret key to the new server, restore as above, restore
`.env` from your password manager, then finish the guide (systemd, Nginx, DNS).

## 4. Tested recovery procedure

The procedure above is exercised by `backend/tests/test_backup_scripts.py`, which runs
the real scripts against PostgreSQL (with `TEST_DATABASE_URL`):

1. migrates a database to the current revision and adds data; creates image and premium
   files in category folders;
2. runs `tpa-backup.sh` with an age key and an "off-server" copy command, and checks the
   status file (ok, verified, off-server copy), the recorded database revision and the
   `0700` backup folder, and that the copy is really encrypted;
3. checks that a tampered backup is refused (`--verify-only`), and that nothing happens
   without `--yes`;
4. restores **the encrypted off-server copy** into a new database and new folders and
   compares table count, data, database revision and permissions, plus a SHA-256 of
   every image and premium file;
5. restores again and checks the previous folder was kept;
6. checks retention (daily/weekly/monthly) and that a failing run is recorded as
   `failed` with no partial backup left.

Repeat a manual test restore on the server every few months, and after changing the
backup configuration: restore the latest backup into `tpa_restore_test` and new folders,
run `flask storage check` against them, then delete them.

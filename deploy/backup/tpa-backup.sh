#!/usr/bin/env bash
# Think Positive Always — backup of the database, images and premium files.
#
# Creates  $BACKUP_DIR/<UTC timestamp>/  containing
#   db.dump         PostgreSQL custom-format dump (pg_restore)
#   media.tar       MEDIA_ROOT (public optimised images + private originals)
#   resources.tar   PRODUCT_FILES_ROOT (premium resource files)
#   SHA256SUMS      checksums of the three files
#   meta.json       when, what, sizes, database revision
# then verifies it (checksums, pg_restore --list, tar listings), optionally sends an
# encrypted copy off the server, applies retention and writes BACKUP_STATUS_FILE for
# /admin/storage and monitoring. Primary storage stays on this server; the off-server
# copy is for disaster recovery only.
#
# Usage:  tpa-backup.sh [/etc/tpa/backup.env]
# Exit:   0 ok, non-zero on any failure (the status file then says "failed").
set -Eeuo pipefail
umask 077

CONFIG="${1:-/etc/tpa/backup.env}"
if [[ -f "$CONFIG" ]]; then
  # shellcheck disable=SC1090
  set -a; . "$CONFIG"; set +a
fi

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:=/var/backups/tpa}"
: "${MEDIA_ROOT:=/var/lib/tpa/media}"
: "${PRODUCT_FILES_ROOT:=/var/lib/tpa/resources/private}"
: "${BACKUP_KEEP_DAILY:=7}"
: "${BACKUP_KEEP_WEEKLY:=4}"
: "${BACKUP_KEEP_MONTHLY:=6}"
: "${BACKUP_MIN_FREE_MB:=1024}"
: "${BACKUP_STATUS_FILE:=$BACKUP_DIR/status.json}"
: "${BACKUP_AGE_RECIPIENTS_FILE:=}"   # age public keys, one per line (preferred)
: "${BACKUP_GPG_RECIPIENT:=}"         # or a GPG key id / email (public key imported)
: "${BACKUP_OFFSITE_COMMAND:=}"       # e.g. rclone copy {file} offsite:tpa-backups/
: "${BACKUP_KEEP_ENCRYPTED_LOCAL:=no}"
: "${PG_BIN:=}"                       # directory of pg_dump/pg_restore matching the server

pg() { if [[ -n "$PG_BIN" ]]; then "$PG_BIN/$1" "${@:2}"; else "$@"; fi; }
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }

# shellcheck source=tpa-pg-env.sh
. "$(dirname "$(readlink -f "$0")")/tpa-pg-env.sh"
# The password goes to PGPASSWORD, never onto the pg_dump/psql command line.
pg_url_to_env "$DATABASE_URL"
DATABASE_URL="$PG_URL"

STAMP="$(date -u +%Y-%m-%dT%H%M%SZ)"
WORK="$BACKUP_DIR/$STAMP.partial"
FINAL="$BACKUP_DIR/$STAMP"
STARTED="$(date -u +%FT%TZ)"
OFFSITE="false"

write_status() {  # status message size verified
  local tmp
  mkdir -p "$(dirname "$BACKUP_STATUS_FILE")"
  tmp="$(mktemp "$(dirname "$BACKUP_STATUS_FILE")/.status.XXXXXX")"
  python3 - "$tmp" "$1" "$2" "${3:-0}" "${4:-false}" "$STAMP" "$STARTED" "$OFFSITE" <<'PY'
import json, sys
from datetime import datetime, timezone
path, status, message, size, verified, name, started, offsite = sys.argv[1:]
json.dump({
    "status": status,
    "message": message,
    "name": name,
    "started_at": started,
    "finished_at": datetime.now(timezone.utc).isoformat(),
    "size_bytes": int(size),
    "verified": verified == "true",
    "offsite": offsite == "true",
}, open(path, "w"))
PY
  chmod 0644 "$tmp"   # read by the application (no secrets inside)
  mv -f "$tmp" "$BACKUP_STATUS_FILE"
}

on_error() {
  local line="$1"
  log "backup FAILED (line $line)"
  rm -rf "$WORK"
  write_status failed "Backup failed at step on line $line; see the backup service log." 0 false || true
  exit 1
}
trap 'on_error $LINENO' ERR

mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/.lock"
if ! flock -n 9; then
  log "another backup is running"; exit 1
fi

# ---- space check ---------------------------------------------------------------------------
need_kb=$(( $(du -sk "$MEDIA_ROOT" 2>/dev/null | cut -f1 || echo 0) \
          + $(du -sk "$PRODUCT_FILES_ROOT" 2>/dev/null | cut -f1 || echo 0) \
          + BACKUP_MIN_FREE_MB * 1024 ))
free_kb=$(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}')
if (( free_kb < need_kb )); then
  log "not enough space in $BACKUP_DIR: ${free_kb} KB free, ${need_kb} KB needed"
  false
fi

# ---- dump ----------------------------------------------------------------------------------
mkdir -p "$WORK"
log "dumping database"
pg pg_dump --format=custom --no-owner --no-privileges --file "$WORK/db.dump" "$DATABASE_URL"
log "archiving images ($MEDIA_ROOT)"
tar -C "$MEDIA_ROOT" --warning=no-file-changed -cf "$WORK/media.tar" .
log "archiving premium files ($PRODUCT_FILES_ROOT)"
tar -C "$PRODUCT_FILES_ROOT" --warning=no-file-changed --exclude=./.incoming -cf "$WORK/resources.tar" .

revision="$(pg psql -Atqc 'SELECT version_num FROM alembic_version' "$DATABASE_URL" 2>/dev/null || echo unknown)"
(cd "$WORK" && sha256sum db.dump media.tar resources.tar > SHA256SUMS)
python3 - "$WORK" "$STAMP" "$revision" <<'PY'
import json, os, socket, sys
work, stamp, revision = sys.argv[1:]
files = {n: os.path.getsize(os.path.join(work, n)) for n in ("db.dump", "media.tar", "resources.tar")}
json.dump({"name": stamp, "host": socket.gethostname(), "alembic_revision": revision,
           "files": files, "format": 1}, open(os.path.join(work, "meta.json"), "w"), indent=2)
PY

# ---- verify --------------------------------------------------------------------------------
log "verifying"
(cd "$WORK" && sha256sum --quiet -c SHA256SUMS)
pg pg_restore --list "$WORK/db.dump" > /dev/null
tar -tf "$WORK/media.tar" > /dev/null
tar -tf "$WORK/resources.tar" > /dev/null
mv "$WORK" "$FINAL"
ln -sfn "$STAMP" "$BACKUP_DIR/latest"
size=$(du -sb "$FINAL" | cut -f1)

# ---- encrypted off-server copy ----------------------------------------------------------------
if [[ -n "$BACKUP_AGE_RECIPIENTS_FILE" || -n "$BACKUP_GPG_RECIPIENT" ]]; then
  mkdir -p "$BACKUP_DIR/encrypted"
  if [[ -n "$BACKUP_AGE_RECIPIENTS_FILE" ]]; then
    enc="$BACKUP_DIR/encrypted/tpa-$STAMP.tar.age"
    tar -C "$BACKUP_DIR" -cf - "$STAMP" | age -R "$BACKUP_AGE_RECIPIENTS_FILE" -o "$enc"
  else
    enc="$BACKUP_DIR/encrypted/tpa-$STAMP.tar.gpg"
    tar -C "$BACKUP_DIR" -cf - "$STAMP" \
      | gpg --batch --yes --trust-model always --encrypt -r "$BACKUP_GPG_RECIPIENT" -o "$enc"
  fi
  sha256sum "$enc" > "$enc.sha256"
  if [[ -n "$BACKUP_OFFSITE_COMMAND" ]]; then
    log "sending encrypted copy off the server"
    for f in "$enc" "$enc.sha256"; do
      cmd="${BACKUP_OFFSITE_COMMAND//\{file\}/$(printf '%q' "$f")}"
      bash -c "$cmd"
    done
    OFFSITE="true"
    if [[ "$BACKUP_KEEP_ENCRYPTED_LOCAL" != "yes" ]]; then rm -f "$enc" "$enc.sha256"; fi
  fi
fi

# ---- retention: newest N daily, newest per ISO week for W weeks, newest per month for M ----
all=()
shopt -s nullglob
for dir in "$BACKUP_DIR"/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z; do
  [[ -d "$dir" && ! -L "$dir" ]] && all+=("$(basename "$dir")")
done
shopt -u nullglob
mapfile -t all < <(printf '%s\n' "${all[@]}" | sort -r)
declare -A keep=() weeks=() months=()
count=0
for name in "${all[@]}"; do
  day="${name:0:10}"
  week="$(date -u -d "$day" +%G-%V)"
  month="${name:0:7}"
  if (( count < BACKUP_KEEP_DAILY )); then keep[$name]=1; fi
  count=$((count + 1))
  if [[ -z "${weeks[$week]:-}" && ${#weeks[@]} -lt $BACKUP_KEEP_WEEKLY ]]; then
    weeks[$week]=1; keep[$name]=1
  fi
  if [[ -z "${months[$month]:-}" && ${#months[@]} -lt $BACKUP_KEEP_MONTHLY ]]; then
    months[$month]=1; keep[$name]=1
  fi
done
for name in "${all[@]}"; do
  if [[ -z "${keep[$name]:-}" ]]; then
    log "retention: removing $name"
    rm -rf "${BACKUP_DIR:?}/$name"
  fi
done
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -name '*.partial' -mmin +720 -exec rm -rf {} +
if [[ -d "$BACKUP_DIR/encrypted" ]]; then
  find "$BACKUP_DIR/encrypted" -type f -mtime +"$BACKUP_KEEP_DAILY" -delete
fi

write_status ok "Backup $STAMP verified." "$size" true
log "backup $STAMP ok ($size bytes, off-server copy: $OFFSITE)"

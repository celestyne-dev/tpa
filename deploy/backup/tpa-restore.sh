#!/usr/bin/env bash
# Think Positive Always — restore a backup made by tpa-backup.sh.
#
#   tpa-restore.sh --from /var/backups/tpa/2026-10-27T031000Z --verify-only
#   tpa-restore.sh --from tpa-2026-10-27T031000Z.tar.age --identity /root/tpa-backup.key \
#       --database postgresql://tpa@127.0.0.1/tpa_restore \
#       --media-root /var/lib/tpa/media --resources-root /var/lib/tpa/resources/private --yes
#
# Steps: decrypt (age or gpg) if needed, verify checksums and the dump, then restore the
# database (pg_restore --clean, one transaction) and swap the file folders into place.
# Existing folders are kept beside the new ones as <folder>.before-restore-<time>.
# Nothing is changed without --yes. Restoring into a new, empty database and pointing
# DATABASE_URL at it is the safest route; see docs/backups.md.
set -Eeuo pipefail
umask 077

FROM="" DATABASE="" MEDIA="" RESOURCES="" IDENTITY="" YES="no" VERIFY_ONLY="no"
: "${PG_BIN:=}"
pg() { if [[ -n "$PG_BIN" ]]; then "$PG_BIN/$1" "${@:2}"; else "$@"; fi; }
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --database) DATABASE="$2"; shift 2 ;;
    --media-root) MEDIA="$2"; shift 2 ;;
    --resources-root) RESOURCES="$2"; shift 2 ;;
    --identity) IDENTITY="$2"; shift 2 ;;
    --yes) YES="yes"; shift ;;
    --verify-only) VERIFY_ONLY="yes"; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done
[[ -n "$FROM" ]] || die "--from is required"

# shellcheck source=tpa-pg-env.sh
. "$(dirname "$(readlink -f "$0")")/tpa-pg-env.sh"
if [[ -n "$DATABASE" ]]; then
  # Keep the password off the pg_restore command line (visible to every local user).
  pg_url_to_env "$DATABASE" || die "--database must be a PostgreSQL URL"
  DATABASE="$PG_URL"
fi

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/tpa-restore.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

# ---- locate (and decrypt) the backup -----------------------------------------------------
if [[ -d "$FROM" ]]; then
  SRC="$FROM"
elif [[ "$FROM" == *.age ]]; then
  [[ -n "$IDENTITY" ]] || die "--identity (age secret key file) is required for .age files"
  log "decrypting $FROM"
  age -d -i "$IDENTITY" "$FROM" | tar -C "$SCRATCH" -xf -
  SRC="$(find "$SCRATCH" -mindepth 1 -maxdepth 1 -type d | head -n1)"
elif [[ "$FROM" == *.gpg ]]; then
  log "decrypting $FROM"
  gpg --batch --decrypt "$FROM" | tar -C "$SCRATCH" -xf -
  SRC="$(find "$SCRATCH" -mindepth 1 -maxdepth 1 -type d | head -n1)"
else
  die "--from must be a backup folder, a .tar.age or a .tar.gpg file"
fi
[[ -f "$SRC/SHA256SUMS" ]] || die "$SRC is not a TPA backup (no SHA256SUMS)"

# ---- verify --------------------------------------------------------------------------------
log "verifying $SRC"
(cd "$SRC" && sha256sum --quiet -c SHA256SUMS) || die "checksum mismatch: the backup is damaged"
pg pg_restore --list "$SRC/db.dump" > /dev/null || die "the database dump can't be read"
tar -tf "$SRC/media.tar" > /dev/null || die "media.tar is damaged"
tar -tf "$SRC/resources.tar" > /dev/null || die "resources.tar is damaged"
log "backup verified: $(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["name"], "revision", m["alembic_revision"])' "$SRC/meta.json")"
if [[ "$VERIFY_ONLY" == "yes" ]]; then
  log "verify-only: nothing restored"; exit 0
fi
[[ "$YES" == "yes" ]] || die "add --yes to restore (this replaces data in the targets you named)"
[[ -n "$DATABASE" || -n "$MEDIA" || -n "$RESOURCES" ]] || die "name at least one target"

# ---- database ------------------------------------------------------------------------------
if [[ -n "$DATABASE" ]]; then
  log "restoring the database"
  pg pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction \
    --exit-on-error --dbname "$DATABASE" "$SRC/db.dump"
fi

# ---- files: extract beside the target, then swap ---------------------------------------------
swap_in() {  # archive target mode
  local archive="$1" target="$2" mode="$3" stamp staging
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  target="${target%/}"
  staging="$target.restoring-$stamp"
  mkdir -p "$(dirname "$target")"
  mkdir "$staging"
  tar -C "$staging" -xf "$archive"
  chmod "$mode" "$staging"
  if [[ -e "$target" ]]; then
    mv "$target" "$target.before-restore-$stamp"
    log "previous $target kept as $target.before-restore-$stamp"
  fi
  mv "$staging" "$target"
  log "restored $target"
}
[[ -z "$MEDIA" ]] || swap_in "$SRC/media.tar" "$MEDIA" 0755
[[ -z "$RESOURCES" ]] || swap_in "$SRC/resources.tar" "$RESOURCES" 0750

cat <<'NEXT'
Restore finished. Next:
  1. Check ownership: chown -R tpa:www-data on the restored folders (see docs/backups.md).
  2. cd /var/www/tpa/backend && set -a && . ./.env && set +a
     .venv/bin/flask --app wsgi db upgrade        # if the backup is from an older release
     .venv/bin/flask --app wsgi storage check     # no missing files, permissions ok
     .venv/bin/flask --app wsgi rbac sync
  3. sudo systemctl restart tpa-api tpa-publish-worker tpa-email-worker
  4. Remove the *.before-restore-* folders once the site is confirmed working.
NEXT

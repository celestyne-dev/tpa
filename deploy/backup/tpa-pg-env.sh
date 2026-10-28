# Sourced by tpa-backup.sh and tpa-restore.sh (not executable on its own).
#
# pg_url_to_env URL: sets PG_URL to the connection URL without its password and exports
# the password as PGPASSWORD (call it directly, not in $(...), so both reach the caller). Command-line arguments are visible to every local user (ps,
# /proc/<pid>/cmdline) while pg_dump/pg_restore/psql run, so the password must never be
# passed in the URL. Also accepts the application's SQLAlchemy form
# (postgresql+psycopg://), which the PostgreSQL tools don't understand.
pg_url_to_env() {
  local out
  out="$(python3 - "$1" <<'PY'
import sys
from urllib.parse import unquote, urlsplit, urlunsplit

parts = urlsplit(sys.argv[1])
scheme = parts.scheme.split("+", 1)[0]
if scheme not in ("postgres", "postgresql"):
    sys.exit("not a PostgreSQL URL")
host = parts.hostname or ""
if ":" in host:
    host = f"[{host}]"
netloc = host + (f":{parts.port}" if parts.port else "")
if parts.username:
    netloc = f"{parts.username}@{netloc}"
print(unquote(parts.password or ""))
print(urlunsplit((scheme, netloc, parts.path, parts.query, "")))
PY
)" || return 1
  local password url
  password="$(printf '%s\n' "$out" | sed -n 1p)"
  url="$(printf '%s\n' "$out" | sed -n 2p)"
  if [[ -n "$password" ]]; then
    export PGPASSWORD="$password"
  fi
  PG_URL="$url"
}

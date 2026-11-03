#!/usr/bin/env bash
# Think Positive Always — read-only production baseline.
#
# Answers "what does this server actually serve for the domain?" without changing
# anything: no service, file, symlink, database or configuration is touched. Prints
# only paths, statuses, hashes and public markers, never environment values or secrets.
#
#   1. nginx: the server blocks that answer for the domain, their root/proxy targets
#   2. the active frontend release (symlink target) and its prerender manifest
#   3. the built homepage's fingerprint (rebuild vs legacy markers)
#   4. what the server answers locally (bypassing DNS, CDN and caches) and publicly,
#      with any cache headers, so cached pages can be told apart from the origin
#   5. TPA services, timers and listening ports (production 8101, staging 8100)
#   6. HTTPS for every TPA hostname nginx serves: certificate names and expiry, and
#      whether plain HTTP redirects to HTTPS (input for the HSTS decision)
#
# Usage:   sudo deploy/verify/tpa-baseline.sh [domain] [site-dir] [api-port]
# Default: thinkpositivealways.com  /var/www/tpa-production-site  8101
# sudo is only needed so `nginx -T` can read the configuration.
set -uo pipefail

DOMAIN="${1:-thinkpositivealways.com}"
SITE_DIR="${2:-/var/www/tpa-production-site}"
API_PORT="${3:-8101}"
CURRENT="$SITE_DIR/current"
UA="tpa-baseline/1.0"

section() { printf '\n== %s\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

# Rebuild vs legacy markers in an HTML document (stdin).
fingerprint() {
  local html
  html="$(cat)"
  printf '  sha256        %s\n' "$(printf '%s' "$html" | sha256sum | cut -c1-16)"
  printf '  title         %s\n' "$(printf '%s' "$html" | grep -o '<title>[^<]*</title>' | head -1)"
  printf '  theme-color   %s\n' "$(printf '%s' "$html" | grep -o 'name="theme-color" content="[^"]*"' | head -1)"
  printf '  viewport      %s\n' "$(printf '%s' "$html" | grep -o 'name="viewport" content="[^"]*"' | head -1)"
  printf '  tpa-build     %s\n' "$(printf '%s' "$html" | grep -o 'name="tpa-build" content="[^"]*"' | head -1)"
  printf '  rebuild hints %s\n' "$(printf '%s' "$html" | grep -c -e 'data-prerendered' -e '__TPA_STATE__' -e 'id="tpa-state"')"
  printf '  /assets/      %s refs   /uploads/ %s refs   /media/ %s refs\n' \
    "$(printf '%s' "$html" | grep -o '/assets/' | wc -l)" \
    "$(printf '%s' "$html" | grep -o '/uploads/' | wc -l)" \
    "$(printf '%s' "$html" | grep -o '/media/' | wc -l)"
}

section "Host"
printf '  %s  %s\n' "$(hostname)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
have getent && printf '  DNS %s -> %s\n' "$DOMAIN" "$(getent ahosts "$DOMAIN" | awk '{print $1}' | sort -u | tr '\n' ' ')"
printf '  this server: %s\n' "$(hostname -I 2>/dev/null)"

section "nginx server blocks for $DOMAIN"
if have nginx; then
  nginx -t 2>&1 | tail -1 | sed 's/^/  /'
  # Print each server block that names the domain: listen, server_name, root, proxy targets, includes.
  nginx -T 2>/dev/null | awk -v d="$DOMAIN" '
    /^# configuration file / { file=$4 }
    /^[[:space:]]*server[[:space:]]*\{/ { inblk=1; depth=0; buf=""; hit=0; start=file }
    inblk {
      line=$0
      if (line ~ /server_name|listen|^[[:space:]]*root|proxy_pass|upstream|try_files|include|return 30/) buf=buf "    " line "\n"
      if (line ~ "server_name" && index(line, d)) hit=1
      n=gsub(/\{/,"{",line); m=gsub(/\}/,"}",line); depth+=n-m
      if (depth<=0 && n+m>0) { if (hit) printf "  [%s]\n%s\n", start, buf; inblk=0 }
    }'
  section "nginx upstreams"
  nginx -T 2>/dev/null | grep -E '^\s*(upstream|server 127\.0\.0\.1)' | sed 's/^\s*/  /' | sort -u
else
  echo "  nginx not found"
fi
ls -l /etc/nginx/sites-enabled 2>/dev/null | sed 's/^/  /'

section "Active frontend release ($CURRENT)"
if [[ -L "$CURRENT" ]]; then
  printf '  -> %s\n' "$(readlink -f "$CURRENT")"
  if [[ -f "$CURRENT/prerender-manifest.json" ]] && have python3; then
    python3 - "$CURRENT/prerender-manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(f"  generatedAt   {m.get('generatedAt')}")
print(f"  release       {m.get('release', '(not recorded: build predates release ids)')}")
print(f"  siteUrl       {m.get('siteUrl')}   indexing {m.get('indexing')}")
print(f"  pages         {len(m.get('pages', []))}")
PY
  fi
  echo "  built homepage:"
  fingerprint < "$CURRENT/index.html"
else
  echo "  $CURRENT is not a symlink"
fi

section "Origin response (127.0.0.1, bypassing DNS/CDN)"
for path in / /admin /api/v1/health /robots.txt /sitemap.xml /feed.xml /uploads/ /articles/page/1; do
  code="$(curl -sk -o /dev/null -w '%{http_code}' -A "$UA" --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN$path")"
  printf '  %-16s %s\n' "$path" "$code"
done
echo "  origin homepage:"
curl -sk -A "$UA" --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/" | fingerprint
echo "  origin homepage headers:"
curl -skI -A "$UA" --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/" |
  grep -iE '^(server|cache-control|x-robots-tag|age|etag|last-modified|strict-transport-security|content-security-policy)' | sed 's/^/    /'
echo "  API health (port $API_PORT):"
curl -s -m 5 "http://127.0.0.1:$API_PORT/api/v1/health" | sed 's/^/    /'; echo

section "Public response (through DNS and any CDN/proxy cache)"
# DNS: every address the domain resolves to should be this server (or a CDN in front of
# it). A stray A/AAAA record sends some visitors and crawlers to another host.
mine=" $(hostname -I 2>/dev/null) "
if have getent; then
  for addr in $(getent ahosts "$DOMAIN" | awk '{print $1}' | sort -u); do
    case "$mine" in *" $addr "*) where="this server" ;; *) where="NOT this server (CDN/proxy or another host)" ;; esac
    printf '  %-40s %s\n' "$addr" "$where"
  done
fi
for family in 4 6; do
  if curl -s -"$family" -o /dev/null -m 10 "https://$DOMAIN/" 2>/dev/null; then
    echo "  public homepage over IPv$family:"
    curl -s -"$family" -m 15 -A "$UA" "https://$DOMAIN/?baseline=$(date +%s)" | fingerprint
    echo "  headers over IPv$family (cache markers: age, cf-cache-status, x-cache, via):"
    curl -sI -"$family" -m 15 -A "$UA" "https://$DOMAIN/?baseline=$(date +%s)" |
      grep -iE '^(server|cache-control|age|cf-cache-status|cf-ray|x-cache|via|x-served-by|etag|last-modified)' | sed 's/^/    /'
  else
    echo "  IPv$family: no public connection from this server"
  fi
done

section "TPA services, timers and ports"
systemctl list-units --all --no-legend 'tpa*' 2>/dev/null | awk '{printf "  %-45s %s %s\n", $1, $3, $4}'
for unit in tpa-backend.service; do
  printf '  legacy %-30s enabled=%s active=%s\n' "$unit" \
    "$(systemctl is-enabled "$unit" 2>/dev/null)" "$(systemctl is-active "$unit" 2>/dev/null)"
done
systemctl list-timers --all --no-legend 'tpa*' 2>/dev/null | awk '{print "  " $0}'
have ss && ss -ltnp 2>/dev/null | awk 'NR==1 || /:(80|443|5000|8000|8100|8101)[[:space:]]/' | sed 's/^/  /'

section "HTTPS for TPA hostnames served by nginx"
hosts="$(nginx -T 2>/dev/null | grep -E '^\s*server_name' | tr -s ' ;' '\n' |
  grep -E "(^|\.)${DOMAIN//./\\.}$" | sort -u)"
for host in ${hosts:-$DOMAIN}; do
  cert="$(echo | timeout 10 openssl s_client -servername "$host" -connect 127.0.0.1:443 2>/dev/null |
    openssl x509 -noout -enddate -ext subjectAltName 2>/dev/null | tr '\n' ' ')"
  redirect="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --resolve "$host:80:127.0.0.1" "http://$host/")"
  hsts="$(curl -skI --resolve "$host:443:127.0.0.1" "https://$host/" | grep -i '^strict-transport-security' | tr -d '\r')"
  printf '  %s\n    cert: %s\n    http: %s\n    hsts: %s\n' "$host" "${cert:-NO CERTIFICATE}" "$redirect" "${hsts:-none}"
done

section "Done (read-only: nothing was changed)"

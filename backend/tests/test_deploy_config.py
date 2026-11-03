"""Batch 12.3: deployment configuration checks (nginx, systemd, environment templates,
trusted proxy, readiness and the pre-deployment check). Nothing here touches a server.

Live checks run only where the tool is installed: `nginx -t` and a real Nginx in front of
a stub upstream (nginx + openssl), and `systemd-analyze verify`.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app import create_app
from app.config import BaseConfig
from app.extensions import db, limiter

ROOT = Path(__file__).resolve().parents[2]
NGINX = ROOT / "deploy" / "nginx" / "tpa.conf.example"
HEADERS_SNIPPET = ROOT / "deploy" / "nginx" / "tpa-security-headers.conf.example"
HTTP_SNIPPET = ROOT / "deploy" / "nginx" / "tpa-http.conf.example"
SYSTEMD = ROOT / "deploy" / "systemd"
ENV_EXAMPLE = ROOT / "backend" / ".env.example"
STAGING_ENV = ROOT / "deploy" / "env" / "staging.env.example"
SNIPPET_INCLUDE = "include /etc/nginx/snippets/tpa-security-headers.conf;"
SECURITY_HEADERS = ("X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options")


# ---- a small Nginx config reader ----------------------------------------------------------


def _blocks(text: str):
    """Yield (header, body_directives, children) for every block, depth-first."""
    lines = [line.split("#", 1)[0].rstrip() for line in text.splitlines()]
    stack = [("root", [], [])]
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        # one-line blocks: location = /x { internal; }
        one = re.fullmatch(r"(.+?)\{(.*)\}", line)
        if one:
            stack[-1][2].append(
                (
                    one.group(1).strip(),
                    [d.strip() for d in one.group(2).split(";") if d.strip()],
                    [],
                )
            )
            continue
        if line.endswith("{"):
            stack.append((line[:-1].strip(), [], []))
        elif line == "}":
            block = stack.pop()
            stack[-1][2].append(block)
        else:
            stack[-1][1].append(line.rstrip(";"))
    return stack[0]


def _walk(block):
    yield block
    for child in block[2]:
        yield from _walk(child)


def _main_server():
    root = _blocks(NGINX.read_text())
    servers = [b for b in root[2] if b[0] == "server"]
    [main] = [s for s in servers if any(d.startswith("root ") for d in s[1])]
    return servers, main


def _locations(server):
    return [b for b in _walk(server) if b[0].startswith("location")]


def _location(server, pattern):
    [loc] = [b for b in _locations(server) if b[0] == f"location {pattern}"]
    return loc


# ---- nginx: static checks -----------------------------------------------------------------


def test_security_headers_reach_every_location_that_sets_headers():
    _servers, main = _main_server()
    assert SNIPPET_INCLUDE.rstrip(";") in main[1]
    snippet = HEADERS_SNIPPET.read_text()
    for name in SECURITY_HEADERS:
        assert f"add_header {name}" in snippet
    for loc in _locations(main):
        if any(d.startswith("add_header") for d in loc[1]):
            # Nginx doesn't inherit server-level add_header into such a location.
            assert SNIPPET_INCLUDE.rstrip(";") in loc[1], loc[0]


def test_proxy_headers_are_set_once_for_every_proxied_location():
    _servers, main = _main_server()
    server_level = set(main[1])
    for directive in (
        "proxy_set_header Host $host",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for",
        "proxy_set_header X-Forwarded-Proto $scheme",
        "proxy_set_header X-Forwarded-Host $host",
    ):
        assert directive in server_level, directive
    proxied = [loc for loc in _locations(main) if any(d.startswith("proxy_pass") for d in loc[1])]
    assert len(proxied) >= 5
    for loc in proxied:
        # Any proxy_set_header here would drop every inherited one (ProxyFix trusts them).
        assert not any(d.startswith("proxy_set_header") for d in loc[1]), loc[0]
        assert any("http://tpa_api" in d for d in loc[1])


def test_unknown_hosts_are_refused_and_private_paths_are_never_served():
    servers, main = _main_server()
    defaults = [s for s in servers if any("default_server" in d for d in s[1])]
    assert {
        tuple(sorted(d for d in s[1] if d.startswith(("return", "ssl_reject")))) for s in defaults
    } == {
        ("return 444",),
        ("ssl_reject_handshake on",),
    }
    downloads = _location(main, "/_protected_downloads/")
    assert "internal" in downloads[1]
    staging = _env(STAGING_ENV)
    assert f"alias {staging['PRODUCT_FILES_ROOT']}/" in downloads[1]
    assert staging["PRODUCT_FILES_ACCEL_REDIRECT_PREFIX"] == "/_protected_downloads"
    media = _location(main, "/media/")
    assert f"alias {staging['MEDIA_ROOT']}/public/" in media[1]  # never media/private
    blocked = _location(main, "~ ^/(resources/private|temporary|var)/")
    assert blocked[1] == ["return 404"]
    root = next(d for d in main[1] if d.startswith("root "))
    assert root == f"root {staging['PUBLISH_CURRENT_LINK']}"


def test_unknown_routes_get_a_genuine_404_never_a_200_page():
    """Only the admin SPA may fall back to an HTML shell (noindex). Everything else ends in
    a real 404 status, served with the prerendered 404 page."""
    _servers, main = _main_server()
    fallbacks = {}
    for loc in _locations(main):
        for d in loc[1]:
            if d.startswith("try_files "):
                fallbacks[loc[0]] = d.split()[-1]
    html_fallbacks = {loc for loc, last in fallbacks.items() if last.endswith(".html")}
    assert html_fallbacks == {"location /admin"}, html_fallbacks
    assert fallbacks["location /"] == "@tpa_fallback"
    customer = _location(main, "~ ^/(cart|checkout|account|purchases)(/|$)")
    assert "try_files $uri $uri/index.html =404" in customer[1]
    assert "error_page 404 /404.html" in customer[1]
    fallback = _location(main, "@tpa_fallback")
    assert "error_page 404 /404.html" in fallback[1] and "proxy_intercept_errors on" in fallback[1]
    assert "internal" in _location(main, "= /404.html")[1]
    # Legacy 410 rules are an opt-in include of exact rules generated by the cleanup tool.
    assert "include /etc/nginx/snippets/tpa-legacy-gone.conf" not in main[1]  # off until approved
    assert "# include /etc/nginx/snippets/tpa-legacy-gone.conf;" in NGINX.read_text()


def test_upload_limits_follow_the_application_limits():
    _servers, main = _main_server()

    def limit(pattern):
        loc = _location(main, pattern)
        value = next(d for d in loc[1] if d.startswith("client_max_body_size"))
        return int(value.split()[1].rstrip("m"))

    assert limit("/api/v1/admin/media") == BaseConfig.MEDIA_MAX_UPLOAD_MB + 1
    assert limit("~ ^/api/v1/admin/products/[0-9]+/files") == BaseConfig.PRODUCT_FILE_MAX_MB + 1
    assert (
        limit("~ ^/api/v1/account/learning/[^/]+/assignments/[^/]+/files$")
        == BaseConfig.SUBMISSION_FILE_MAX_MB + 1
    )


def test_gunicorn_upstream_and_prerender_url_agree():
    api = (SYSTEMD / "tpa-api.service.example").read_text()
    assert "--bind 127.0.0.1:8000" in api  # loopback only; Nginx is the entry point
    assert "server 127.0.0.1:8000;" in NGINX.read_text()
    assert _env(STAGING_ENV)["PUBLISH_API_URL"] == "http://127.0.0.1:8000/api/v1"


# ---- nginx: live checks (only where nginx and openssl are installed) ------------------------

needs_nginx = pytest.mark.skipif(
    not (shutil.which("nginx") and shutil.which("openssl")), reason="nginx/openssl not installed"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Upstream(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def log_message(self, *_args):
        pass

    def do_GET(self):  # noqa: N802
        _Upstream.seen.append(
            {"path": self.path, **{k.lower(): v for k, v in self.headers.items()}}
        )
        if self.path.startswith("/_redirect/"):
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/api/v1/download":
            self.send_response(200)
            self.send_header("X-Accel-Redirect", "/_protected_downloads/guide.pdf")
            self.end_headers()
            return
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _nginx_conf(tmp: Path, http_port: int, https_port: int, upstream_port: int) -> Path:
    site, media, private, snippets = (tmp / n for n in ("site", "media", "private", "snippets"))
    for d in (site / "admin", media / "public", private, snippets, tmp / "logs"):
        d.mkdir(parents=True)
    (site / "index.html").write_text("<h1>home</h1>")
    (site / "404.html").write_text("not found")
    (site / "admin" / "index.html").write_text("admin shell")
    (site / "account").mkdir()
    (site / "account" / "index.html").write_text("account shell")
    for page in ("articles", "articles/page/2", "search", "about"):
        (site / page).mkdir(parents=True)
        (site / page / "index.html").write_text(f"<h1>{page}</h1>")
    (site / "feed.xml").write_text('<?xml version="1.0"?><rss version="2.0"></rss>')
    (site / ".env").write_text("SECRET=never")
    (media / "public" / "a.webp").write_bytes(b"img")
    (media / "private").mkdir()
    (private / "guide.pdf").write_bytes(b"%PDF premium")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-subj", "/CN=example.com", "-keyout", str(tmp / "key.pem"), "-out", str(tmp / "cert.pem")],
        check=True, capture_output=True,
    )  # fmt: skip
    shutil.copy(HEADERS_SNIPPET, snippets / "tpa-security-headers.conf")
    text = NGINX.read_text()
    replacements = {
        "/etc/nginx/snippets/": f"{snippets}/",
        "/etc/letsencrypt/live/example.com/fullchain.pem": str(tmp / "cert.pem"),
        "/etc/letsencrypt/live/example.com/privkey.pem": str(tmp / "key.pem"),
        "/var/www/tpa-site/current": str(site),
        "/var/lib/tpa/media/public/": f"{media}/public/",
        "/var/lib/tpa/resources/private/": f"{private}/",
        "/var/www/letsencrypt": str(tmp / "acme"),
        "127.0.0.1:8000": f"127.0.0.1:{upstream_port}",
    }
    for old, new in replacements.items():
        assert old in text, old  # the test must follow the real example
        text = text.replace(old, new)
    # Enable the legacy 410 include with a snippet generated by the cleanup tool.
    from legacy_migration.cleanup import gone_snippet

    (snippets / "tpa-legacy-gone.conf").write_text(gone_snippet(["/forums/topic/12"]))
    include = f"# include {snippets}/tpa-legacy-gone.conf;"
    assert include in text
    text = text.replace(include, include.lstrip("# "))
    text = re.sub(r"^\s*listen \[::\].*$", "", text, flags=re.M)  # no IPv6 in CI sandboxes
    text = text.replace("listen 443", f"listen {https_port}").replace(
        "listen 80", f"listen {http_port}"
    )
    (tmp / "tpa.conf").write_text(text)
    temp = " ".join(
        f"{k}_temp_path {tmp}/logs;" for k in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi")
    )
    shutil.copy(HTTP_SNIPPET, tmp / "tpa-http.conf")  # /etc/nginx/conf.d/ on the server
    conf = tmp / "nginx.conf"
    conf.write_text(
        ("user root;\n" if os.geteuid() == 0 else "")
        + f"pid {tmp}/nginx.pid;\nerror_log {tmp}/logs/error.log;\nevents {{}}\n"
        f"http {{ include /etc/nginx/mime.types; access_log off; {temp} "
        f"include {tmp}/tpa-http.conf; include {tmp}/tpa.conf; }}\n"
    )
    return conf


@pytest.fixture()
def live_nginx(tmp_path):
    upstream_port, http_port, https_port = _free_port(), _free_port(), _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", upstream_port), _Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _Upstream.seen.clear()
    conf = _nginx_conf(tmp_path, http_port, https_port, upstream_port)
    check = subprocess.run(
        ["nginx", "-t", "-p", str(tmp_path), "-c", str(conf)], capture_output=True, text=True
    )
    assert check.returncode == 0, check.stderr
    subprocess.run(["nginx", "-p", str(tmp_path), "-c", str(conf)], check=True)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", https_port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        yield {"http": http_port, "https": https_port}
    finally:
        subprocess.run(["nginx", "-p", str(tmp_path), "-c", str(conf), "-s", "stop"], check=False)
        server.shutdown()


def _https(port, path, *, sni="example.com", headers=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection(("127.0.0.1", port), timeout=5)
    conn = http.client.HTTPConnection("example.com")
    conn.sock = ctx.wrap_socket(raw, server_hostname=sni)
    conn.request("GET", path, headers={"Host": "example.com", **(headers or {})})
    res = conn.getresponse()
    return res.status, {k.lower(): v for k, v in res.getheaders()}, res.read()


@needs_nginx
def test_live_nginx_headers_proxy_trust_and_private_files(live_nginx):
    port = live_nginx["https"]
    # Security headers on prerendered pages, the admin shell, media and API responses.
    for path in ("/", "/admin/users", "/media/a.webp", "/api/v1/site"):
        status, headers, _ = _https(port, path)
        assert status == 200, path
        for name in SECURITY_HEADERS:
            assert name.lower() in headers, (path, name)
    assert _https(port, "/admin/users")[1]["cache-control"] == "no-store"

    # The API sees the real client: spoofed forwarding headers can't win.
    _https(
        port,
        "/api/v1/site",
        headers={"X-Forwarded-For": "6.6.6.6", "X-Forwarded-Host": "evil.example"},
    )
    seen = _Upstream.seen[-1]
    assert seen["x-forwarded-for"].split(",")[-1].strip() == "127.0.0.1"  # appended by Nginx
    assert seen["x-forwarded-host"] == "example.com" and seen["x-forwarded-proto"] == "https"

    # Unknown paths go to Flask's redirect lookup with the same trusted headers, then 404.
    status, _h, body = _https(port, "/no-such-page", headers={"X-Forwarded-Host": "evil.example"})
    assert status == 404 and body == b"not found"
    assert _Upstream.seen[-1]["path"] == "/_redirect/no-such-page"
    assert _Upstream.seen[-1]["x-forwarded-host"] == "example.com"

    # Customer shells exist; unknown customer paths are a genuine 404 (not the page with 200).
    assert _https(port, "/account")[0] == 200
    status, _h, body = _https(port, "/account/old-forum-profile")
    assert (status, body) == (404, b"not found")
    # Approved legacy 410 rules: exact path, trailing slash and any query string only.
    for path in ("/forums/topic/12", "/forums/topic/12/", "/forums/topic/12?page=2"):
        assert _https(port, path)[0] == 410, path
    for path in ("/forums/topic/120", "/forums/topic"):
        assert _https(port, path)[0] == 404, path  # no prefix rules

    # Premium files: only through Flask's X-Accel-Redirect, never directly.
    status, headers, body = _https(port, "/api/v1/download")
    assert (status, body) == (200, b"%PDF premium") and "no-store" in headers["cache-control"]
    assert _https(port, "/_protected_downloads/guide.pdf")[0] == 404
    for path in (
        "/.env",
        "/media/../private/guide.pdf",
        "/var/lib/tpa/x",
        "/resources/private/guide.pdf",
    ):
        assert _https(port, path)[0] in (400, 404), path

    # Other hostnames: TLS refused; plain HTTP redirects only for the real domain.
    with pytest.raises(ssl.SSLError):
        _https(port, "/", sni="evil.example")
    conn = http.client.HTTPConnection("127.0.0.1", live_nginx["http"], timeout=5)
    conn.request("GET", "/x", headers={"Host": "example.com"})
    res = conn.getresponse()
    assert res.status == 301 and res.getheader("Location") == "https://example.com/x"
    conn = http.client.HTTPConnection("127.0.0.1", live_nginx["http"], timeout=5)
    conn.request("GET", "/", headers={"Host": "evil.example"})
    with pytest.raises((http.client.RemoteDisconnected, ConnectionResetError)):
        conn.getresponse()  # 444: connection closed without a response


@needs_nginx
def test_live_nginx_one_url_per_page_search_feed_and_csp(live_nginx):
    port = live_nginx["https"]

    def location(path):
        """Status and redirect target (path and query; the test port is in the host)."""
        from urllib.parse import urlsplit

        status, headers, _ = _https(port, path)
        target = urlsplit(headers.get("location") or "")
        return status, target.path + (f"?{target.query}" if target.query else "")

    # Trailing slash and index.html: one canonical URL (no slash) for prerendered pages.
    assert location("/articles/") == (301, "/articles")
    assert location("/articles/index.html") == (301, "/articles")
    assert location("/articles/page/2/?ref=x") == (301, "/articles/page/2?ref=x")
    assert location("/index.html") == (301, "/")
    assert _https(port, "/articles")[0] == 200 and _https(port, "/")[0] == 200
    # Page 1 of a listing is the listing itself.
    assert location("/articles/page/1") == (301, "/articles")
    assert location("/topics/calm/page/1/") == (301, "/topics/calm")
    # Paths that aren't pages still reach Flask (CMS redirects, then a genuine 404) in one hop.
    _Upstream.seen.clear()
    assert _https(port, "/old-category/")[0] == 404
    assert _Upstream.seen[-1]["path"] == "/_redirect/old-category/"
    # Approved legacy 410 rules still win, with or without the slash.
    assert _https(port, "/forums/topic/12/")[0] == 410
    # The API and admin are never rewritten.
    assert _https(port, "/api/v1/site/")[0] == 200
    assert _https(port, "/admin/users/")[0] == 200

    status, headers, _ = _https(port, "/search?q=calm")
    assert status == 200 and headers["x-robots-tag"] == "noindex, follow"
    status, headers, body = _https(port, "/feed.xml")
    assert status == 200 and headers["content-type"].startswith("application/rss+xml")
    for path in ("/", "/search", "/feed.xml", "/admin/users"):
        csp = _https(port, path)[1]["content-security-policy-report-only"]
        assert "script-src 'self';" in csp and "report-uri /api/v1/csp-report" in csp, path
        assert "'unsafe-eval'" not in csp and "script-src 'self' 'unsafe-inline'" not in csp


def test_csp_allows_only_this_site_and_the_video_embeds():
    snippet = HEADERS_SNIPPET.read_text()
    [policy] = re.findall(r'Content-Security-Policy-Report-Only "([^"]+)"', snippet)
    directives = dict(d.strip().split(" ", 1) for d in policy.split(";") if d.strip())
    assert directives["script-src"] == "'self'"
    assert directives["object-src"] == "'none'" and directives["base-uri"] == "'self'"
    assert directives["frame-src"] == (
        "'self' https://www.youtube-nocookie.com https://player.vimeo.com"
    )
    # HSTS stays off until the HTTPS audit (tpa-baseline.sh) covers every hostname.
    assert not re.search(r"^\s*add_header Strict-Transport-Security", snippet, re.M)


# ---- systemd ------------------------------------------------------------------------------


def _units():
    return {p.name.removesuffix(".example"): p.read_text() for p in SYSTEMD.glob("*.example")}


def test_systemd_units_are_consistent_and_use_real_commands():
    units = _units()
    app = create_app("testing")
    commands = {
        (g, c) for g, group in app.cli.commands.items() for c in getattr(group, "commands", {})
    }
    for name, text in units.items():
        if name.endswith(".timer"):
            assert name.replace(".timer", ".service") in units, f"{name} has no service"
            continue
        if name == "tpa-backup.service":
            continue  # root, reads /etc/tpa/backup.env
        assert "EnvironmentFile=/var/www/tpa/backend/.env" in text, name
        assert "Environment=FLASK_CONFIG=production" in text, name
        assert "NoNewPrivileges=true" in text, name
        for group, command in re.findall(r"flask --app wsgi (\S+) (\S+)", text):
            assert (group, command) in commands, f"{name}: flask {group} {command}"
    api = units["tpa-api.service"]
    assert "ExecReload=/bin/kill -s HUP $MAINPID" in api
    assert "redis-server.service" in api


def test_scheduled_publishing_is_not_enabled_twice():
    """tpa-publish-worker already runs the scheduler: the optional timer is for
    --no-scheduler setups only and must not be in the default enable list."""
    guide = (ROOT / "docs" / "hostinger-vps.md").read_text()
    enable = re.findall(r"systemctl enable --now ((?:[^\n]*\\\n)*[^\n]*)", guide)
    enabled = " ".join(enable)
    assert "tpa-publish-worker" in enabled and "tpa-publish-due.timer" not in enabled
    for timer in (
        "tpa-analytics-maintain.timer",
        "tpa-membership-reconcile.timer",
        "tpa-storage-maintenance.timer",
        "tpa-backup.timer",
        "tpa-media-prune.timer",
    ):
        assert timer in enabled, timer


@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="systemd-analyze not installed")
def test_systemd_analyze_verify(tmp_path):
    for p in SYSTEMD.glob("*.example"):
        shutil.copy(p, tmp_path / p.name.removesuffix(".example"))
    files = sorted(str(p) for p in tmp_path.iterdir())
    res = subprocess.run(
        ["systemd-analyze", "verify", "--man=no", *files], capture_output=True, text=True
    )
    problems = [
        line
        for line in (res.stdout + res.stderr).splitlines()
        if line.strip() and "is not executable: No such file or directory" not in line
    ]
    assert problems == []  # only the server's install paths are missing here


# ---- environment templates ----------------------------------------------------------------


def _env(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def test_env_example_documents_every_setting_the_config_reads():
    source = (ROOT / "backend" / "app" / "config" / "__init__.py").read_text()
    names = set(re.findall(r'(?:environ\.get|_bool|_list|_int)\("([A-Z0-9_]+)"', source))
    documented = set(re.findall(r"^#?\s?([A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M))
    assert names - documented == set()


def test_staging_template_is_safe_and_has_no_secrets():
    env = _env(STAGING_ENV)
    for key in ("SECRET_KEY", "JWT_SECRET_KEY", "MAIL_SMTP_PASSWORD"):
        assert env[key] == "CHANGE-ME", key
    assert "CHANGE-ME@" in env["DATABASE_URL"]
    assert env["PAYSTACK_SECRET_KEY"].startswith("sk_test_")
    assert env["PAYMENTS_LIVE_ALLOWED"] == "false" and env["MEMBERSHIP_BILLING_MODE"] == "disabled"
    assert env["TRUST_PROXY"] == "1" and env["RATELIMIT_STORAGE_URI"].startswith("redis://")
    documented = set(re.findall(r"^#?\s?([A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M))
    assert set(env) - documented == set()  # no settings the app doesn't know


def _run_backend(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    # Only the given settings: FLASK_SKIP_DOTENV keeps a developer's backend/.env out.
    base = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", "/tmp"),
        "FLASK_SKIP_DOTENV": "1",
    }
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT / "backend", env=base | env,
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip


def _deploy_check(env: dict[str, str]) -> subprocess.CompletedProcess:
    args = ["-m", "flask", "--app", "wsgi", "deploy", "check", "--no-database", "--json"]
    return _run_backend(args, env)


def _deploy_report(env: dict[str, str]) -> tuple[subprocess.CompletedProcess, dict]:
    """Run the check and parse its JSON, failing with the exit code and output if it
    printed none (instead of an unexplained JSONDecodeError)."""
    res = _deploy_check(env)
    try:
        report = json.loads(res.stdout)
    except json.JSONDecodeError:
        report = None
    if not isinstance(report, dict):
        pytest.fail(
            f"`flask deploy check --json` printed no JSON report (exit {res.returncode}).\n"
            f"--- stdout ---\n{res.stdout[-2000:] or '(empty)'}\n"
            f"--- stderr ---\n{res.stderr[-4000:] or '(empty)'}",
            pytrace=False,
        )
    return res, report


def _errors(report: dict) -> set[str]:
    return {r["check"] for r in report["results"] if r["level"] == "error"}


SECRET, JWT_SECRET, SMTP_PASSWORD = (f"s3cr3t-{n}-" + "x7Kq9Lm2" * 6 for n in "abc")
SECRET_VALUES = (SECRET, JWT_SECRET, SMTP_PASSWORD, "db-password-123", "a" * 40)


def _filled_in_staging_env(tmp_path: Path) -> dict[str, str]:
    return _env(STAGING_ENV) | {
        "SECRET_KEY": SECRET,
        "JWT_SECRET_KEY": JWT_SECRET,
        "MAIL_SMTP_PASSWORD": SMTP_PASSWORD,
        "MAIL_SMTP_HOST": "smtp.example.net",
        "DATABASE_URL": "postgresql+psycopg://tpa:db-password-123@127.0.0.1:1/tpa",
        "PAYSTACK_SECRET_KEY": "sk_test_" + "a" * 40,
        "PAYSTACK_PUBLIC_KEY": "pk_test_" + "b" * 40,
        # Writable stand-ins for the server paths (same layout).
        "MEDIA_ROOT": str(tmp_path / "media"),
        "PRODUCT_FILES_ROOT": str(tmp_path / "resources" / "private"),
        "UPLOAD_TEMP_ROOT": str(tmp_path / "temporary" / "uploads"),
        "PUBLISH_RELEASES_DIR": str(tmp_path / "site" / "releases"),
        "PUBLISH_CURRENT_LINK": str(tmp_path / "site" / "current"),
        "RATELIMIT_STORAGE_URI": "redis://127.0.0.1:1/0",  # nothing listens: unreachable
    }


def _assert_no_secrets(res: subprocess.CompletedProcess, *extra: str) -> None:
    for value in (*SECRET_VALUES, *extra):
        assert value not in res.stdout + res.stderr


def test_filled_in_staging_template_passes_the_deploy_check_without_leaking_secrets(tmp_path):
    res, report = _deploy_report(_filled_in_staging_env(tmp_path))
    assert _errors(report) == {"RATELIMIT_STORAGE_URI"}, report  # only Redis is missing here
    assert res.returncode == 2
    _assert_no_secrets(res)


def test_deploy_check_reports_settings_that_production_refuses_to_start_with(tmp_path):
    """Problems ProductionConfig.validate() refuses used to abort the CLI before the check
    ran (empty stdout, exit 1 = "warnings"). They are now errors in the JSON report."""
    env = _filled_in_staging_env(tmp_path) | {
        "NEWSLETTER_MAIL_BACKEND": "console",
        "PAYSTACK_API_BASE": "https://paystack.example.net",
    }
    res, report = _deploy_report(env)
    assert {"NEWSLETTER_MAIL_BACKEND", "PAYSTACK_API_BASE"} <= _errors(report), report
    assert report["status"] == "error" and res.returncode == 2
    _assert_no_secrets(res)


def test_deploy_check_reports_an_application_that_cannot_initialise(tmp_path):
    """An extension that fails during create_app (here: an unknown rate-limit storage, as
    with a Redis URI and no redis client) is reported as JSON, with credentials removed."""
    env = _filled_in_staging_env(tmp_path) | {
        "RATELIMIT_STORAGE_URI": "nosuchstore://ratelimit:store-pass-987@127.0.0.1:1/0"
    }
    res, report = _deploy_report(env)
    startup = [r for r in report["results"] if r["check"] == "startup"]
    assert startup and startup[0]["level"] == "error", report
    assert "ConfigurationError" in startup[0]["message"]
    assert "live_checks" in _errors(report)
    assert report["status"] == "error" and res.returncode == 2
    _assert_no_secrets(res, "store-pass-987")


def test_production_start_up_still_refuses_invalid_settings(tmp_path):
    """Only `deploy check` reports instead of refusing: importing wsgi (what Gunicorn
    does) still fails on the same settings."""
    env = _filled_in_staging_env(tmp_path) | {"NEWSLETTER_MAIL_BACKEND": "console"}
    res = _run_backend(["-c", "import wsgi"], env)
    assert res.returncode != 0
    assert "Missing required production settings: NEWSLETTER_MAIL_BACKEND" in res.stderr


def test_only_the_deploy_check_command_uses_the_preflight_app():
    from app.preflight import is_deploy_check

    assert is_deploy_check(["flask", "--app", "wsgi", "deploy", "check", "--json"])
    assert not is_deploy_check(["gunicorn", "--workers", "3", "wsgi:app"])
    assert not is_deploy_check(["flask", "--app", "wsgi", "db", "upgrade"])
    assert not is_deploy_check(["flask", "--app", "wsgi", "deploy"])


def test_deploy_check_flags_unsafe_production_settings(tmp_path):
    env = _env(STAGING_ENV) | {
        "SECRET_KEY": "k" * 8 + "Zq81LmPw" * 5,
        "JWT_SECRET_KEY": "k" * 8 + "Zq81LmPw" * 5,  # same as SECRET_KEY
        "DATABASE_URL": "postgresql+psycopg://tpa:pw@127.0.0.1:1/tpa",
        "TRUST_PROXY": "0",
        "RATELIMIT_STORAGE_URI": "memory://",
        "SITE_URL": "http://staging.example.com",
        "PAYMENTS_LIVE_ALLOWED": "true",
        "PAYSTACK_SECRET_KEY": "sk_test_x",
        "PAYSTACK_PUBLIC_KEY": "pk_test_x",
        "MEDIA_ROOT": str(tmp_path / "media"),
        "PRODUCT_FILES_ROOT": str(tmp_path / "private"),
        "UPLOAD_TEMP_ROOT": str(tmp_path / "uploads"),
        "PUBLISH_RELEASES_DIR": str(tmp_path / "releases"),
        "PUBLISH_CURRENT_LINK": str(tmp_path / "current"),
    }
    _, report = _deploy_report(env)
    errors = _errors(report)
    assert {
        "secrets_distinct",
        "TRUST_PROXY",
        "RATELIMIT_STORAGE_URI",
        "SITE_URL",
        "PAYMENTS_LIVE_ALLOWED",
    } <= errors


# ---- application: readiness and trusted proxy ----------------------------------------------


def test_readiness_reports_dependencies_without_details(app, client, monkeypatch):
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    assert res.get_json()["data"] == {
        "status": "ready",
        "checks": {"database": "ok", "rate_limit_storage": "ok"},
    }

    def broken(*_a, **_k):
        raise RuntimeError("connection to server at 10.0.0.5 failed: password authentication")

    monkeypatch.setattr(db.session, "execute", broken)
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 503
    assert res.get_json()["data"]["checks"]["database"] == "unavailable"
    assert b"10.0.0.5" not in res.data and b"password" not in res.data
    assert client.get("/api/v1/health").status_code == 200  # liveness doesn't depend on it


def test_rate_limits_key_on_the_address_nginx_appends(tmp_path):
    """TRUST_PROXY=1 trusts exactly one proxy: the right-most X-Forwarded-For entry (added
    by Nginx). A client-supplied entry in front of it can't dodge or shift the limit."""
    app = create_app(
        "testing",
        {"TRUST_PROXY": True, "RATELIMIT_LOGIN": "3 per minute", "MEDIA_ROOT": str(tmp_path)},
    )
    with app.app_context():
        db.create_all()
    limiter.reset()
    client = app.test_client()

    def login(chain):
        return client.post(
            "/api/v1/admin/auth/login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
            headers={"X-Forwarded-For": chain, "Origin": "http://localhost:5173"},
        ).status_code

    assert [login("203.0.113.5") for _ in range(3)] == [401, 401, 401]
    assert login("198.51.100.1, 203.0.113.5") == 429  # spoofed first entry: same client
    assert login("203.0.113.6") == 401  # a different real client has its own limit
    with app.app_context():
        db.drop_all()


# ---- backup scripts: the database password never reaches a command line ----------------------

PG_ENV = ROOT / "deploy" / "backup" / "tpa-pg-env.sh"


def _pg_env(url: str) -> subprocess.CompletedProcess:
    script = f'set -Eeuo pipefail; . "{PG_ENV}"; pg_url_to_env "$1"; printf "%s\\n%s\\n" "$PG_URL" "${{PGPASSWORD:-}}"'
    return subprocess.run(["bash", "-c", script, "_", url], capture_output=True, text=True)


def test_backup_scripts_move_the_database_password_out_of_the_url():
    res = _pg_env("postgresql+psycopg://tpa:p%40ss%3Aw0rd@127.0.0.1:5432/tpa?sslmode=require")
    url, password = res.stdout.splitlines()
    assert url == "postgresql://tpa@127.0.0.1:5432/tpa?sslmode=require"  # pg_dump-compatible
    assert password == "p@ss:w0rd"
    url, password = _pg_env("postgresql://tpa@localhost/tpa").stdout.splitlines()
    assert url == "postgresql://tpa@localhost/tpa" and password == ""
    assert _pg_env("mysql://u:p@h/db").returncode != 0
    for script in ("tpa-backup.sh", "tpa-restore.sh"):
        text = (ROOT / "deploy" / "backup" / script).read_text()
        assert "tpa-pg-env.sh" in text and "pg_url_to_env" in text, script


# ---- production / staging isolation --------------------------------------------------------

PRODUCTION_ENV = ROOT / "deploy" / "env" / "production.env.example"


def _filled_in_production_env(tmp_path: Path) -> dict[str, str]:
    staging = _filled_in_staging_env(tmp_path)
    secrets = {k: staging[k] for k in ("SECRET_KEY", "JWT_SECRET_KEY", "MAIL_SMTP_PASSWORD")}
    return (
        _env(PRODUCTION_ENV)
        | secrets
        | {
            "MAIL_SMTP_HOST": "smtp.example.net",
            "DATABASE_URL": "postgresql+psycopg://tpa_production:db-password-123@127.0.0.1:1/tpa_production",
            "PAYSTACK_SECRET_KEY": "sk_test_" + "a" * 40,
            "PAYSTACK_PUBLIC_KEY": "pk_test_" + "b" * 40,
            "MEDIA_ROOT": str(tmp_path / "tpa-production" / "media"),
            "PRODUCT_FILES_ROOT": str(tmp_path / "tpa-production" / "private"),
            "UPLOAD_TEMP_ROOT": str(tmp_path / "tpa-production" / "uploads"),
            "PUBLISH_RELEASES_DIR": str(tmp_path / "tpa-production-site" / "releases"),
            "PUBLISH_CURRENT_LINK": str(tmp_path / "tpa-production-site" / "current"),
            "RATELIMIT_STORAGE_URI": "redis://127.0.0.1:1/0",
        }
    )


def _check(report: dict, name: str) -> dict:
    return next(r for r in report["results"] if r["check"] == name)


def test_production_template_is_safe_and_names_its_tier():
    env = _env(PRODUCTION_ENV)
    assert env["TPA_ENVIRONMENT"] == "production" and env["FLASK_CONFIG"] == "production"
    for key in ("SECRET_KEY", "JWT_SECRET_KEY", "MAIL_SMTP_PASSWORD"):
        assert env[key] == "CHANGE-ME", key
    assert env["PAYMENTS_LIVE_ALLOWED"] == "false" and env["NEWSLETTER_LIVE_ALLOWED"] == "false"
    assert env["PUBLISH_API_URL"] == "http://127.0.0.1:8101/api/v1"
    assert env["DATABASE_URL"].endswith("/tpa_production")
    from app.services.deploy_check import _names_tier

    assert not [k for k, v in env.items() if _names_tier(v, "staging")]  # no staging values
    documented = set(re.findall(r"^#?\s?([A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M))
    assert set(env) - documented == set()
    assert _env(STAGING_ENV)["TPA_ENVIRONMENT"] == "staging"


def test_filled_in_production_template_passes_isolation(tmp_path):
    res, report = _deploy_report(_filled_in_production_env(tmp_path))
    assert _check(report, "TPA_ENVIRONMENT")["level"] == "ok"
    assert _check(report, "isolation")["level"] == "ok", report
    assert _errors(report) == {"RATELIMIT_STORAGE_URI"}, report  # only Redis is missing here
    _assert_no_secrets(res)


@pytest.mark.parametrize(
    ("tier", "change", "named"),
    [
        (
            "production",
            {"DATABASE_URL": "postgresql+psycopg://u:db-password-123@127.0.0.1:1/tpa_staging"},
            "DATABASE_URL (database tpa_staging)",
        ),
        ("production", {"RATELIMIT_KEY_PREFIX": "tpa-staging"}, "RATELIMIT_KEY_PREFIX"),
        (
            "production",
            {"PUBLISH_API_URL": "http://127.0.0.1:8100/api/v1"},
            "port 8100 is the staging API",
        ),
        (
            "production",
            {"PUBLISH_CURRENT_LINK": "/var/www/tpa-staging-site/current"},
            "PUBLISH_CURRENT_LINK",
        ),
        (
            "staging",
            {"DATABASE_URL": "postgresql+psycopg://u:db-password-123@127.0.0.1:1/tpa_production"},
            "database tpa_production",
        ),
        (
            "staging",
            {"PUBLISH_API_URL": "http://127.0.0.1:8101/api/v1"},
            "port 8101 is the production API",
        ),
        ("staging", {"SITE_URL": "https://prod.example.com"}, "SITE_URL"),
    ],
)
def test_deploy_check_refuses_settings_from_the_other_tier(tmp_path, tier, change, named):
    base = (
        _filled_in_production_env(tmp_path)
        if tier == "production"
        else _filled_in_staging_env(tmp_path)
    )
    res, report = _deploy_report(base | change)
    isolation = _check(report, "isolation")
    assert isolation["level"] == "error" and named in isolation["message"], isolation
    assert report["status"] == "error" and res.returncode == 2
    _assert_no_secrets(res, "db-password-123")


def test_deploy_check_asks_for_the_tier_and_ignores_lookalike_words(tmp_path):
    env = _filled_in_staging_env(tmp_path)
    env.pop("TPA_ENVIRONMENT")
    _, report = _deploy_report(env)
    assert _check(report, "TPA_ENVIRONMENT")["level"] == "warning"
    from app.services.deploy_check import _names_tier

    assert _names_tier("tpa_staging", "staging") and _names_tier("/srv/prod/site", "production")
    assert not _names_tier("/var/lib/tpa/stagecoach", "staging")
    assert not _names_tier("https://products.example.com", "production")

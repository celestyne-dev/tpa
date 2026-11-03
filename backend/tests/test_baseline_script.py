"""The read-only production baseline script (deploy/verify/tpa-baseline.sh).

It runs here against a fake release directory with the system tools stubbed, so the
test proves what the script reports and that it never changes anything.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "verify" / "tpa-baseline.sh"

REBUILD_HTML = (
    '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1" />'
    '<meta name="theme-color" content="#f7f2e8" /><meta name="tpa-build" content="abc1234 2026-11-03" />'
    "<title>Think Positive Always</title>"
    '<script type="module" src="/assets/index-x.js"></script></head>'
    '<body><div id="root" data-prerendered="true"></div></body></html>'
)
LEGACY_HTML = (
    '<html><head><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />'
    '<meta name="theme-color" content="#ffffff" /><title>Legacy</title>'
    '<meta property="og:image" content="/uploads/0123456789abcdef0123456789abcdef.webp" /></head></html>'
)


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path: Path, public_html: str) -> str:
    site = tmp_path / "site"
    release = site / "releases" / "r1"
    release.mkdir(parents=True)
    (release / "index.html").write_text(REBUILD_HTML)
    (release / "prerender-manifest.json").write_text(
        '{"generatedAt": "2026-11-03T10:00:00Z", "release": "abc1234", '
        '"siteUrl": "https://example.com", "indexing": true, "pages": [{"path": "/"}]}'
    )
    (site / "current").symlink_to(release)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    # Every stub records its arguments, so the test can see exactly what the script ran.
    record = f'echo "$(basename "$0") $*" >> {log}'
    conf = (
        "# configuration file /etc/nginx/sites-enabled/tpa:\n"
        "server {\n    listen 443 ssl;\n    server_name example.com www.example.com;\n"
        f"    root {site}/current;\n    location / {{ try_files $uri @tpa_fallback; }}\n}}\n"
        "upstream tpa_api {\n    server 127.0.0.1:8101;\n}\n"
    )
    (tmp_path / "nginx.conf").write_text(conf)
    _stub(
        bin_dir,
        "nginx",
        record
        + f'\n[[ "$1" == -T ]] && cat {tmp_path}/nginx.conf; [[ "$1" == -t ]] && echo "test is successful" >&2; exit 0',
    )
    (tmp_path / "public.html").write_text(public_html)
    (tmp_path / "origin.html").write_text(REBUILD_HTML)
    _stub(
        bin_dir,
        "curl",
        record
        + "\n"
        + 'args="$*"\n'
        + 'if [[ "$args" == *"-o /dev/null"* ]]; then echo -n 200; exit 0; fi\n'
        + 'if [[ "$args" == *-I* || "$args" == *-skI* || "$args" == *-sI* ]]; then printf "Server: nginx\\r\\nAge: 4100\\r\\nCF-Cache-Status: HIT\\r\\n"; exit 0; fi\n'
        + 'if [[ "$args" == *8101* ]]; then echo \'{"data":{"status":"ok","release":"abc1234"}}\'; exit 0; fi\n'
        + f'if [[ "$args" == *--resolve* ]]; then cat {tmp_path}/origin.html; else cat {tmp_path}/public.html; fi',
    )
    for name in ("systemctl", "ss", "openssl", "getent", "timeout"):
        _stub(bin_dir, name, record + "\nexit 0")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    res = subprocess.run(
        ["bash", str(SCRIPT), "example.com", str(site), "8101"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert res.returncode == 0, res.stderr
    return res.stdout, log.read_text()


def test_baseline_tells_the_origin_apart_from_a_cached_public_copy(tmp_path):
    out, calls = _run(tmp_path, LEGACY_HTML)
    # The active release and its manifest.
    assert "-> " in out and "releases/r1" in out
    assert "release       abc1234" in out and "generatedAt   2026-11-03T10:00:00Z" in out
    # nginx: the block for the domain, its root and the upstream port.
    assert "server_name example.com www.example.com;" in out
    assert "server 127.0.0.1:8101;" in out
    origin = out.split("== Origin response")[1].split("== Public response")[0]
    public = out.split("== Public response")[1].split("== TPA services")[0]
    # Origin: the rebuild. Public (stubbed as a stale cache): the legacy page and cache markers.
    assert 'content="#f7f2e8"' in origin and "/uploads/ 0 refs" in origin
    assert 'content="#ffffff"' in public and "viewport-fit=cover" in public
    assert "/uploads/ 1 refs" in public and "CF-Cache-Status: HIT" in public


def test_baseline_is_read_only(tmp_path):
    _out, calls = _run(tmp_path, REBUILD_HTML)
    # Only reading commands reached the stubs.
    for line in calls.splitlines():
        tool, _, args = line.partition(" ")
        if tool == "systemctl":
            assert args.split()[0] in {"list-units", "list-timers", "is-enabled", "is-active"}, line
        if tool == "nginx":
            assert args.split()[0] in {"-t", "-T"}, line
        if tool == "curl":
            assert not re.search(r"(^|\s)-(X|d|T|F)\b|--data|--upload", args), line
    text = SCRIPT.read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in (
        r"\brm\b",
        r"\bmv\b",
        r"\bln\b",
        r"\bcp\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"systemctl (start|stop|restart|reload|enable|disable|mask)",
        r"nginx -s",
        r"\bpsql\b",
        r"\bpg_",
        r"\bflask\b",
        r"\bgit\b",
        r"\btee\b",
        r"(?<![-=\w<])>>?\s*(?!/dev/null|&)\S",  # shell writes go only to /dev/null
    ):
        assert not re.search(forbidden, code), forbidden
    # Never prints environment values.
    assert "/etc/tpa" not in code and "env" not in re.sub(r"getent|environment", "", code)


def test_baseline_script_has_valid_syntax():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0

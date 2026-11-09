"""Screenshots of the policy pages and cookie settings at 390/820/1440 px (temporary)."""
import http.server, json, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

DIST = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve(); OUT.mkdir(parents=True, exist_ok=True)

class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        t = DIST / path.lstrip("/")
        if t.is_file(): return str(t)
        if (t / "index.html").is_file(): return str(t / "index.html")
        return str(DIST / "404.html")
    def log_message(self, *a): pass

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
PAGES = ["/cookie-policy", "/editorial-policy", "/refund-policy", "/accessibility",
         "/disclaimer", "/advertising-policy", "/community-guidelines", "/copyright-policy"]
report = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, (w, h) in {"390": (390, 844), "820": (820, 1180), "1440": (1440, 900)}.items():
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.route("**/api/**", lambda r: r.abort())
        for path in PAGES:
            pg.goto(base + path, wait_until="networkidle"); pg.wait_for_timeout(300)
            info = pg.evaluate("""()=>({overflow:document.documentElement.scrollWidth-innerWidth,
              h1:[...document.querySelectorAll('h1')].map(e=>e.textContent.trim()),
              robots:document.querySelector('meta[name=robots]')?.content,
              canonical:document.querySelector('link[rel=canonical]')?.href,
              title:document.title,
              toc:document.querySelectorAll('nav[aria-label="Table of contents"] a[href^="#"]').length,
              brokenAnchors:[...document.querySelectorAll('nav[aria-label="Table of contents"] a[href^="#"]')].filter(a=>!document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)))).length,
              notice:!!document.querySelector('section[aria-label="Cookie notice"]'),
              cookieButton:[...document.querySelectorAll('footer button')].map(b=>b.textContent.trim())})""")
            report.append({"width": name, "path": path, **info})
            slug = path.strip("/")
            if path in ("/cookie-policy", "/editorial-policy", "/refund-policy") or name == "390":
                pg.screenshot(path=str(OUT / f"{slug}-{name}.png"), full_page=True)
        # The notice (consent mode build) and the panel, in the viewport.
        pg.goto(base + "/accessibility", wait_until="networkidle"); pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / f"notice-{name}.png"))
        pg.get_by_role("button", name="Customise").click(); pg.wait_for_timeout(300)
        pg.screenshot(path=str(OUT / f"panel-{name}.png"))
        # Keyboard: Tab order inside the dialog, Escape closes, focus returns.
        focus = []
        for _ in range(6):
            pg.keyboard.press("Tab")
            focus.append(pg.evaluate("document.activeElement.getAttribute('aria-label')||document.activeElement.textContent.trim().slice(0,30)"))
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        report.append({"width": name, "keyboard": focus,
                       "dialogClosed": pg.evaluate("!document.querySelector('[role=dialog]')")})
        # Reject in the notice, then reopen from the footer link.
        pg.get_by_role("button", name="Reject").click(); pg.wait_for_timeout(200)
        stored = pg.evaluate("localStorage.getItem('tpa:privacy-choices')")
        pg.locator("footer").get_by_role("button", name="Cookie settings").click(); pg.wait_for_timeout(300)
        checked = pg.get_by_role("switch", name="Usage statistics").is_checked()
        report.append({"width": name, "afterReject": stored, "switchChecked": checked,
                       "noticeGone": pg.evaluate("!document.querySelector('section[aria-label=\"Cookie notice\"]')")})
        pg.keyboard.press("Escape")
        pg.locator("footer").scroll_into_view_if_needed(); pg.wait_for_timeout(200)
        pg.locator("footer").screenshot(path=str(OUT / f"footer-{name}.png"))
        ctx.close()
    b.close()
(OUT / "report.json").write_text(json.dumps(report, indent=1))
srv.shutdown()

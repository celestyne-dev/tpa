/**
 * Local production preview that mirrors the Nginx configuration in
 * docs/deployment.md: static files from dist/, `<path>/index.html` for
 * prerendered routes, the admin SPA shell for /admin/*, dist/404.html with
 * HTTP 404 for unknown URLs, /api and /media proxied to Flask, and CMS
 * redirects answered by Flask (/_redirect) before falling back to the 404 page.
 * Usage: npm run serve:dist  (PORT, API_PROXY_TARGET, SERVE_DIR to serve a release)
 */
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const distDir = path.resolve(
  process.env.SERVE_DIR || path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "dist"),
);
const port = Number(process.env.PORT || 4173);
const apiTarget = new URL(process.env.API_PROXY_TARGET || "http://127.0.0.1:5000");

const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".woff2": "font/woff2",
  ".json": "application/json",
  ".xml": "application/xml",
  ".txt": "text/plain; charset=utf-8",
  ".webmanifest": "application/manifest+json",
};

async function resolveFile(urlPath) {
  const clean = path.normalize(decodeURIComponent(urlPath)).replace(/^(\.\.[/\\])+/, "");
  for (const candidate of [clean, path.join(clean, "index.html")]) {
    const file = path.join(distDir, candidate);
    if (!file.startsWith(distDir)) return null;
    try {
      if ((await stat(file)).isFile()) return file;
    } catch {
      /* try next */
    }
  }
  return null;
}

function send(res, status, file) {
  const headers = { "Content-Type": types[path.extname(file)] ?? "application/octet-stream" };
  // Same policy as Nginx: fingerprinted assets are immutable, HTML always revalidates.
  if (file.includes(`${path.sep}assets${path.sep}`))
    headers["Cache-Control"] = "public, max-age=31536000, immutable";
  else if (file.endsWith(".html")) headers["Cache-Control"] = "no-cache";
  res.writeHead(status, headers);
  createReadStream(file).pipe(res);
}

function proxy(req, res, targetPath, onMissing) {
  const upstreamReq = http.request(
    {
      host: apiTarget.hostname,
      port: apiTarget.port,
      path: targetPath,
      method: req.method,
      headers: req.headers,
    },
    (upstream) => {
      if (onMissing && upstream.statusCode === 404) {
        upstream.resume();
        onMissing();
        return;
      }
      res.writeHead(upstream.statusCode ?? 502, upstream.headers);
      upstream.pipe(res);
    },
  );
  upstreamReq.on("error", () => {
    if (onMissing) return onMissing();
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { code: "bad_gateway", message: "API unavailable." } }));
  });
  req.pipe(upstreamReq);
}

http
  .createServer(async (req, res) => {
    const { pathname } = new URL(req.url, "http://local");
    if (pathname.startsWith("/api/") || pathname.startsWith("/media/")) {
      proxy(req, res, req.url);
      return;
    }
    const file = await resolveFile(pathname);
    if (file) send(res, 200, file);
    else if (pathname === "/admin" || pathname.startsWith("/admin/"))
      send(res, 200, path.join(distDir, "admin", "index.html"));
    else
      // Like Nginx's @fallback: CMS redirects (real 301/308) first, then the 404 page.
      proxy(req, res, `/_redirect${pathname}`, () =>
        send(res, 404, path.join(distDir, "404.html")),
      );
  })
  .listen(port, () =>
    console.log(`Serving dist/ on http://localhost:${port} (API → ${apiTarget.origin})`),
  );

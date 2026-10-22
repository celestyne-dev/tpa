/**
 * Local production preview that mirrors the Nginx configuration in
 * docs/deployment.md: static files from dist/, `<path>/index.html` for
 * prerendered routes, dist/404.html with HTTP 404 for unknown URLs, and
 * /api proxied to Flask. Usage: npm run serve:dist  (PORT, API_PROXY_TARGET)
 */
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const distDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "dist");
const port = Number(process.env.PORT || 4173);
const apiTarget = new URL(process.env.API_PROXY_TARGET || "http://127.0.0.1:5000");

const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
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
  res.writeHead(status, {
    "Content-Type": types[path.extname(file)] ?? "application/octet-stream",
  });
  createReadStream(file).pipe(res);
}

http
  .createServer(async (req, res) => {
    const { pathname } = new URL(req.url, "http://local");
    if (pathname.startsWith("/api/")) {
      const proxy = http.request(
        {
          host: apiTarget.hostname,
          port: apiTarget.port,
          path: req.url,
          method: req.method,
          headers: req.headers,
        },
        (upstream) => {
          res.writeHead(upstream.statusCode ?? 502, upstream.headers);
          upstream.pipe(res);
        },
      );
      proxy.on("error", () => {
        res.writeHead(502, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: { code: "bad_gateway", message: "API unavailable." } }));
      });
      req.pipe(proxy);
      return;
    }
    const file = await resolveFile(pathname);
    if (file) send(res, 200, file);
    else send(res, 404, path.join(distDir, "404.html"));
  })
  .listen(port, () =>
    console.log(`Serving dist/ on http://localhost:${port} (API → ${apiTarget.origin})`),
  );

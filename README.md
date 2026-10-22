# Think Positive Always

The commercial home of **Think Positive Always (TPA)**: personal development articles, digital products, free resources, the newsletter, and brand partnerships.

The project uses a React/Vite frontend and a Python Flask API backed by PostgreSQL, the same architecture as Ticksy. Public pages are **prerendered to static HTML at build time** from Flask API data, so search engines receive complete content and metadata.

## 1. Technology stack

| Layer    | Technology                                                                                                                                          |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend | React 19, Vite 8, JavaScript/JSX, Tailwind CSS 4, React Router 8, Redux Toolkit 2, React Redux 9, Axios, Lucide React, Fontsource (Fraunces, Inter) |
| SEO      | Build-time prerendering (Vite SSR build + `react-dom/server`), built-in head manager, generated sitemap/robots                                      |
| Testing  | Vitest, React Testing Library, jsdom (frontend), pytest (backend)                                                                                   |
| Quality  | ESLint 9, Prettier (frontend), Ruff (backend)                                                                                                       |
| Backend  | Python 3.11+, Flask 3, Flask-RESTful, Flask-CORS, Flask-SQLAlchemy, Flask-Migrate, Marshmallow, python-dotenv, Gunicorn                             |
| Database | PostgreSQL (production, psycopg 3) and SQLite (local development)                                                                                   |
| Hosting  | Linux VPS with Nginx, Gunicorn, systemd, PostgreSQL and static frontend assets (see `docs/deployment.md`)                                           |

## 2. Folder structure

```
tpa/
├── frontend/                 React + Vite app
│   ├── public/               Static files (images, OG images, icon, manifest)
│   ├── scripts/
│   │   ├── prerender.mjs     Build-time HTML, sitemap and robots generation
│   │   └── serve-dist.mjs    Local production preview (mirrors Nginx)
│   └── src/
│       ├── app/              App root (shared by browser, prerender and tests)
│       ├── assets/styles/    Tailwind design tokens and global CSS
│       ├── components/       layout/ ui/ articles/ products/ newsletter/ home/ topics/ legal/ seo/
│       ├── config/           Site identity, navigation, routes
│       ├── data/             Static marketing copy and shared list queries
│       ├── hooks/            Data hooks (useArticles, useArticle, useTopics…)
│       ├── pages/            One component per route
│       ├── routes/           Route table and per-route data loaders
│       ├── services/         Axios client and content API
│       ├── store/            Redux Toolkit store and slices
│       ├── utils/            Formatting and structured data helpers
│       ├── entry-client.jsx  Browser entry (hydrates prerendered HTML)
│       └── entry-server.jsx  Prerender entry (renders a URL to HTML)
├── backend/                  Flask API
│   ├── app/
│   │   ├── api/              /api/v1 resources (health, site, topics, articles, products)
│   │   ├── config/           Development / testing / production configuration
│   │   ├── data/             Temporary sample content (JSON, replaced by PostgreSQL)
│   │   ├── extensions/       SQLAlchemy, Migrate and CORS instances
│   │   ├── models/           SQLAlchemy models (Batch 02)
│   │   ├── schemas/          Marshmallow request and response schemas
│   │   ├── services/         Business logic and content repository abstraction
│   │   └── utils/            Response envelopes and JSON error handling
│   ├── tests/                pytest suite
│   ├── requirements.txt      Runtime dependencies (requirements-dev.txt adds test tools)
│   └── wsgi.py               WSGI entry point (Flask CLI and Gunicorn)
├── deploy/                   Nginx and systemd example configuration
├── docs/                     Architecture and deployment documentation
└── scripts/build-production.sh
```

## 3. Requirements

- **Python 3.11 or newer** (tested with 3.13)
- **Node.js 20.19+ or 22.12+** (Node 22 LTS recommended) and npm
- On Ubuntu WSL: `sudo apt install python3 python3-venv python3-pip`

## 4. Environment variables

Both apps run without any configuration. Copy the examples to customise them:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Backend (`backend/.env`, server-side only):

| Variable                                                                              | Purpose                                                                                      |
| ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `FLASK_CONFIG`                                                                        | `development` (default), `testing` or `production`                                           |
| `SECRET_KEY`                                                                          | Required in production                                                                       |
| `DATABASE_URL`                                                                        | Required in production (PostgreSQL). Development falls back to SQLite in `backend/instance/` |
| `CORS_ORIGINS`                                                                        | Comma-separated list of approved browser origins (default: the Vite dev server)              |
| `TRUST_PROXY`                                                                         | `1` behind Nginx                                                                             |
| `CONTACT_EMAIL`, `PARTNERSHIPS_EMAIL`, `SOCIAL_*`, `MEDIA_KIT_URL`, `NEWSLETTER_OPEN` | Public business settings returned by `/api/v1/site`. Each one stays hidden until it is set   |

Frontend (`frontend/.env.local`). `VITE_*` values are embedded in the browser bundle, so never put secrets in them:

| Variable              | Purpose                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `VITE_SITE_URL`       | Public origin for canonical URLs, Open Graph and the sitemap (default `http://localhost:5173`)                           |
| `VITE_ALLOW_INDEXING` | `true` **only** for the verified production build. Any other value produces `noindex` tags and a disallow-all robots.txt |
| `VITE_API_BASE_URL`   | Browser API base (default `/api/v1`, proxied by Vite in development and by Nginx in production)                          |
| `API_PROXY_TARGET`    | Flask origin for the Vite dev proxy (default `http://127.0.0.1:5000`)                                                    |
| `PRERENDER_API_URL`   | Flask API used during `npm run build` (default `http://127.0.0.1:5000/api/v1`)                                           |

## 5. Local development (Ubuntu WSL)

**Backend** (terminal 1):

```bash
cd ~/development/code/tpa/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
flask --app wsgi run --debug          # http://127.0.0.1:5000/api/v1/health
```

**Frontend** (terminal 2):

```bash
cd ~/development/code/tpa/frontend
npm install
npm run dev                            # http://localhost:5173 (proxies /api to Flask)
```

The frontend and backend start independently. If the API is not running, the site shell still renders and each content section shows a retry message.

## 6. Tests and quality checks

```bash
# Backend
cd backend && source .venv/bin/activate
python -m pytest             # API, service and configuration tests
ruff check . && ruff format --check .

# Frontend
cd frontend
npm run lint
npm run format:check
npm run test                 # Vitest + React Testing Library
npm run check                # lint + format check + tests
```

## 7. Production build

The build prerenders pages from the API, so Flask must be reachable. The helper script starts a temporary local API for you:

```bash
./scripts/build-production.sh
# or, with the API already running:
cd frontend && npm run build
# Preview the result exactly as Nginx will serve it (real 404s, /api proxy):
npm run serve:dist           # http://localhost:4173
```

For a production build, set `VITE_SITE_URL` to the real domain. Set `VITE_ALLOW_INDEXING=true` only after the domain is verified and the site is ready to launch.

`npm run build` runs three steps:

1. `vite build`: the client bundle in `dist/`.
2. `vite build --ssr`: a server render bundle in `.ssr/` (temporary).
3. `node scripts/prerender.mjs`: fetches topics and articles from Flask and writes `dist/<route>/index.html` for every public route, plus `dist/404.html`, `sitemap.xml`, `robots.txt` and `prerender-manifest.json`. The build fails if the API is unreachable or returns errors, so it never ships empty pages.

## 8. SEO and prerendering approach

- **Why build-time prerendering?** TPA's editorial pages change only when content is published. Static HTML is the fastest, most robust option for crawlers and Core Web Vitals, and it keeps Flask as the only runtime service. A Node SSR server would be a second production process with no benefit at this stage. Vite's official SSR build is used directly with a small prerender script, which avoids a third-party prerender plugin that could break on Vite upgrades.
- **Every prerendered page contains:** a unique `<title>`, meta description, canonical URL, robots directive, Open Graph and Twitter tags, article metadata, JSON-LD (Organization, WebSite, Article, BreadcrumbList), semantic headings, image alt text, the full article content, and serialised Redux state for hydration.
- **Head management:** `react-helmet-async` v3 hands tags to React 19's native metadata hoisting and no longer collects head tags during server rendering, so a small built-in head manager is used instead (`src/components/seo/`). It writes into static HTML during prerendering and updates `document.head` during client navigation.
- **Invalid URLs:** unknown routes and slugs get `404.html` with an HTTP 404 status (Nginx `try_files … =404`). In the browser, the same unknown slugs render the not-found page.
- **Indexing safeguards:** pages are `noindex` and robots.txt disallows everything unless `VITE_ALLOW_INDEXING=true`.
- **Slugs and migration:** article slugs come from the API unchanged. Legacy URLs are redirected with Nginx 301 rules (`deploy/nginx/redirects.conf.example`). Articles carry `seo.canonical_url` and legacy fields; an article with an external canonical is left out of the sitemap.
- **New content:** the prerenderer discovers topics and articles from the API, so content published in PostgreSQL appears after the next build with no frontend code changes. Real-time publishing (a rebuild triggered by the CMS) is planned for the admin batches and is **not implemented yet**. See `docs/architecture.md`.

## 9. API (v1)

All responses use `{"data": …, "meta": {…}}`; errors use `{"error": {"code", "message", "details?"}}` with the correct HTTP status. Internal errors never expose stack traces.

| Endpoint                      | Notes                                                  |
| ----------------------------- | ------------------------------------------------------ |
| `GET /api/v1/health`          | Service status                                         |
| `GET /api/v1/site`            | Public business settings                               |
| `GET /api/v1/topics`          | `?featured=true\|false`                                |
| `GET /api/v1/topics/<slug>`   | 404 for unknown slugs                                  |
| `GET /api/v1/articles`        | `?topic=&featured=&page=&page_size=` (≤ 50), paginated |
| `GET /api/v1/articles/<slug>` | Article with body plus related articles                |
| `GET /api/v1/products`        | Upcoming product previews (no prices or purchasing)    |

## 10. Future PostgreSQL configuration

```bash
sudo -u postgres psql -c "CREATE USER tpa_user WITH PASSWORD 'change-me';"
sudo -u postgres psql -c "CREATE DATABASE tpa OWNER tpa_user;"
# backend/.env
DATABASE_URL=postgresql+psycopg://tpa_user:change-me@127.0.0.1:5432/tpa
flask --app wsgi db init      # once, when the first models land (Batch 02)
flask --app wsgi db migrate -m "initial schema" && flask --app wsgi db upgrade
```

`postgres://` and `postgresql://` URLs are normalised to the psycopg 3 driver automatically.

## 11. Deployment architecture

Nginx serves `frontend/dist` and proxies `/api/` to Gunicorn (`wsgi:app`), which systemd keeps running, with PostgreSQL behind it. Example configs are in `deploy/`, and step-by-step instructions are in `docs/deployment.md`. Nothing has been deployed yet.

## 12. Deferred features

Authentication (Flask-JWT-Extended), role-based access, the admin dashboard and CMS, database models and migrations, Paystack checkout, digital downloads, customer accounts, newsletter provider integration, contact forms, analytics, migration of the old website's articles, CMS-triggered rebuilds, and per-article OG image generation for new content (new articles currently fall back to the default share image).

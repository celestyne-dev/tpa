# Architecture

## Overview

```
Browser ──► Nginx ──► frontend/dist (prerendered HTML, JS, CSS, images)
                 └──► /api/* ──► Gunicorn ──► Flask (app factory)
                                              ├── api/       Flask-RESTful resources (/api/v1)
                                              ├── schemas/   Marshmallow validation and serialisation
                                              ├── services/  business logic
                                              └── services/content_repository.py
                                                    ├── LocalContentRepository (JSON, Batch 01)
                                                    └── SQLAlchemy repository (Batch 02, PostgreSQL)
```

Flask is the single source of truth for content and business settings. The React app reads everything through Axios (`src/services`) and stores shared server data in Redux Toolkit slices (`site`, `topics`, `articles`, `products`). Local UI state such as the mobile menu stays in components; the article filter lives in the URL.

## Data flow

1. Each route in `src/routes/routeConfig.js` declares the thunks its page needs (`load`).
2. **Prerendering:** `entry-server.jsx` dispatches those thunks against the Flask API, renders the page with `StaticRouter`, collects head tags, and returns HTML, head and the Redux state.
3. **Browser:** `entry-client.jsx` hydrates the prerendered HTML using the serialised state, so there is no refetch. On later client navigation, page hooks (`src/hooks/useContent.js`) fetch whatever is missing, with loading, error and retry states.

## Publishing PostgreSQL content without frontend changes

The prerender script never hard-codes slugs. It calls `GET /api/v1/topics` and pages through `GET /api/v1/articles`, so once Batch 02 swaps `LocalContentRepository` for a database repository, newly published articles are prerendered by the next build automatically.

Planned for the CMS batches (not implemented):

- On publish, update or unpublish, the API queues a rebuild job (for example, a systemd path unit or a small worker running `scripts/build-production.sh` against the live API) and atomically swaps `frontend/dist`.
- An optional incremental mode would re-render only changed slugs by calling `render(url)` for each affected path.
- Per-article OG images would be generated or uploaded and exposed as `seo.og_image`, which the frontend already uses.

## Migration readiness

- Article records keep their original `slug`, plus `source` (`sample` | `original` | `migrated`), `legacy` (`original_path`, `original_url`, `canonical_url`, `imported_at`) and `seo` overrides.
- The JSON sample format in `backend/app/data/articles.json` doubles as the import format.
- Legacy URL redirects belong in Nginx (`deploy/nginx/redirects.conf.example`) as 301s.

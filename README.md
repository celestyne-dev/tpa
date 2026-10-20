# Think Positive Always

The commercial home of **Think Positive Always (TPA)**: personal development articles, digital products, free resources, the newsletter, and brand partnerships.

Built with Next.js (App Router), React, TypeScript (strict), Tailwind CSS v4, and Lucide icons.

## Getting started

Requires Node.js 20.9 or later (Node 22 LTS recommended).

```bash
npm install
cp .env.example .env.local   # optional; every variable is optional
npm run dev                  # http://localhost:3000
```

## Scripts

| Command                | Purpose                                       |
| ---------------------- | --------------------------------------------- |
| `npm run dev`          | Start the development server                  |
| `npm run build`        | Production build                              |
| `npm run start`        | Serve the production build                    |
| `npm run lint`         | ESLint (Next.js core-web-vitals + TypeScript) |
| `npm run typecheck`    | TypeScript strict type check                  |
| `npm run format`       | Format with Prettier                          |
| `npm run format:check` | Check formatting                              |
| `npm run test`         | Unit and content integrity tests (Vitest)     |
| `npm run check`        | typecheck + lint + format check + tests       |

## Configuration

All environment variables are optional. The site builds and runs without any of them. See `.env.example`.

| Variable                         | Effect                                                                                                                  |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_SITE_URL`           | Base URL for canonical URLs, sitemap, Open Graph. Defaults to `http://localhost:3000`.                                  |
| `NEXT_PUBLIC_ALLOW_INDEXING`     | Set to `true` **only in production** to allow indexing. Otherwise every page is `noindex` and robots.txt disallows all. |
| `NEXT_PUBLIC_CONTACT_EMAIL`      | Shows a contact email on Contact and Partner pages.                                                                     |
| `NEXT_PUBLIC_PARTNERSHIPS_EMAIL` | Dedicated partnerships email (falls back to the contact email).                                                         |
| `NEXT_PUBLIC_SOCIAL_*`           | Social profile URLs (https only). Links stay hidden until set.                                                          |

Other switches live in `src/config/site.ts`:

- `newsletter.isOpen`: keep it `false` until a real email provider is integrated.
- `mediaKitUrl`: set this once a media kit exists.

## Project structure

```
src/
  app/                 Routes, metadata, sitemap, robots, OG images, error/404/loading
  components/
    layout/            Header, footer, mobile navigation, logo
    ui/                Design system primitives (Button, Card, Section, Badge, fields…)
    home/              Homepage sections
    articles/          Article cards, grid, filter, body renderer
    topics/            Topic cards and icons
    products/          Product preview cards and designed covers
    newsletter/        Newsletter presentation
    legal/             Legal page layout
  config/              Site identity, navigation, social links, legacy redirects
  data/                Local sample content (topics, articles, products)
  lib/
    content/           Async content repository (swap point for Supabase/CMS)
    env.ts, seo.ts, structured-data.ts, utils.ts, reading-time.ts
  types/               Shared content and navigation types
public/images/         Static artwork
```

### Content architecture

Pages read content only through `src/lib/content/*` (async functions such as `getArticles`, `getArticleBySlug`, `getTopics`). Replacing the local `src/data` source with database queries in a later batch means changing those functions, not the pages.

Article bodies are structured blocks (`paragraph`, `heading`, `list`, `quote`), so content renders without injecting raw HTML and can be mapped to and from a rich-text CMS format.

### Article migration readiness

- `Article.slug`: keep the original slugs when importing.
- `Article.source`: `"sample" | "original" | "migrated"`. Sample content is labelled in the UI.
- `Article.legacy`: `originalPath`, `originalUrl`, `canonicalUrl`, `importedAt`.
- `Article.seo`: per-article title, description, canonical, and `noIndex` overrides.
- `src/config/redirects.ts`: add `{ source, destination, permanent: true }` entries for old URLs. These are emitted as 308 redirects by `next.config.ts`.
- Articles with an external canonical URL are left out of the sitemap automatically.
- Raster featured images (JPG/PNG/WebP) go through `next/image` optimisation via `ContentImage`. Add remote hosts to `images.remotePatterns` when needed.

## Roadmap

- **Batch 02**: PostgreSQL/Supabase, authentication, role-based access, admin dashboard, CMS foundations.
- Later: newsletter integration, product catalog and checkout, secure downloads, customer accounts, analytics.

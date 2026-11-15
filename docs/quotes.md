# Quote collections (Admin › Quotes)

Quote collections live at `/quotes/<slug>` and are listed on `/quotes`. They are stored
with articles (`articles.content_type = 'quotes'`) so they reuse the article editor,
autosave, revisions, review, previews, scheduling, SEO fields and publishing (every
publish, update or unpublish queues the normal site rebuild). Everything article-facing
(`/articles`, topic pages, search, RSS, author pages, newsletter automations, article
pickers) shows articles only.

## Writing a collection

1. **Admin › Quotes › New quote collection.** Give it a title, excerpt, topic and
   featured image. An author is optional (the byline falls back to Think Positive Always).
2. **Introduction:** a paragraph before the first quotes: why these quotes, and how to use
   them.
3. **Quotes:** a *Numbered list*, one quote per line, ending with the attribution:
   `Courage is a habit. — Mary Daly` (or `— Unknown`). Bold, italic and links work.
4. **Images between quotes:** add an *Image* block. Give the image a clear title, alt text
   and a credit (or source) in the Media Library; the optional *Pinterest description* is
   used by "Save to Pinterest". Images are part of the collection; they never get pages
   of their own.
5. **More quotes:** use *More quotes (continue from N)*, or set *starts at* / *Continue
   numbering* on a numbered list, so 1–5 → image → 6–10 continues. Lists never continue
   automatically.
6. **Reflections:** paragraphs, headings and the *Key points*, *Example / case study*,
   *Exercise / reflection* and *Further reading* blocks.
7. **Preview**, then **Publish** (or schedule).

## Quality checklist and indexing

New collections start with **indexing off**. The SEO panel lists the editorial checks:
an original introduction, the editor's own commentary, attributions, continuous
numbering, repeated quotes, quotes that also appear in other collections, and image
rights (a credit or source on every image). They are guidance, not word counts, and none
blocks publishing. Turn indexing on (SEO permission) once the collection is ready; only
indexable collections (own canonical, not noindex) are in the sitemap, with their
images. `/quotes` is in the sitemap once there is an indexable collection; filtered
views (`?topic=`, `?q=`) are noindex.

## Elsewhere on the site

- **Homepage builder / any page / article sidebar:** the *Quote collections* section
  (latest, hand-picked, or on the article's topic in the sidebar; grid or carousel).
- **Articles** show up to two collections on the same topic ("Quotes on this topic").
- **Navigation:** the default header and footer link to `/quotes` once a collection is
  published. A menu saved in Admin › Navigation is never changed: add "Quotes" there (it
  is offered in the link picker under *Quotes*).
- **/quotes landing page:** built in; publish a CMS page at `/quotes` (Admin › Pages) to
  replace it with your own layout.

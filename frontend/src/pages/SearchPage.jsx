import { Search } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useDispatch } from "react-redux";
import { Link, useSearchParams } from "react-router";
import { Seo } from "@/components/seo/Seo";
import { ArticleMeta } from "@/components/articles/ArticleMeta";
import { Container } from "@/components/ui/Container";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { routes } from "@/config/navigation";
import { runSearch } from "@/store/slices/authorsSlice";

const MAX_QUERY = 100;
const TYPING_DELAY_MS = 250;

/** Wraps the searched words in <mark> (plain text only; never HTML). */
export function Highlight({ text, terms }) {
  const value = String(text ?? "");
  const words = (terms ?? []).filter(Boolean);
  if (words.length === 0) return value;
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  return value.split(pattern).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded bg-gold-100 px-0.5 text-charcoal">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

function searchHref(q, page) {
  const params = new URLSearchParams({ q });
  if (page > 1) params.set("page", String(page));
  return `${routes.search}?${params}`;
}

/**
 * Site search. The form is a plain GET form (works without JavaScript); with JavaScript,
 * results update as you type and the result count is announced to screen readers.
 * Search pages are never indexed.
 */
export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const dispatch = useDispatch();
  const inputId = useId();
  const q = (searchParams.get("q") ?? "").slice(0, MAX_QUERY);
  const page = Math.max(1, Number.parseInt(searchParams.get("page") ?? "1", 10) || 1);
  const [draft, setDraft] = useState(q);
  const [draftFor, setDraftFor] = useState(q);
  // Results are tagged with the query they answer; anything else is still loading.
  const [answer, setAnswer] = useState(null);
  const typing = useRef(null);
  const key = `${page}:${q}`;

  // Keep the box in step with the address (back/forward, links): adjusted while rendering.
  if (q !== draftFor) {
    setDraftFor(q);
    setDraft(q);
  }

  useEffect(() => {
    if (!q.trim()) return undefined;
    let cancelled = false;
    dispatch(runSearch({ q, page }))
      .unwrap()
      .then((data) => {
        if (!cancelled) setAnswer({ key, status: "done", ...data });
      })
      .catch(() => {
        if (!cancelled) setAnswer({ key, status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [dispatch, q, page, key]);

  const idle = { status: "idle", results: [], terms: [], pagination: null };
  const state = !q.trim()
    ? idle
    : answer?.key === key
      ? { ...idle, ...answer }
      : { ...idle, status: "loading" };

  const onChange = (event) => {
    const value = event.target.value.slice(0, MAX_QUERY);
    setDraft(value);
    clearTimeout(typing.current);
    typing.current = setTimeout(() => {
      setSearchParams(value.trim() ? { q: value } : {}, { replace: true });
    }, TYPING_DELAY_MS);
  };
  const onSubmit = (event) => {
    event.preventDefault();
    clearTimeout(typing.current);
    setSearchParams(draft.trim() ? { q: draft } : {});
  };
  useEffect(() => () => clearTimeout(typing.current), []);

  const total = state.pagination?.total ?? 0;
  let status = "";
  if (state.status === "loading") status = "Searching…";
  else if (state.status === "error") status = "Search isn't available right now. Please try again.";
  else if (state.status === "done")
    status =
      total === 0
        ? `No articles found for “${q}”.`
        : `${total} ${total === 1 ? "article" : "articles"} found for “${q}”.`;

  return (
    <>
      <Seo title={q ? `Search: ${q}` : "Search"} path={routes.search} noIndex />
      <PageHeader eyebrow="Search" title="Search articles" />
      <Container size="narrow" className="py-12 sm:py-16">
        <form role="search" action={routes.search} method="get" onSubmit={onSubmit}>
          <label htmlFor={inputId} className="block text-sm font-semibold text-charcoal">
            Search for articles
          </label>
          <div className="mt-2 flex gap-3">
            <input
              id={inputId}
              type="search"
              name="q"
              value={draft}
              onChange={onChange}
              maxLength={MAX_QUERY}
              autoComplete="off"
              placeholder="e.g. confidence, starting over, gratitude"
              className="min-h-12 w-full rounded-full border border-charcoal/20 bg-white px-5 text-base text-ink placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-700"
            />
            <button
              type="submit"
              className="inline-flex min-h-12 items-center gap-2 rounded-full bg-sage-700 px-6 font-semibold text-ivory hover:bg-sage-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-700"
            >
              <Search aria-hidden className="size-4" />
              Search
            </button>
          </div>
        </form>

        <p role="status" aria-live="polite" className="mt-6 min-h-6 text-sm text-muted">
          {status}
        </p>

        {state.results.length > 0 && (
          <ol className="mt-6 divide-y divide-charcoal/10" aria-label="Search results">
            {state.results.map((article) => (
              <li key={article.slug} className="py-6">
                {article.topic && (
                  <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
                    {article.topic.name}
                  </p>
                )}
                <h2 className="mt-2 font-serif text-2xl leading-snug">
                  <Link
                    to={routes.article(article.slug)}
                    className="text-charcoal hover:text-sage-700 hover:underline hover:underline-offset-4"
                  >
                    <Highlight text={article.title} terms={state.terms} />
                  </Link>
                </h2>
                {article.excerpt && (
                  <p className="mt-2 text-base text-charcoal/80">
                    <Highlight text={article.excerpt} terms={state.terms} />
                  </p>
                )}
                <ArticleMeta
                  className="mt-3"
                  publishedAt={article.published_at}
                  updatedAt={article.content_modified_at}
                  readingTimeMinutes={article.reading_time_minutes}
                />
              </li>
            ))}
          </ol>
        )}

        {state.pagination && (
          <Pagination
            page={state.pagination.page}
            totalPages={state.pagination.total_pages}
            hrefFor={(p) => searchHref(q, p)}
            label="Search result pages"
          />
        )}
      </Container>
    </>
  );
}

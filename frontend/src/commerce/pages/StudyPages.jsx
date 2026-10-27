import { Bookmark, Download, Highlighter, ListChecks, NotebookPen, Search } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { routes } from "@/config/navigation";
import { useCustomer } from "@/hooks/useShop";
import { AccountShell } from "../AccountShell";
import { RequireCustomer } from "../RequireCustomer";
import { LearningSearchForm } from "./LearningPages";

const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : "";

const SWATCH = {
  yellow: "border-[#d4a72c] bg-[#fde68a]/40",
  green: "border-[#3f9d63] bg-[#bbf7d0]/40",
  blue: "border-[#4a7fd1] bg-[#bfdbfe]/40",
  pink: "border-[#c9598f] bg-[#fbcfe8]/40",
};

const TABS = [
  { key: "notes", label: "My notes", icon: NotebookPen },
  { key: "highlights", label: "Highlights", icon: Highlighter },
  { key: "bookmarks", label: "Bookmarks", icon: Bookmark },
  { key: "checklists", label: "Checklists", icon: ListChecks },
];

function useDebounced(value, delay = 300) {
  const [out, setOut] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setOut(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return out;
}

function LessonLink({ item, highlight }) {
  if (!item.lesson.available || !item.lesson.slug) {
    return (
      <span className="text-muted">
        {item.lesson.title}
        <span className="text-sm"> · not available right now</span>
      </span>
    );
  }
  const to = routes.learn(item.course.slug, item.lesson.slug);
  return (
    <Link
      to={highlight ? `${to}?highlight=${encodeURIComponent(highlight)}` : to}
      className="font-medium text-sage-800 underline underline-offset-4"
    >
      {item.lesson.title}
    </Link>
  );
}

function Excerpt({ anchor, color }) {
  if (!anchor) return null;
  if (anchor.hidden) {
    return (
      <p className="text-sm text-muted italic">Excerpt hidden while you can't open this course.</p>
    );
  }
  return (
    <blockquote
      className={`rounded-r-lg border-l-4 py-1 pr-2 pl-3 ${color ? SWATCH[color] : "border-gold-400"}`}
    >
      “{anchor.quote}”
      {anchor.status === "orphaned" && (
        <span className="mt-1 block text-xs text-muted">
          Saved excerpt — the lesson text has changed since you saved it.
        </span>
      )}
    </blockquote>
  );
}

function Meta({ item, date }) {
  return (
    <p className="text-sm text-muted">
      {item.course.title} · <LessonLink item={item} highlight={item.color && item.id} />
      {date && <> · {formatDate(date)}</>}
    </p>
  );
}

function Notebook() {
  const shopApi = useShopApi();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.key === params.get("tab")) ? params.get("tab") : "notes";
  const course = params.get("course") ?? "";
  const [q, setQ] = useState(params.get("q") ?? "");
  const query = useDebounced(q);
  const [state, setState] = useState({ status: "loading", data: null });
  const ids = useId();

  useEffect(() => {
    let live = true;
    shopApi.notebook({ ...(course && { course }), ...(query.trim() && { q: query.trim() }) }).then(
      (res) => live && setState({ status: "ready", data: res.data }),
      (error) => live && setState({ status: "error", error }),
    );
    return () => {
      live = false;
    };
  }, [shopApi, course, query]);

  const set = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  if (state.status === "error") return <ErrorState title="We couldn't load your notebook" />;
  const data = state.data;
  const counts = data
    ? {
        notes: data.notes.length,
        highlights: data.highlights.length,
        bookmarks: data.bookmarks.length,
        checklists: data.checklists.length,
      }
    : {};

  return (
    <div className="space-y-6">
      <p className="text-muted">
        Your private notes, highlights, saved lessons and checklist progress from every course. Only
        you can see them.
      </p>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem]">
        <div>
          <label htmlFor={`${ids}-q`} className="text-sm font-medium">
            Search your notebook
          </label>
          <input
            id={`${ids}-q`}
            type="search"
            value={q}
            maxLength={120}
            onChange={(e) => {
              setQ(e.target.value);
              set("q", e.target.value);
            }}
            placeholder="Words in a note, highlight, lesson or course"
            className="mt-1 w-full rounded-xl border border-charcoal/15 bg-white px-3 py-2.5"
          />
        </div>
        <div>
          <label htmlFor={`${ids}-course`} className="text-sm font-medium">
            Course
          </label>
          <select
            id={`${ids}-course`}
            value={course}
            onChange={(e) => set("course", e.target.value)}
            className="mt-1 w-full rounded-xl border border-charcoal/15 bg-white px-3 py-2.5"
          >
            <option value="">All courses</option>
            {(data?.courses ?? []).map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.title}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">Export notes and highlights:</span>
        {[
          ["txt", "Text file"],
          ["pdf", "PDF"],
        ].map(([format, label]) => (
          <a
            key={format}
            href={shopApi.notebookExportUrl(format, course || undefined)}
            className="inline-flex items-center gap-1 font-medium text-sage-800 underline underline-offset-4"
          >
            <Download aria-hidden className="size-4" /> {label}
          </a>
        ))}
      </div>
      <div role="tablist" aria-label="Notebook sections" className="flex flex-wrap gap-2">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={`${ids}-tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`${ids}-panel`}
            onClick={() => set("tab", key === "notes" ? "" : key)}
            className="inline-flex items-center gap-2 rounded-full border border-charcoal/15 px-4 py-2 text-sm font-medium aria-selected:border-sage-700 aria-selected:bg-sage-50"
          >
            <Icon aria-hidden className="size-4" /> {label}
            {data && <span className="text-muted">({counts[key]})</span>}
          </button>
        ))}
      </div>
      <div id={`${ids}-panel`} role="tabpanel" aria-labelledby={`${ids}-tab-${tab}`}>
        {state.status === "loading" ? (
          <p role="status">Loading your notebook…</p>
        ) : (
          <NotebookPanel tab={tab} data={data} filtered={Boolean(course || query.trim())} />
        )}
      </div>
    </div>
  );
}

function NotebookPanel({ tab, data, filtered }) {
  const empty = {
    notes: "Notes you write while reading appear here.",
    highlights: "Select text in a lesson and choose a colour to highlight it.",
    bookmarks: "Use “Save lesson” in the reader to bookmark lessons.",
    checklists: "Checklists you tick in lessons appear here.",
  };
  const items = data[tab];
  if (!items.length) {
    return (
      <EmptyState
        icon={NotebookPen}
        title={filtered ? "Nothing matches" : "Nothing here yet"}
        description={filtered ? "Try another word or course." : empty[tab]}
      />
    );
  }
  return (
    <ul className="space-y-4">
      {tab === "notes" &&
        items.map((note) => (
          <li key={note.id} className="rounded-2xl border border-charcoal/10 bg-white p-5">
            <Meta item={note} date={note.updated_at} />
            {note.anchor && (
              <div className="mt-3">
                <Excerpt anchor={note.anchor} />
              </div>
            )}
            <p className="mt-3 whitespace-pre-line">{note.body}</p>
          </li>
        ))}
      {tab === "highlights" &&
        items.map((item) => (
          <li key={item.id} className="rounded-2xl border border-charcoal/10 bg-white p-5">
            <Meta item={item} date={item.created_at} />
            <div className="mt-3">
              <Excerpt anchor={{ ...item.anchor, status: item.status }} color={item.color} />
            </div>
          </li>
        ))}
      {tab === "bookmarks" &&
        items.map((item) => (
          <li
            key={`${item.course.slug}/${item.lesson.title}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-charcoal/10 bg-white p-5"
          >
            <span>
              <LessonLink item={item} />
              <span className="block text-sm text-muted">{item.course.title}</span>
            </span>
            {item.access !== "active" && (
              <span className="rounded-full bg-cream px-3 py-1 text-sm">
                Access ended ·{" "}
                <Link to={routes.course(item.course.slug)} className="underline">
                  course page
                </Link>
              </span>
            )}
          </li>
        ))}
      {tab === "checklists" &&
        items.map((item) => (
          <li
            key={`${item.course.slug}/${item.lesson.title}`}
            className="rounded-2xl border border-charcoal/10 bg-white p-5"
          >
            <Meta item={item} date={item.updated_at} />
            <ul className="mt-2 space-y-1">
              {item.lists.map((list, i) => (
                <li key={i}>
                  {list.title}: {list.done} of {list.total} ticked
                  {list.required && <span className="text-sm text-muted"> (required)</span>}
                </li>
              ))}
            </ul>
          </li>
        ))}
    </ul>
  );
}

export function NotebookPage() {
  return (
    <RequireCustomer>
      <AccountShell title="Study notebook" path={routes.notebook}>
        <Notebook />
      </AccountShell>
    </RequireCustomer>
  );
}

// ---- course search ------------------------------------------------------------------------

function Marked({ text, terms }) {
  if (!terms?.length) return text;
  const pattern = new RegExp(
    `(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi",
  );
  return text.split(pattern).map((part, i) =>
    i % 2 ? (
      <mark key={i} className="rounded bg-gold-100 px-0.5 text-charcoal">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

export function LearningSearchPage() {
  const shopApi = useShopApi();
  const { customer } = useCustomer();
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    if (!q.trim()) return undefined;
    let live = true;
    Promise.resolve()
      .then(() => live && setState({ status: "loading" }))
      .then(() => shopApi.searchLearning(q))
      .then(
        (res) => live && setState({ status: "ready", data: res.data }),
        (error) => live && setState({ status: "error", error }),
      );
    return () => {
      live = false;
    };
  }, [shopApi, q, customer]);

  const data = state.data;
  return (
    <>
      <Seo title="Search courses" path={routes.learnSearch} noIndex />
      <Container size="narrow" className="py-12">
        <h1 className="text-3xl font-medium sm:text-4xl">Search courses</h1>
        <p className="mt-2 text-muted">
          {customer
            ? "Search course titles and the lessons of courses you can open."
            : "Search the catalogue and free preview lessons. Sign in to search your courses."}
        </p>
        <div className="mt-6">
          <LearningSearchForm key={q} initial={q} />
        </div>
        <div className="mt-8" aria-live="polite">
          {!q.trim() ? null : state.status === "loading" || state.status === "idle" ? (
            <p role="status">Searching…</p>
          ) : state.status === "error" ? (
            <p role="alert" className="rounded-2xl bg-red-50 p-4">
              {state.error?.details?.q?.[0] ?? "Search isn't available right now."}
            </p>
          ) : !data.courses.length && !data.lessons.length ? (
            <EmptyState
              icon={Search}
              title={`No results for “${data.query}”`}
              description="Try fewer or different words."
            />
          ) : (
            <div className="space-y-8">
              <p role="status" className="text-sm text-muted">
                {data.lessons.length} lesson{data.lessons.length === 1 ? "" : "s"} and{" "}
                {data.courses.length} course{data.courses.length === 1 ? "" : "s"} for “{data.query}
                ”
              </p>
              {data.lessons.length > 0 && (
                <section aria-labelledby="lesson-results">
                  <h2 id="lesson-results" className="text-xl font-medium">
                    Lessons
                  </h2>
                  <ul className="mt-3 space-y-3">
                    {data.lessons.map((r) => (
                      <li
                        key={`${r.course.slug}/${r.slug}`}
                        className="rounded-2xl border border-charcoal/10 bg-white p-5"
                      >
                        <Link
                          to={routes.learn(r.course.slug, r.slug)}
                          className="font-medium text-sage-800 underline underline-offset-4"
                        >
                          <Marked text={r.title} terms={data.terms} />
                        </Link>
                        <p className="text-sm text-muted">
                          {r.course.title} · {r.module}
                          {r.access === "preview" && " · Free preview"}
                        </p>
                        <p className="mt-2">
                          <Marked text={r.snippet} terms={data.terms} />
                        </p>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {data.courses.length > 0 && (
                <section aria-labelledby="course-results">
                  <h2 id="course-results" className="text-xl font-medium">
                    Courses
                  </h2>
                  <ul className="mt-3 space-y-3">
                    {data.courses.map((c) => (
                      <li
                        key={c.slug}
                        className="rounded-2xl border border-charcoal/10 bg-white p-5"
                      >
                        <Link
                          to={c.enrolled ? routes.learn(c.slug) : routes.course(c.slug)}
                          className="font-medium text-sage-800 underline underline-offset-4"
                        >
                          <Marked text={c.title} terms={data.terms} />
                        </Link>
                        {c.enrolled && <span className="ml-2 text-sm text-muted">Enrolled</span>}
                        <p className="mt-1 text-muted">{c.summary}</p>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}
        </div>
      </Container>
    </>
  );
}

import {
  Bookmark,
  BookmarkCheck,
  CheckCircle2,
  ChevronDown,
  Circle,
  Highlighter,
  ListTree,
  NotebookPen,
  Settings2,
  StickyNote,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/Button";
import { routes } from "@/config/navigation";
import { formatMinutes, sectionId } from "../courseFormat";
import { READER_LABELS, READER_OPTIONS } from "./readerPrefs";
import { useAutosave } from "./readerHooks";
import { COLOR_LABELS, COLORS } from "./textAnchors";

const SWATCH = {
  yellow: "bg-[#fde68a]",
  green: "bg-[#bbf7d0]",
  blue: "bg-[#bfdbfe]",
  pink: "bg-[#fbcfe8]",
};
const BORDER = {
  yellow: "border-[#d4a72c]",
  green: "border-[#3f9d63]",
  blue: "border-[#4a7fd1]",
  pink: "border-[#c9598f]",
};

// ---- display settings ---------------------------------------------------------------------

export function ReaderSettings({ prefs, onChange, status }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div className="relative">
      <Button
        variant="outline"
        size="sm"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <Settings2 aria-hidden className="size-4" /> Display
      </Button>
      {open && (
        <div
          id={panelId}
          className="absolute right-0 z-30 mt-2 w-[min(20rem,calc(100vw-2rem))] rounded-2xl border border-charcoal/10 bg-white p-4 text-base shadow-lift"
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        >
          <div className="flex items-center justify-between">
            <p className="font-medium">Reading display</p>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close display settings"
              className="grid size-9 place-items-center rounded-full hover:bg-cream"
            >
              <X aria-hidden className="size-4" />
            </button>
          </div>
          {Object.entries(READER_OPTIONS).map(([key, options]) => (
            <fieldset key={key} className="mt-3">
              <legend className="text-sm font-medium text-muted">{READER_LABELS[key]}</legend>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {options.map(([value, label]) => (
                  <label
                    key={value}
                    className="cursor-pointer rounded-full border border-charcoal/15 px-3 py-1.5 text-sm has-[:checked]:border-sage-700 has-[:checked]:bg-sage-50 has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-sage-600"
                  >
                    <input
                      type="radio"
                      className="sr-only"
                      name={`${panelId}-${key}`}
                      value={value}
                      checked={prefs[key] === value}
                      onChange={() => onChange({ [key]: value })}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          <p role="status" className="mt-3 min-h-5 text-xs text-muted">
            {status}
          </p>
          <p className="text-xs text-muted">
            Your browser's zoom and text size settings still apply.
          </p>
        </div>
      )}
    </div>
  );
}

// ---- outline and table of contents ------------------------------------------------------------

function OutlineList({ courseSlug, outline }) {
  return (
    <ol className="space-y-5">
      {outline.map((module, m) => (
        <li key={module.id}>
          <p className="text-sm font-semibold">
            <span className="text-sage-700">Module {m + 1}.</span> {module.title}
          </p>
          <p className="text-xs text-muted">
            {module.completed} of {module.total} lessons done
          </p>
          <ol className="mt-2 space-y-0.5">
            {module.lessons.map((lesson) => (
              <li key={lesson.slug}>
                <Link
                  to={routes.learn(courseSlug, lesson.slug)}
                  aria-current={lesson.current ? "page" : undefined}
                  className={`flex items-start gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-cream aria-[current=page]:bg-sage-50 aria-[current=page]:font-medium`}
                >
                  {lesson.completed ? (
                    <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-sage-700" />
                  ) : (
                    <Circle aria-hidden className="mt-0.5 size-4 shrink-0 text-charcoal/30" />
                  )}
                  <span className="flex-1">
                    {lesson.title}
                    <span className="sr-only">{lesson.completed ? " (completed)" : ""}</span>
                  </span>
                  <span className="text-xs text-muted">{formatMinutes(lesson.minutes)}</span>
                </Link>
              </li>
            ))}
          </ol>
        </li>
      ))}
    </ol>
  );
}

/** Course outline: a sticky sidebar on desktop, a collapsible section on smaller screens. */
export function ReaderOutline({ courseSlug, outline, variant }) {
  const done = outline.reduce((n, m) => n + m.completed, 0);
  const total = outline.reduce((n, m) => n + m.total, 0);
  if (variant === "sidebar") {
    return (
      <nav
        aria-label="Course outline"
        className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto pr-2"
      >
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <ListTree aria-hidden className="size-4" /> Course outline
        </p>
        <OutlineList courseSlug={courseSlug} outline={outline} />
      </nav>
    );
  }
  return (
    <details className="group rounded-2xl border border-charcoal/10 bg-white text-base lg:hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 font-medium [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2">
          <ListTree aria-hidden className="size-4" /> Course outline
          <span className="text-sm font-normal text-muted">
            ({done} of {total} done)
          </span>
        </span>
        <ChevronDown aria-hidden className="size-4 transition-transform group-open:rotate-180" />
      </summary>
      <nav aria-label="Course outline" className="border-t border-charcoal/10 px-3 py-4">
        <OutlineList courseSlug={courseSlug} outline={outline} />
      </nav>
    </details>
  );
}

export function TableOfContents({ toc, onJump }) {
  if (!toc || toc.length < 2) return null;
  return (
    <nav aria-label="In this lesson" className="text-sm">
      <p className="font-semibold">In this lesson</p>
      <ol className="mt-2 space-y-1 border-l border-charcoal/10">
        {toc.map((item) => (
          <li key={item.uid} className={item.level === 3 ? "pl-6" : "pl-3"}>
            <a
              href={`#${sectionId(item.uid)}`}
              onClick={(e) => {
                e.preventDefault();
                onJump(item.uid);
              }}
              className="block py-0.5 text-muted hover:text-charcoal hover:underline"
            >
              {item.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

// ---- selection toolbar ----------------------------------------------------------------------

/** Appears over a text selection in the lesson: highlight in a colour, or add a note. */
export function SelectionToolbar({ selection, onHighlight, onNote, onDismiss }) {
  if (!selection) return null;
  if (selection.error) {
    return (
      <div
        role="status"
        className="fixed inset-x-4 bottom-4 z-40 mx-auto max-w-md rounded-2xl bg-charcoal px-4 py-3 text-sm text-ivory shadow-lift"
      >
        {selection.error}
      </div>
    );
  }
  const rect = selection.rect;
  const desktop = typeof window !== "undefined" && window.innerWidth >= 640 && rect;
  const style = desktop
    ? {
        top: Math.max(8, rect.top - 56),
        left: Math.min(Math.max(8, rect.left + rect.width / 2 - 150), window.innerWidth - 308),
      }
    : undefined;
  return (
    <div
      role="toolbar"
      aria-label="Study tools for the selected text"
      style={style}
      className={`z-40 flex items-center gap-1 rounded-full border border-charcoal/10 bg-white p-1.5 shadow-lift ${
        desktop ? "fixed w-[300px]" : "fixed inset-x-4 bottom-4 mx-auto max-w-sm justify-center"
      }`}
      onMouseDown={(e) => e.preventDefault()}
      onKeyDown={(e) => e.key === "Escape" && onDismiss()}
    >
      <Highlighter aria-hidden className="mx-1 size-4 text-muted" />
      {COLORS.map((color) => (
        <button
          key={color}
          type="button"
          onClick={() => onHighlight(color)}
          aria-label={`Highlight in ${COLOR_LABELS[color].toLowerCase()}`}
          className={`size-9 rounded-full border-2 border-white ring-1 ring-charcoal/20 ${SWATCH[color]} hover:ring-charcoal/60`}
        />
      ))}
      <button
        type="button"
        onClick={onNote}
        className="ml-1 inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium hover:bg-cream"
      >
        <StickyNote aria-hidden className="size-4" /> Add note
      </button>
    </div>
  );
}

// ---- study panel: bookmark, highlights, notes --------------------------------------------------

function SaveStatus({ status }) {
  return (
    <span
      role="status"
      className={`text-xs ${status.state === "error" ? "text-red-800" : "text-muted"}`}
    >
      {status.message}
    </span>
  );
}

function Quote({ anchor, color }) {
  if (!anchor) return null;
  if (anchor.hidden) {
    return (
      <p className="text-sm text-muted italic">Excerpt hidden while you can't open this course.</p>
    );
  }
  return (
    <blockquote
      className={`border-l-4 pl-3 text-sm text-ink ${color ? BORDER[color] : "border-gold-400"}`}
    >
      “{anchor.quote}”
      {anchor.status === "orphaned" && (
        <span className="mt-1 block text-xs text-muted not-italic">
          Saved excerpt — this passage changed in a later version of the lesson.
        </span>
      )}
    </blockquote>
  );
}

function NoteItem({ note, onSave, onDelete, onJump }) {
  const id = useId();
  const [body, setBody] = useState(note.body);
  const [confirm, setConfirm] = useState(false);
  const { status, schedule } = useAutosave((value) => onSave(note.id, value));
  return (
    <li className="rounded-xl border border-charcoal/10 bg-white p-3">
      {note.anchor && (
        <div className="mb-2">
          <Quote anchor={note.anchor} />
          {note.anchor.status !== "orphaned" && !note.anchor.hidden && onJump && (
            <button
              type="button"
              onClick={() => onJump(note.anchor)}
              className="mt-1 text-xs font-medium text-sage-800 underline underline-offset-4"
            >
              Show in lesson
            </button>
          )}
        </div>
      )}
      <label htmlFor={`${id}-body`} className="sr-only">
        Note
      </label>
      <textarea
        id={`${id}-body`}
        value={body}
        rows={3}
        maxLength={10000}
        onChange={(e) => {
          setBody(e.target.value);
          if (e.target.value.trim()) schedule(e.target.value);
        }}
        className="w-full rounded-lg border border-charcoal/15 bg-white p-2 text-sm"
      />
      <div className="mt-1 flex items-center justify-between gap-2">
        <SaveStatus status={status} />
        {confirm ? (
          <span className="flex items-center gap-2 text-sm">
            Delete this note?
            <button
              type="button"
              className="font-medium text-red-800 underline"
              onClick={() => onDelete(note.id)}
            >
              Delete
            </button>
            <button type="button" className="underline" onClick={() => setConfirm(false)}>
              Keep
            </button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => setConfirm(true)}
            aria-label="Delete note"
            className="grid size-9 place-items-center rounded-full text-muted hover:bg-cream hover:text-red-800"
          >
            <Trash2 aria-hidden className="size-4" />
          </button>
        )}
      </div>
    </li>
  );
}

function NewNote({ draftAnchor, onCreate, onSave, onClearAnchor }) {
  const id = useId();
  const [body, setBody] = useState("");
  const created = useRef(null);
  const [createdId, setCreatedId] = useState(null);
  const anchorRef = useRef(draftAnchor);
  useEffect(() => {
    anchorRef.current = draftAnchor;
  });
  const { status, schedule } = useAutosave(async (value) => {
    if (created.current) return onSave(created.current, value);
    const note = await onCreate(value, anchorRef.current);
    created.current = note.id;
    setCreatedId(note.id);
    return note;
  });
  const textareaRef = useRef(null);
  useEffect(() => {
    if (draftAnchor) textareaRef.current?.focus();
  }, [draftAnchor]);
  const reset = () => {
    created.current = null;
    setCreatedId(null);
    setBody("");
    onClearAnchor();
  };
  return (
    <div className="rounded-xl border border-dashed border-charcoal/20 p-3">
      {draftAnchor && (
        <div className="mb-2">
          <Quote anchor={draftAnchor} />
        </div>
      )}
      <label htmlFor={`${id}-new`} className="text-sm font-medium">
        {draftAnchor ? "Note on this passage" : "New note on this lesson"}
      </label>
      <textarea
        id={`${id}-new`}
        ref={textareaRef}
        value={body}
        rows={3}
        maxLength={10000}
        placeholder="Write a private note… it saves automatically."
        onChange={(e) => {
          setBody(e.target.value);
          if (e.target.value.trim()) schedule(e.target.value);
        }}
        className="mt-1 w-full rounded-lg border border-charcoal/15 bg-white p-2 text-sm"
      />
      <div className="mt-1 flex items-center justify-between">
        <SaveStatus status={status} />
        {createdId && status.state === "saved" && (
          <button
            type="button"
            onClick={reset}
            className="text-sm font-medium underline underline-offset-4"
          >
            Start another note
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Side panel with this lesson's private study tools. Non-modal: the lesson stays
 * readable and focus returns to the toggle when it closes.
 */
export function StudyPanel({
  open,
  onClose,
  study,
  draftAnchor,
  onClearAnchor,
  onCreateNote,
  onSaveNote,
  onDeleteNote,
  onRecolor,
  onRemoveHighlight,
  onJump,
  highlightsSupported,
  panelId,
}) {
  const headingRef = useRef(null);
  useEffect(() => {
    // A note on a selected passage focuses its text box instead (see NewNote).
    if (open && !draftAnchor) headingRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  if (!open) return null;
  const current = study.highlights.filter((h) => h.status !== "orphaned");
  const orphaned = study.highlights.filter((h) => h.status === "orphaned");
  return (
    <aside
      id={panelId}
      aria-labelledby={`${panelId}-title`}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-sm flex-col border-l border-charcoal/10 bg-ivory text-base text-ink shadow-lift"
    >
      <div className="flex items-center justify-between border-b border-charcoal/10 px-4 py-3">
        <h2
          id={`${panelId}-title`}
          ref={headingRef}
          tabIndex={-1}
          className="flex items-center gap-2 font-sans text-lg font-semibold"
        >
          <NotebookPen aria-hidden className="size-5" /> Notes &amp; highlights
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close notes and highlights"
          className="grid size-10 place-items-center rounded-full hover:bg-cream"
        >
          <X aria-hidden className="size-5" />
        </button>
      </div>
      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-4">
        <section aria-labelledby={`${panelId}-notes`}>
          <h3 id={`${panelId}-notes`} className="font-sans text-base font-semibold">
            Notes ({study.notes.length})
          </h3>
          <div className="mt-2">
            <NewNote
              key={draftAnchor ? `${draftAnchor.block}:${draftAnchor.start}` : "lesson"}
              draftAnchor={draftAnchor}
              onCreate={onCreateNote}
              onSave={onSaveNote}
              onClearAnchor={onClearAnchor}
            />
          </div>
          <ul className="mt-3 space-y-3">
            {study.notes.map((note) => (
              <NoteItem
                key={note.id}
                note={note}
                onSave={onSaveNote}
                onDelete={onDeleteNote}
                onJump={onJump}
              />
            ))}
          </ul>
        </section>
        <section aria-labelledby={`${panelId}-highlights`}>
          <h3 id={`${panelId}-highlights`} className="font-sans text-base font-semibold">
            Highlights ({study.highlights.length})
          </h3>
          {!highlightsSupported && study.highlights.length > 0 && (
            <p className="mt-1 text-xs text-muted">
              Your browser can't colour highlights inside the text; they're listed here.
            </p>
          )}
          {study.highlights.length === 0 && (
            <p className="mt-1 text-sm text-muted">
              Select text in the lesson and choose a colour to highlight it.
            </p>
          )}
          <ul className="mt-2 space-y-3">
            {[...current, ...orphaned].map((item) => (
              <li key={item.id} className="rounded-xl border border-charcoal/10 bg-white p-3">
                <Quote anchor={{ ...item.anchor, status: item.status }} color={item.color} />
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                  {item.status !== "orphaned" && (
                    <button
                      type="button"
                      onClick={() => onJump(item.anchor, item.id)}
                      className="font-medium text-sage-800 underline underline-offset-4"
                    >
                      Show in lesson
                    </button>
                  )}
                  <label className="sr-only" htmlFor={`${item.id}-color`}>
                    Highlight colour
                  </label>
                  <select
                    id={`${item.id}-color`}
                    value={item.color}
                    onChange={(e) => onRecolor(item.id, e.target.value)}
                    className="rounded-lg border border-charcoal/15 bg-white px-2 py-1"
                  >
                    {COLORS.map((c) => (
                      <option key={c} value={c}>
                        {COLOR_LABELS[c]}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => onRemoveHighlight(item.id)}
                    className="ml-auto text-muted underline underline-offset-4 hover:text-red-800"
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
        <p className="text-sm">
          <Link to={routes.notebook} className="font-medium underline underline-offset-4">
            Open your study notebook
          </Link>{" "}
          <span className="text-muted">— every course, search and export.</span>
        </p>
      </div>
    </aside>
  );
}

export function BookmarkButton({ bookmarked, busy, onToggle }) {
  return (
    <Button
      variant="outline"
      size="sm"
      aria-pressed={bookmarked}
      disabled={busy}
      onClick={onToggle}
    >
      {bookmarked ? (
        <BookmarkCheck aria-hidden className="size-4" />
      ) : (
        <Bookmark aria-hidden className="size-4" />
      )}
      {bookmarked ? "Saved" : "Save lesson"}
    </Button>
  );
}

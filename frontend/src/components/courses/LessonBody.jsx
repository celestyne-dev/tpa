import { BookMarked, Download, FileText, Lightbulb, PenLine } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { Button } from "@/components/ui/Button";
import { formatBytes } from "@/utils/format";

const LESSON_TYPES = new Set([
  "key_points",
  "example",
  "exercise",
  "checklist",
  "download",
  "further_reading",
]);

function KeyPoints({ block }) {
  return (
    <aside className="my-8 rounded-2xl border-l-4 border-sage-600 bg-sage-50 p-5">
      <p className="flex items-center gap-2 font-semibold">
        <Lightbulb aria-hidden className="size-5 text-sage-700" />
        {block.title || "Key points"}
      </p>
      <ul className="mt-3 list-disc space-y-1.5 pl-6">
        {block.items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </aside>
  );
}

function Example({ block }) {
  return (
    <section className="my-8 rounded-2xl border border-charcoal/10 bg-cream p-5">
      <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
        {block.variant === "case_study" ? "Case study" : "Example"}
      </p>
      <h3 className="mt-1 text-lg font-medium">{block.title}</h3>
      <p className="mt-2 whitespace-pre-line">{block.text}</p>
    </section>
  );
}

function Checklist({ block }) {
  // Ticks are a reading aid only (kept on this page); nothing is stored or graded.
  const [ticked, setTicked] = useState(() => new Set());
  const toggle = (item) =>
    setTicked((prev) => {
      const next = new Set(prev);
      if (next.has(item)) next.delete(item);
      else next.add(item);
      return next;
    });
  return (
    <fieldset className="my-8 rounded-2xl border border-charcoal/10 bg-white p-5">
      <legend className="px-1 font-semibold">{block.title || "Checklist"}</legend>
      <ul className="mt-2 space-y-2">
        {block.items.map((item) => (
          <li key={item}>
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                className="mt-1 size-5 accent-sage-700"
                checked={ticked.has(item)}
                onChange={() => toggle(item)}
              />
              <span className={ticked.has(item) ? "text-muted line-through" : undefined}>
                {item}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

function Exercise({ block, state, onSave }) {
  const id = useId();
  const savedResponse = state?.responses?.[block.id] ?? "";
  const done = state?.acknowledged?.includes(block.id) ?? false;
  const [response, setResponse] = useState(savedResponse);
  const [status, setStatus] = useState({ busy: false, message: "" });
  const save = async (patch) => {
    if (!onSave) return;
    setStatus({ busy: true, message: "" });
    try {
      await onSave(block.id, patch);
      setStatus({ busy: false, message: "Saved." });
    } catch (error) {
      setStatus({ busy: false, message: error.message });
    }
  };
  return (
    <section
      aria-labelledby={`${id}-title`}
      className="my-8 rounded-2xl border-2 border-gold-300 bg-gold-100/30 p-5"
    >
      <h3 id={`${id}-title`} className="flex items-center gap-2 text-lg font-medium">
        <PenLine aria-hidden className="size-5 text-gold-700" />
        {block.title || "Exercise"}
        {block.required && (
          <span className="rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-gold-700">
            Required
          </span>
        )}
      </h3>
      <p className="mt-2 whitespace-pre-line">{block.prompt}</p>
      {onSave ? (
        <div className="mt-4 space-y-3">
          {block.allow_response !== false && (
            <div>
              <label htmlFor={`${id}-answer`} className="text-sm font-medium">
                Your notes (private)
              </label>
              <textarea
                id={`${id}-answer`}
                rows={4}
                maxLength={5000}
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                className="mt-1 w-full rounded-xl border border-charcoal/15 bg-white p-3"
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            {block.allow_response !== false && (
              <Button
                size="sm"
                variant="outline"
                disabled={status.busy || response === savedResponse}
                onClick={() => save({ response })}
              >
                Save notes
              </Button>
            )}
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                className="size-5 accent-sage-700"
                checked={done}
                disabled={status.busy}
                onChange={(e) =>
                  save({
                    done: e.target.checked,
                    ...(block.allow_response !== false && { response }),
                  })
                }
              />
              I've done this exercise
            </label>
            <span role="status" className="text-sm text-muted">
              {status.message}
            </span>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted">Enrol to save your answer and progress.</p>
      )}
    </section>
  );
}

function DownloadBlock({ block, onDownload }) {
  const [state, setState] = useState({ busy: false, error: "" });
  const file = block.file;
  if (!file) return null;
  const go = async () => {
    setState({ busy: true, error: "" });
    try {
      await onDownload(file);
      setState({ busy: false, error: "" });
    } catch (error) {
      setState({ busy: false, error: error.message });
    }
  };
  return (
    <div className="my-8 flex flex-col gap-3 rounded-2xl border border-charcoal/10 bg-white p-5 sm:flex-row sm:items-center">
      <FileText aria-hidden className="size-8 shrink-0 text-sage-700" />
      <div className="flex-1">
        <p className="font-medium">{block.title || file.title}</p>
        {block.description && <p className="text-sm text-muted">{block.description}</p>}
        <p className="text-sm text-muted">
          {file.format} · {formatBytes(file.size_bytes)}
        </p>
        {state.error && (
          <p role="alert" className="mt-1 text-sm text-red-800">
            {state.error}
          </p>
        )}
      </div>
      <Button size="sm" onClick={go} disabled={state.busy}>
        <Download aria-hidden className="size-4" />
        {state.busy ? "Preparing…" : "Download"}
      </Button>
    </div>
  );
}

function FurtherReading({ block }) {
  return (
    <section className="my-8">
      <h3 className="flex items-center gap-2 text-lg font-medium">
        <BookMarked aria-hidden className="size-5 text-sage-700" />
        {block.title || "Further reading"}
      </h3>
      <ul className="mt-3 space-y-2">
        {block.items.map((item) => (
          <li key={item.href}>
            {item.href.startsWith("/") ? (
              <Link to={item.href} className="font-medium underline underline-offset-4">
                {item.label}
              </Link>
            ) : (
              <a
                href={item.href}
                rel="noopener noreferrer"
                className="font-medium underline underline-offset-4"
              >
                {item.label}
              </a>
            )}
            {item.note && <span className="text-muted"> — {item.note}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Lesson content: article blocks (text, images, tables) plus the written-learning blocks.
 * ``onSaveExercise`` and ``onDownload`` are only given to enrolled learners.
 */
export function LessonBody({ blocks, state, onSaveExercise, onDownload }) {
  const groups = [];
  for (const block of blocks) {
    const last = groups[groups.length - 1];
    if (!LESSON_TYPES.has(block.type) && last?.article) last.blocks.push(block);
    else if (!LESSON_TYPES.has(block.type)) groups.push({ article: true, blocks: [block] });
    else groups.push({ article: false, block });
  }
  return (
    <div className="lesson-body">
      {groups.map((group, index) => {
        if (group.article) return <ArticleBody key={index} blocks={group.blocks} />;
        const { block } = group;
        switch (block.type) {
          case "key_points":
            return <KeyPoints key={index} block={block} />;
          case "example":
            return <Example key={index} block={block} />;
          case "exercise":
            return <Exercise key={block.id} block={block} state={state} onSave={onSaveExercise} />;
          case "checklist":
            return <Checklist key={index} block={block} />;
          case "download":
            return onDownload ? (
              <DownloadBlock key={index} block={block} onDownload={onDownload} />
            ) : null;
          case "further_reading":
            return <FurtherReading key={index} block={block} />;
          default:
            return null;
        }
      })}
    </div>
  );
}

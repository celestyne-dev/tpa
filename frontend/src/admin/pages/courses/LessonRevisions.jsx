import { useEffect, useState } from "react";
import { LessonBody } from "@/components/courses/LessonBody";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../../adminApiContext";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";

const when = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "";

const ACTIONS = {
  published: "Published",
  restored: "Restored and published",
  migrated: "Original",
};
const FIELD_LABELS = {
  title: "Title",
  summary: "Summary",
  estimated_minutes: "Estimated time",
  is_preview: "Free preview",
  completion_required: "Required for completion",
};
const show = (value) =>
  value === true ? "Yes" : value === false ? "No" : value === null || value === "" ? "—" : value;

/** A private preview of the draft as learners will read it (nothing here is public). */
export function DraftPreviewDialog({ open, lesson, onClose }) {
  return (
    <Modal open={open} size="lg" title={`Draft preview: ${lesson.title}`} onClose={onClose}>
      <p className="mb-4 rounded-xl bg-gold-100 px-3 py-2 text-sm">
        Private preview of unpublished changes. Learners still read the live version until you
        publish.
      </p>
      <article className="mx-auto max-w-[68ch]">
        <h1 className="text-3xl font-medium">{lesson.title}</h1>
        {lesson.summary && <p className="mt-2 text-muted">{lesson.summary}</p>}
        <div className="mt-6">
          <LessonBody blocks={lesson.preview_body ?? []} />
        </div>
      </article>
    </Modal>
  );
}

function Diff({ diff }) {
  if (diff.identical) return <p className="text-muted">These versions are identical.</p>;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        {diff.counts.added} added · {diff.counts.removed} removed · {diff.counts.changed} changed
        blocks
      </p>
      {diff.fields.length > 0 && (
        <table className="w-full text-sm">
          <caption className="sr-only">Changed settings</caption>
          <thead>
            <tr className="text-left text-muted">
              <th scope="col">Setting</th>
              <th scope="col">{diff.left.label}</th>
              <th scope="col">{diff.right.label}</th>
            </tr>
          </thead>
          <tbody>
            {diff.fields.map((f) => (
              <tr key={f.field} className="border-t border-charcoal/10 align-top">
                <th scope="row" className="py-1.5 pr-3 font-medium">
                  {FIELD_LABELS[f.field] ?? f.field}
                </th>
                <td className="py-1.5 pr-3">{show(f.before)}</td>
                <td className="py-1.5">{show(f.after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <ol className="space-y-2">
        {diff.blocks
          .filter((b) => b.status !== "unchanged")
          .map((b, i) => (
            <li
              key={i}
              className={`rounded-xl border p-3 text-sm ${
                b.status === "added"
                  ? "border-sage-300 bg-sage-50"
                  : b.status === "removed"
                    ? "border-red-200 bg-red-50"
                    : "border-gold-300 bg-gold-100/40"
              }`}
            >
              <p className="text-xs font-semibold tracking-wide uppercase">
                {b.status} · {b.type?.replace("_", " ")}
              </p>
              {b.status === "changed" ? (
                <>
                  <p className="mt-1">
                    <span className="font-medium">Before: </span>
                    <del>{b.before}</del>
                  </p>
                  <p className="mt-1">
                    <span className="font-medium">After: </span>
                    <ins className="no-underline">{b.after}</ins>
                  </p>
                </>
              ) : (
                <p className="mt-1">{b.status === "added" ? b.after : <del>{b.before}</del>}</p>
              )}
            </li>
          ))}
      </ol>
    </div>
  );
}

/**
 * Revision history: every published version, comparisons between any two versions (or
 * the draft), and restoring an earlier version into the draft (optionally publishing).
 */
export function RevisionsDialog({ open, course, lesson, onClose, onRestored }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [items, setItems] = useState(null);
  const [left, setLeft] = useState("live");
  const [right, setRight] = useState("draft");
  const [diff, setDiff] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const can = course.can;

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    api.courses.lessonRevisions(course.id, lesson.id).then(
      (res) => live && setItems(res.data),
      (err) => live && setError(err.message),
    );
    return () => {
      live = false;
    };
  }, [api, open, course.id, lesson.id]);

  const options = [
    ...(can.view_drafts ? [{ value: "draft", label: "Current draft" }] : []),
    ...(lesson.live ? [{ value: "live", label: `Live (revision ${lesson.live.revision})` }] : []),
    ...(items ?? []).map((r) => ({ value: String(r.number), label: `Revision ${r.number}` })),
  ];
  const compare = async () => {
    setError("");
    try {
      const res = await api.courses.compareLesson(course.id, lesson.id, left, right);
      setDiff(res.data);
    } catch (err) {
      setError(err.message);
    }
  };
  const restore = async (number, publish) => {
    setBusy(true);
    try {
      const res = await api.courses.restoreRevision(course.id, lesson.id, number, {
        lock_version: lesson.lock_version,
        publish,
      });
      notify(
        publish
          ? `Revision ${number} restored and published.`
          : `Revision ${number} copied into the draft.`,
      );
      onRestored(res.data);
      onClose();
    } catch (err) {
      setError(
        err.code === "edit_conflict"
          ? "The lesson changed meanwhile. Reload it first."
          : err.message,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} size="lg" title={`Revisions: ${lesson.title}`} onClose={onClose}>
      {error && (
        <p role="alert" className="mb-3 rounded-xl bg-red-50 p-3 text-sm">
          {error}
        </p>
      )}
      <section aria-labelledby="compare-heading" className="rounded-xl bg-cream/60 p-4">
        <h3 id="compare-heading" className="font-medium">
          Compare versions
        </h3>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          {[
            ["From", left, setLeft],
            ["To", right, setRight],
          ].map(([label, value, setter]) => (
            <label key={label} className="text-sm">
              <span className="block font-medium">{label}</span>
              <select
                value={value}
                onChange={(e) => setter(e.target.value)}
                className="mt-1 rounded-lg border border-charcoal/15 bg-white px-2 py-1.5"
              >
                {options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <Button size="sm" variant="outline" onClick={compare} disabled={left === right}>
            Compare
          </Button>
        </div>
        {diff && (
          <div className="mt-4" aria-live="polite">
            <Diff diff={diff} />
          </div>
        )}
      </section>
      <h3 className="mt-6 font-medium">History</h3>
      {!items ? (
        <p role="status">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">This lesson hasn't been published yet.</p>
      ) : (
        <ol className="mt-2 divide-y divide-charcoal/10">
          {items.map((r) => (
            <li key={r.number} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>
                <span className="font-medium">Revision {r.number}</span>
                {r.live && (
                  <span className="ml-2 rounded-full bg-sage-100 px-2 py-0.5 text-xs">Live</span>
                )}
                <span className="block text-sm text-muted">
                  {ACTIONS[r.action] ?? r.action} {when(r.created_at)}
                  {r.created_by ? ` by ${r.created_by}` : ""}
                  {r.restored_from ? ` (from revision ${r.restored_from})` : ""}
                  {r.note ? ` — ${r.note}` : ""}
                </span>
              </span>
              {can.restore_revisions && !r.live && (
                <span className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => restore(r.number, false)}
                  >
                    Restore to draft
                  </Button>
                  {can.publish_lessons && (
                    <Button size="sm" disabled={busy} onClick={() => restore(r.number, true)}>
                      Restore and publish
                    </Button>
                  )}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}

export function PublishDialog({ open, lesson, onClose, onPublish }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const firstTime = !lesson.live;
  return (
    <Modal
      open={open}
      size="sm"
      title={firstTime ? "Publish lesson" : "Publish lesson changes"}
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onPublish(note);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Publishing…" : "Publish"}
          </Button>
        </>
      }
    >
      <p className="text-sm text-muted">
        {firstTime
          ? "Learners will be able to read this lesson."
          : "Learners will see the new version straight away. The current live version stays in the history."}
      </p>
      <label className="mt-3 block text-sm font-medium">
        What changed? (optional, kept with the revision)
        <input
          value={note}
          maxLength={300}
          onChange={(e) => setNote(e.target.value)}
          className="mt-1 w-full rounded-lg border border-charcoal/15 bg-white px-3 py-2"
        />
      </label>
    </Modal>
  );
}

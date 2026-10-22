import { GitCompareArrows, History, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { ConfirmDialog } from "./ConfirmDialog";

const KIND_LABELS = {
  manual: "Saved",
  autosave: "Autosave",
  restore: "Restored",
  publish: "Published",
  system: "System",
};

const show = (value) => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  return String(value);
};

/** Revision history with compare and restore. */
export function RevisionsPanel({ articleId, canRestore, lockVersion, onRestored, refreshKey }) {
  const api = useAdminApi();
  const list = useAdminQuery(() => api.articles.revisions(articleId), [articleId, refreshKey]);
  const [selected, setSelected] = useState([]);
  const [diff, setDiff] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const toggle = (id) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id].slice(-2),
    );

  const compare = async () => {
    setError(null);
    try {
      const [a, b] = selected;
      const res = await api.articles.compareRevisions(articleId, a, b);
      setDiff(res.data);
    } catch (err) {
      setError(err.message);
    }
  };

  const restore = async () => {
    setBusy(true);
    try {
      const res = await api.articles.restoreRevision(articleId, confirm.id, lockVersion);
      onRestored?.(res);
      setConfirm(null);
      list.reload();
    } catch (err) {
      setError(err.message);
      setConfirm(null);
    } finally {
      setBusy(false);
    }
  };

  if (list.loading && !list.data) return <Skeleton className="h-40 w-full" />;
  if (list.error)
    return (
      <p role="alert" className="text-sm text-red-800">
        {list.error.message}
      </p>
    );
  if (!list.data?.length)
    return <EmptyState icon={History} title="No revisions yet" description="Saves appear here." />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Select two revisions to compare. Autosaves are combined so the history stays readable.
        </p>
        <Button size="sm" variant="outline" disabled={selected.length !== 2} onClick={compare}>
          <GitCompareArrows aria-hidden />
          Compare selected
        </Button>
      </div>
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
          {error}
        </p>
      )}
      <ol className="divide-y divide-charcoal/5 rounded-xl border border-charcoal/10 bg-white">
        {list.data.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
            <input
              type="checkbox"
              className="accent-sage-700"
              aria-label={`Select revision ${r.number}`}
              checked={selected.includes(r.id)}
              onChange={() => toggle(r.id)}
            />
            <span className="w-10 font-mono text-xs text-muted">#{r.number}</span>
            <span className="min-w-0 flex-1">
              <span className="font-medium">{r.summary || KIND_LABELS[r.kind]}</span>
              <span className="block text-xs text-muted">
                {KIND_LABELS[r.kind]} · {r.editor?.display_name ?? "System"} ·{" "}
                <time dateTime={r.updated_at}>{formatDateTime(r.updated_at)}</time>
              </span>
            </span>
            {canRestore && r.id !== list.data[0].id && (
              <Button size="sm" variant="ghost" onClick={() => setConfirm(r)}>
                <RotateCcw aria-hidden />
                Restore
              </Button>
            )}
          </li>
        ))}
      </ol>

      {diff && (
        <section
          aria-label="Revision comparison"
          className="rounded-xl border border-charcoal/10 bg-white p-4 text-sm"
        >
          <h3 className="font-sans font-semibold">
            Changes from #{diff.from.number} to #{diff.to.number}
          </h3>
          {diff.fields.length === 0 && diff.blocks.length === 0 && (
            <p className="mt-2 text-muted">No differences.</p>
          )}
          {diff.fields.length > 0 && (
            <table className="mt-3 w-full table-fixed text-left text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="w-1/5 font-normal">Field</th>
                  <th className="font-normal">Before</th>
                  <th className="font-normal">After</th>
                </tr>
              </thead>
              <tbody>
                {diff.fields.map((f) => (
                  <tr key={f.field} className="align-top">
                    <td className="py-1 font-medium">{f.label}</td>
                    <td className="py-1 break-words text-red-900">{show(f.from)}</td>
                    <td className="text-sage-900 py-1 break-words">{show(f.to)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {diff.blocks.length > 0 && (
            <ul className="mt-3 space-y-1">
              {diff.blocks.map((b) => (
                <li key={b.index}>
                  <span className="font-medium">Block {b.index + 1}</span> {b.change}:{" "}
                  {b.change === "added"
                    ? b.to
                    : b.change === "removed"
                      ? b.from
                      : `${b.from} → ${b.to}`}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <ConfirmDialog
        open={Boolean(confirm)}
        title={`Restore revision #${confirm?.number}?`}
        message="Its content becomes the current draft. For a published article it is saved as unpublished changes until a publisher publishes them. Nothing is lost: the current version stays in the history."
        confirmLabel="Restore revision"
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={restore}
      />
    </div>
  );
}

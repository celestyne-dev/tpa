import { Ban, Hammer, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { SelectField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const REASONS = {
  article_published: "Article published",
  published_article_updated: "Published article changed",
  article_unpublished: "Article unpublished",
  article_archived: "Article archived",
  scheduled_published: "Scheduled article went live",
  media_updated: "Image details changed",
  media_replaced: "Image replaced",
  manual_request: "Manual rebuild",
  redirect_created: "Redirect added",
  redirect_updated: "Redirect changed",
  redirect_deleted: "Redirect removed",
  slug_redirect: "Slug changed",
};
const reason = (r) => REASONS[r] ?? r.replaceAll("_", " ");

/** Static site builds: queue, history, retries. Builds run in a separate worker process. */
export function PublishingPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const canManage = can("publishing.manage");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [log, setLog] = useState(null);
  const [busy, setBusy] = useState(false);
  const jobs = useAdminQuery(
    () => api.publishing.jobs({ status: status || undefined, page, page_size: 20 }),
    [status, page],
  );
  const summary = jobs.meta?.summary;

  const act = async (fn, message) => {
    setBusy(true);
    try {
      await fn();
      notify(message);
      jobs.reload();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Publishing jobs"
        description="CMS changes that affect public pages queue a site rebuild. The publishing worker builds the site and switches it live only after a successful, verified build."
        breadcrumbs={[{ label: "Publishing jobs" }]}
        actions={
          canManage && (
            <Button
              size="sm"
              disabled={busy}
              onClick={() => act(() => api.publishing.request(), "Rebuild queued.")}
            >
              <Hammer aria-hidden />
              Rebuild now
            </Button>
          )
        }
      />
      {summary && (
        <section aria-label="Current state" className="mb-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-charcoal/10 bg-white p-4 text-sm">
            <p className="text-xs tracking-wide text-muted uppercase">Live release</p>
            <p className="mt-1 font-medium">
              {summary.last_success
                ? `${summary.last_success.release} · ${formatDateTime(summary.last_success.finished_at)}`
                : "No successful build recorded yet"}
            </p>
          </div>
          <div className="rounded-xl border border-charcoal/10 bg-white p-4 text-sm">
            <p className="text-xs tracking-wide text-muted uppercase">Queue</p>
            <p className="mt-1 font-medium">
              {summary.running
                ? `Building job #${summary.running.id}…`
                : summary.pending
                  ? `Job #${summary.pending.id} waiting (starts after ${formatDateTime(summary.pending.not_before)})`
                  : "Idle"}
            </p>
          </div>
          <div className="rounded-xl border border-charcoal/10 bg-white p-4 text-sm">
            <p className="text-xs tracking-wide text-muted uppercase">Last failure</p>
            <p className="mt-1 font-medium">
              {summary.last_failure
                ? `#${summary.last_failure.id}: ${summary.last_failure.error}`
                : "None since the last success"}
            </p>
          </div>
        </section>
      )}
      <div className="mb-4 max-w-xs">
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          options={[
            { value: "", label: "All jobs" },
            { value: "pending", label: "Pending" },
            { value: "running", label: "Running" },
            { value: "succeeded", label: "Succeeded" },
            { value: "failed", label: "Failed" },
            { value: "cancelled", label: "Cancelled" },
          ]}
        />
      </div>
      {jobs.error ? (
        <ErrorState title="We couldn't load publishing jobs" onRetry={jobs.reload} />
      ) : (
        <DataTable
          caption="Publishing jobs"
          rows={jobs.data}
          loading={jobs.loading}
          empty={{ title: "No publishing jobs yet" }}
          columns={[
            { key: "id", header: "Job", render: (j) => `#${j.id}` },
            {
              key: "status",
              header: "Status",
              render: (j) => (
                <StatusBadge status={j.status === "succeeded" ? "published" : j.status} />
              ),
            },
            {
              key: "reasons",
              header: "Why",
              render: (j) => (
                <span className="text-xs">
                  {j.reasons.slice(0, 3).map(reason).join(", ")}
                  {j.reasons.length > 3 && ` +${j.reasons.length - 3}`}
                </span>
              ),
            },
            { key: "created", header: "Queued", render: (j) => formatDateTime(j.created_at) },
            {
              key: "duration",
              header: "Duration",
              render: (j) => (j.duration_seconds != null ? `${j.duration_seconds}s` : "—"),
            },
            {
              key: "attempts",
              header: "Attempts",
              render: (j) => `${j.attempts}/${j.max_attempts}`,
            },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              className: "text-right",
              render: (j) => (
                <span className="flex justify-end gap-1">
                  {(j.log_tail || j.error) && (
                    <Button size="sm" variant="ghost" onClick={() => setLog(j)}>
                      Details
                    </Button>
                  )}
                  {canManage && ["failed", "cancelled"].includes(j.status) && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => act(() => api.publishing.retry(j.id), "Retry queued.")}
                    >
                      <RotateCcw aria-hidden />
                      Retry
                    </Button>
                  )}
                  {canManage && j.status === "pending" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => act(() => api.publishing.cancel(j.id), "Job cancelled.")}
                    >
                      <Ban aria-hidden />
                      Cancel
                    </Button>
                  )}
                </span>
              ),
            },
          ]}
        />
      )}
      <Pagination pagination={jobs.meta?.pagination} onPage={setPage} />
      <Modal open={Boolean(log)} onClose={() => setLog(null)} title={`Job #${log?.id}`} size="lg">
        {log && (
          <div className="space-y-3 text-sm">
            {log.error && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-red-900">
                {log.error}
              </p>
            )}
            {log.release && <p>Release: {log.release}</p>}
            {log.log_tail && (
              <pre className="max-h-80 overflow-auto rounded-lg bg-charcoal p-3 text-xs whitespace-pre-wrap text-ivory">
                {log.log_tail}
              </pre>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}

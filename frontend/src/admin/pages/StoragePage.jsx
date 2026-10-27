import { AlertTriangle, CheckCircle2, HardDrive, Info, RefreshCw, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { cn, formatBytes, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { useAdminQuery } from "../hooks/useAdminQuery";

const LEVEL = {
  critical: { icon: ShieldAlert, label: "Critical", className: "bg-red-50 text-red-900" },
  warning: { icon: AlertTriangle, label: "Warning", className: "bg-gold-100/70 text-charcoal" },
  info: { icon: Info, label: "Note", className: "bg-sage-50 text-charcoal" },
};
const STATUS_TEXT = {
  ok: "Storage is healthy.",
  warning: "Storage needs attention soon.",
  critical: "Storage has a problem that needs fixing now.",
};

function DiskBar({ disk }) {
  if (!disk) return <span className="text-muted">Unknown</span>;
  const used = 100 - disk.free_percent;
  return (
    <div className="min-w-40">
      <div
        className="h-2 overflow-hidden rounded-full bg-charcoal/10"
        role="meter"
        aria-label="Disk used"
        aria-valuenow={Math.round(used)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={cn(
            "h-full rounded-full",
            disk.free_percent < 5
              ? "bg-red-700"
              : disk.free_percent < 15
                ? "bg-gold-500"
                : "bg-sage-600",
          )}
          style={{ width: `${used}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-muted">
        {formatBytes(disk.free_bytes)} free of {formatBytes(disk.total_bytes)} ({disk.free_percent}
        %)
      </p>
    </div>
  );
}

function BackupCard({ backup }) {
  let text;
  if (!backup.configured)
    text = "Backups aren't monitored here yet (BACKUP_STATUS_FILE is not set).";
  else if (!backup.found) text = "No backup has been recorded yet.";
  else if (!backup.readable) text = "The backup status file can't be read.";
  else
    text = `${backup.ok ? "Last backup succeeded" : "Last backup failed"} ${
      backup.finished_at ? formatDateTime(backup.finished_at) : ""
    }${backup.age_hours != null ? ` (${backup.age_hours} h ago)` : ""}${
      backup.size_bytes ? ` · ${formatBytes(backup.size_bytes)}` : ""
    }${backup.offsite ? " · encrypted copy stored off the server" : ""}${
      backup.verified ? " · verified" : ""
    }.`;
  return (
    <section className="rounded-xl border border-charcoal/10 bg-white p-5">
      <h2 className="text-lg font-medium">Backups</h2>
      <p className="mt-2 text-sm">{text}</p>
      {backup.message && <p className="mt-1 text-sm text-muted">{backup.message}</p>}
    </section>
  );
}

/** Storage health on the VPS: disk space, folders, missing files, upload errors, backups. */
export function StoragePage() {
  const api = useAdminApi();
  const report = useAdminQuery(() => api.storage.health(), []);
  const errors = useAdminQuery(() => api.storage.uploadErrors(), []);
  const data = report.data;
  const reload = () => {
    report.reload();
    errors.reload();
  };

  return (
    <>
      <AdminPageHeader
        title="Storage health"
        description="Images and premium files are stored on this server. This page checks free disk space, folder permissions, missing files and backups."
        breadcrumbs={[{ label: "Storage health" }]}
        actions={
          <Button variant="outline" onClick={reload} disabled={report.loading}>
            <RefreshCw aria-hidden /> Check again
          </Button>
        }
      />
      {report.error ? (
        <ErrorState title="We couldn't check storage" onRetry={reload} />
      ) : !data ? (
        <p role="status" className="text-muted">
          Checking storage…
        </p>
      ) : (
        <div className="space-y-6">
          <div
            role="status"
            className={cn(
              "flex items-center gap-3 rounded-xl p-4 text-sm font-medium",
              data.status === "ok" ? "bg-sage-50" : LEVEL[data.status].className,
            )}
          >
            {data.status === "ok" ? (
              <CheckCircle2 aria-hidden className="size-5 text-sage-700" />
            ) : (
              <AlertTriangle aria-hidden className="size-5" />
            )}
            {STATUS_TEXT[data.status]}
            <span className="ml-auto text-xs font-normal text-muted">
              Checked {formatDateTime(data.generated_at)}
            </span>
          </div>
          {data.warnings.length > 0 && (
            <section aria-labelledby="storage-warnings">
              <h2 id="storage-warnings" className="mb-2 text-lg font-medium">
                Findings
              </h2>
              <ul className="space-y-2">
                {data.warnings.map((w) => {
                  const level = LEVEL[w.level];
                  return (
                    <li
                      key={w.code}
                      className={cn("flex gap-3 rounded-lg p-3 text-sm", level.className)}
                    >
                      <level.icon aria-hidden className="mt-0.5 size-4 shrink-0" />
                      <span>
                        <span className="font-medium">{level.label}: </span>
                        {w.message}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
          <section aria-labelledby="storage-areas">
            <h2 id="storage-areas" className="mb-2 text-lg font-medium">
              Storage areas
            </h2>
            <DataTable
              caption="Storage areas"
              rowKey={(a) => a.key}
              rows={data.areas}
              columns={[
                {
                  key: "label",
                  header: "Area",
                  render: (a) => (
                    <span>
                      <span className="flex items-center gap-2 font-medium">
                        <HardDrive aria-hidden className="size-4 text-sage-700" />
                        {a.label}
                      </span>
                      <span className="block text-xs text-muted">{a.purpose}</span>
                    </span>
                  ),
                },
                {
                  key: "path",
                  header: "Folder",
                  render: (a) => <code className="text-xs break-all">{a.path}</code>,
                },
                {
                  key: "mode",
                  header: "Access",
                  render: (a) =>
                    !a.exists ? (
                      "Missing"
                    ) : (
                      <span>
                        {a.private ? "Private" : "Public"} · {a.mode}
                        {!a.writable && <span className="block text-red-800">Not writable</span>}
                      </span>
                    ),
                },
                { key: "disk", header: "Disk", render: (a) => <DiskBar disk={a.disk} /> },
              ]}
            />
          </section>
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-charcoal/10 bg-white p-5">
              <h2 className="text-lg font-medium">Stored files</h2>
              <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm">
                <dt className="text-muted">Optimised images</dt>
                <dd>{formatBytes(data.tracked.media_variants_bytes)}</dd>
                <dt className="text-muted">Image originals</dt>
                <dd>{formatBytes(data.tracked.media_originals_bytes)}</dd>
                <dt className="text-muted">Replaced images awaiting cleanup</dt>
                <dd>{formatBytes(data.tracked.media_superseded_bytes)}</dd>
                <dt className="text-muted">Premium files</dt>
                <dd>
                  {data.tracked.premium_files} files, {data.tracked.premium_versions} versions ·{" "}
                  {formatBytes(data.tracked.premium_bytes)}
                </dd>
                <dt className="text-muted">Upload limits</dt>
                <dd>
                  Images {data.limits.media_max_mb} MB · premium files {data.limits.premium_max_mb}{" "}
                  MB
                </dd>
                <dt className="text-muted">Premium formats</dt>
                <dd>{data.limits.premium_formats.map((f) => f.toUpperCase()).join(", ")}</dd>
                <dt className="text-muted">Delivery</dt>
                <dd>
                  {data.limits.x_accel_redirect
                    ? "Nginx (internal redirect)"
                    : "Streamed by the application"}
                </dd>
              </dl>
            </section>
            <BackupCard backup={data.backup} />
          </div>
        </div>
      )}
      <section aria-labelledby="upload-errors" className="mt-8">
        <h2 id="upload-errors" className="mb-2 text-lg font-medium">
          Recent upload errors
        </h2>
        {errors.error ? (
          <ErrorState title="We couldn't load upload errors" onRetry={errors.reload} />
        ) : (
          <DataTable
            caption="Recent upload errors"
            loading={errors.loading}
            rows={errors.data}
            empty={{ icon: CheckCircle2, title: "No failed uploads recorded" }}
            columns={[
              { key: "at", header: "When", render: (e) => formatDateTime(e.at) },
              { key: "area", header: "Library", render: (e) => e.area },
              {
                key: "kind",
                header: "Problem",
                render: (e) => (e.kind === "rejected" ? "File refused" : "Storage failure"),
              },
              { key: "filename", header: "File", render: (e) => e.filename || "—" },
              { key: "reason", header: "Reason" },
              { key: "actor", header: "By", render: (e) => e.actor ?? "—" },
            ]}
          />
        )}
      </section>
    </>
  );
}

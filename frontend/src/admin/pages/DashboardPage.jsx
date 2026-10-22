import {
  CalendarClock,
  FileCheck2,
  FilePen,
  FileText,
  FolderTree,
  RefreshCw,
  UserRound,
} from "lucide-react";
import { Link } from "react-router";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

function Stat({ label, value, icon: Icon }) {
  return (
    <div className="min-w-0 rounded-xl border border-charcoal/10 bg-white p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">{label}</p>
        <Icon aria-hidden className="size-4 text-sage-700" />
      </div>
      <p className="mt-2 font-serif text-3xl text-charcoal">{value}</p>
    </div>
  );
}

function PublishingPanel({ publishing }) {
  if (!publishing) return null;
  return (
    <section
      aria-labelledby="publishing-heading"
      className="min-w-0 rounded-xl border border-charcoal/10 bg-white p-5"
    >
      <h2
        id="publishing-heading"
        className="flex items-center gap-2 font-sans text-base font-semibold"
      >
        <RefreshCw aria-hidden className="size-4 text-sage-700" />
        Public site build
      </h2>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted">Last static build</dt>
          <dd>
            {publishing.build_manifest_found
              ? formatDateTime(publishing.last_build_at)
              : "No build found"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Latest public change</dt>
          <dd>{formatDateTime(publishing.latest_public_change_at)}</dd>
        </div>
      </dl>
      {publishing.rebuild_required ? (
        <p className="mt-3 rounded-lg bg-gold-100/70 px-3 py-2 text-sm text-gold-700">
          Published changes are not yet on the static site. Run{" "}
          <code className="font-mono">{publishing.rebuild_command}</code> to rebuild.
        </p>
      ) : (
        <p className="mt-3 text-sm text-muted">
          The static site is up to date with published content.
        </p>
      )}
      {publishing.scheduled_due_count > 0 && (
        <p className="mt-2 text-sm text-gold-700">
          {publishing.scheduled_due_count} scheduled article(s) are due. Run{" "}
          <code className="font-mono">flask --app wsgi content publish-due</code>, then rebuild.
        </p>
      )}
    </section>
  );
}

function AnalyticsPanel() {
  const api = useAdminApi();
  const { data, error } = useAdminQuery(() => api.analytics(), []);
  if (error) return null;
  return (
    <section
      aria-labelledby="analytics-heading"
      className="min-w-0 rounded-xl border border-charcoal/10 bg-white p-5"
    >
      <h2 id="analytics-heading" className="font-sans text-base font-semibold">
        Content insights
      </h2>
      <p className="mt-1 text-sm text-muted">
        {data?.note ?? "Based on published editorial records."}
      </p>
      {data && (
        <div className="mt-3 grid gap-6 sm:grid-cols-2">
          <div>
            <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">
              Published by topic
            </h3>
            {data.published_by_topic.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No published articles yet.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {data.published_by_topic.map((t) => (
                  <li key={t.topic} className="flex justify-between gap-3">
                    <span>{t.topic}</span>
                    <span className="font-medium">{t.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">
              Published by month
            </h3>
            {data.published_by_month.length === 0 ? (
              <p className="mt-2 text-sm text-muted">No published articles yet.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {data.published_by_month.map((m) => (
                  <li key={m.month} className="flex justify-between gap-3">
                    <span>{m.month}</span>
                    <span className="font-medium">{m.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export function DashboardPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const { data, loading, error, reload } = useAdminQuery(() => api.dashboard(), []);

  return (
    <>
      <AdminPageHeader
        title="Dashboard"
        description="An overview of editorial content and recent activity."
      />
      {error && <ErrorState title="We couldn't load the dashboard" onRetry={reload} />}
      {loading && !data && (
        <div role="status" aria-label="Loading dashboard" className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}
      {data && (
        <div className="space-y-8">
          <section aria-label="Content totals" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Stat label="Total articles" value={data.articles.total} icon={FileText} />
            <Stat label="Published" value={data.articles.published} icon={FileCheck2} />
            <Stat label="Drafts" value={data.articles.draft} icon={FilePen} />
            <Stat label="Scheduled" value={data.articles.scheduled} icon={CalendarClock} />
            <Stat label="Topics" value={data.topics_total} icon={FolderTree} />
            <Stat label="Authors" value={data.authors_total} icon={UserRound} />
          </section>

          <PublishingPanel publishing={data.publishing} />
          {can("analytics.view") && <AnalyticsPanel />}

          <div className="grid gap-6 xl:grid-cols-2">
            <section
              aria-labelledby="recent-articles"
              className="min-w-0 rounded-xl border border-charcoal/10 bg-white p-5"
            >
              <h2 id="recent-articles" className="font-sans text-base font-semibold">
                Recent editorial activity
              </h2>
              {data.recent_articles.length === 0 ? (
                <p className="mt-3 text-sm text-muted">
                  No articles yet.{" "}
                  {can("content.write") && (
                    <Link to="/admin/articles/new" className="text-sage-700 underline">
                      Create the first article
                    </Link>
                  )}
                </p>
              ) : (
                <ul className="mt-3 divide-y divide-charcoal/5">
                  {data.recent_articles.map((a) => (
                    <li
                      key={a.id}
                      className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5 text-sm"
                    >
                      <Link
                        to={`/admin/articles/${a.id}/edit`}
                        className="min-w-0 truncate font-medium hover:text-sage-700"
                      >
                        {a.title}
                      </Link>
                      <span className="flex shrink-0 items-center gap-3 text-muted">
                        <StatusBadge status={a.status} />
                        <time dateTime={a.updated_at}>{formatDateTime(a.updated_at)}</time>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {data.recent_audit && (
              <section
                aria-labelledby="recent-audit"
                className="min-w-0 rounded-xl border border-charcoal/10 bg-white p-5"
              >
                <div className="flex items-center justify-between">
                  <h2 id="recent-audit" className="font-sans text-base font-semibold">
                    Recent admin activity
                  </h2>
                  <Link to="/admin/audit-log" className="text-sm text-sage-700 hover:underline">
                    View audit log
                  </Link>
                </div>
                {data.recent_audit.length === 0 ? (
                  <p className="mt-3 text-sm text-muted">No activity recorded yet.</p>
                ) : (
                  <ul className="mt-3 divide-y divide-charcoal/5">
                    {data.recent_audit.map((e) => (
                      <li
                        key={e.id}
                        className="flex flex-wrap justify-between gap-x-3 gap-y-1 py-2.5 text-sm"
                      >
                        <span>
                          <span className="font-mono text-xs">{e.action}</span>
                          <span className="text-muted"> · {e.actor?.display_name ?? "System"}</span>
                        </span>
                        <time dateTime={e.created_at} className="shrink-0 text-muted">
                          {formatDateTime(e.created_at)}
                        </time>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
          </div>
        </div>
      )}
    </>
  );
}

import { Link } from "react-router";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const COLUMNS = [
  { key: "drafts", title: "Drafts", params: { status: "draft", review_status: "none" } },
  { key: "review", title: "Awaiting review", params: { review_status: "submitted" } },
  { key: "approved", title: "Approved", params: { status: "draft", review_status: "approved" } },
  { key: "pending", title: "Unpublished changes", params: { has_pending: true } },
  { key: "scheduled", title: "Scheduled", params: { status: "scheduled" } },
];

function Column({ column }) {
  const api = useAdminApi();
  const { data, meta, loading, error } = useAdminQuery(
    () => api.articles.list({ ...column.params, page: 1, page_size: 20 }),
    [column.key],
  );
  return (
    <section
      aria-labelledby={`wf-${column.key}`}
      className="flex min-w-0 flex-col rounded-xl border border-charcoal/10 bg-white"
    >
      <h2
        id={`wf-${column.key}`}
        className="flex items-center justify-between border-b border-charcoal/10 px-4 py-3 font-sans text-sm font-semibold"
      >
        {column.title}
        <span className="rounded-full bg-beige px-2 text-xs">{meta?.pagination?.total ?? "…"}</span>
      </h2>
      {loading && !data ? (
        <Skeleton className="m-4 h-16" />
      ) : error ? (
        <p className="p-4 text-sm text-red-800">{error.message}</p>
      ) : data?.length ? (
        <ul className="divide-y divide-charcoal/5">
          {data.map((a) => (
            <li key={a.id} className="px-4 py-3 text-sm">
              <Link to={`/admin/articles/${a.id}/edit`} className="font-medium hover:text-sage-700">
                {a.title}
              </Link>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                <StatusBadge status={a.status} />
                {a.created_by?.display_name && <span>{a.created_by.display_name}</span>}
                <span>
                  {a.status === "scheduled" && a.published_at
                    ? `Goes live ${formatDateTime(a.published_at)}`
                    : `Updated ${formatDateTime(a.updated_at)}`}
                </span>
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="p-4 text-sm text-muted">Nothing here.</p>
      )}
    </section>
  );
}

/** Editorial board: where every article is in the draft → review → publish flow. */
export function WorkflowPage() {
  const { can } = usePermissions();
  return (
    <>
      <AdminPageHeader
        title="Editorial workflow"
        description={
          can("articles.view")
            ? "Drafts move to review, approval and publication. Writers submit, reviewers approve, publishers publish or schedule."
            : "Your articles and where they are in the review process."
        }
        breadcrumbs={[{ label: "Editorial workflow" }]}
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {COLUMNS.map((c) => (
          <Column key={c.key} column={c} />
        ))}
      </div>
    </>
  );
}

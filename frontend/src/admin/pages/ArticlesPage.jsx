import { FilePlus2, PenSquare } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { contentKind } from "../contentKinds";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { SelectField, TextField } from "../components/Fields";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "scheduled", label: "Scheduled" },
  { value: "published", label: "Published" },
  { value: "archived", label: "Archived" },
];

const REVIEW_LABELS = { submitted: "Awaiting review", approved: "Approved" };
const REVIEW_OPTIONS = [
  { value: "", label: "Any review state" },
  { value: "submitted", label: "Awaiting review" },
  { value: "approved", label: "Approved" },
];

export function ArticlesPage({ contentType = "article" }) {
  const kind = contentKind(contentType);
  const api = useAdminApi();
  const { can } = usePermissions();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const review = params.get("review") ?? "";
  const page = Number(params.get("page") ?? 1) || 1;
  const [search, setSearch] = useState(q);

  const { data, meta, loading, error, reload } = useAdminQuery(
    () =>
      api.articles.list({
        q: q || undefined,
        status: status || undefined,
        review_status: review || undefined,
        content_type: contentType === "article" ? undefined : contentType,
        page,
        page_size: 20,
      }),
    [q, status, review, page, contentType],
  );

  const update = (next) => {
    const merged = { q, status, review, page: 1, ...next };
    const out = new URLSearchParams();
    Object.entries(merged).forEach(([k, v]) => v && !(k === "page" && v === 1) && out.set(k, v));
    setParams(out);
  };

  const columns = [
    {
      key: "title",
      header: "Title",
      render: (a) => (
        <div>
          <Link
            to={`${kind.base}/${a.id}/edit`}
            className="font-medium text-charcoal hover:text-sage-700"
          >
            {a.title}
          </Link>
          <p className="text-xs text-muted">
            {contentType === "quotes" ? `/quotes/${a.slug}` : `/${a.slug}`}
          </p>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (a) => (
        <span className="flex flex-col items-start gap-1">
          <StatusBadge status={a.status} />
          {a.review_status && a.review_status !== "none" && (
            <span className="text-xs text-muted">{REVIEW_LABELS[a.review_status]}</span>
          )}
        </span>
      ),
    },
    { key: "topic", header: "Topic", render: (a) => a.primary_topic?.name ?? "—" },
    { key: "author", header: "Author", render: (a) => a.author?.display_name ?? "—" },
    {
      key: "updated",
      header: "Updated",
      render: (a) => <time dateTime={a.updated_at}>{formatDateTime(a.updated_at)}</time>,
    },
  ];

  return (
    <>
      <AdminPageHeader
        title={kind.plural}
        description={
          can("articles.view")
            ? kind.description
            : `Your ${kind.plural.toLowerCase()}. Drafts can be edited until they are published.`
        }
        breadcrumbs={[{ label: kind.plural }]}
        actions={
          can("articles.create") && (
            <ButtonLink to={`${kind.base}/new`} size="sm">
              <FilePlus2 aria-hidden />
              {kind.newLabel}
            </ButtonLink>
          )
        }
      />
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          update({ q: search.trim() });
        }}
        className="mb-4 grid gap-3 rounded-xl border border-charcoal/10 bg-white p-4 sm:grid-cols-[1fr_12rem_12rem_auto] sm:items-end"
      >
        <TextField
          label="Search"
          type="search"
          placeholder="Title or slug"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <SelectField
          label="Status"
          options={STATUS_OPTIONS}
          value={status}
          onChange={(e) => update({ status: e.target.value })}
        />
        <SelectField
          label="Review"
          options={REVIEW_OPTIONS}
          value={review}
          onChange={(e) => update({ review: e.target.value })}
        />
        <button
          type="submit"
          className="h-10 rounded-lg bg-charcoal px-4 text-sm font-medium text-ivory hover:bg-ink"
        >
          Search
        </button>
      </form>
      {meta?.counts && (
        <p className="mb-3 text-sm text-muted">
          {meta.counts.published} published · {meta.counts.draft} drafts · {meta.counts.scheduled}{" "}
          scheduled · {meta.counts.archived} archived
        </p>
      )}
      {error ? (
        <ErrorState title={`We couldn't load ${kind.plural.toLowerCase()}`} onRetry={reload} />
      ) : (
        <DataTable
          caption={kind.plural}
          columns={columns}
          rows={data}
          loading={loading}
          empty={{
            icon: PenSquare,
            title:
              q || status || review
                ? `No matching ${kind.plural.toLowerCase()}`
                : contentType === "quotes"
                  ? "No quote collections yet"
                  : "No articles yet",
            description:
              q || status || review
                ? "Try a different search or status."
                : `Your first ${kind.singular} will appear here.`,
          }}
        />
      )}
      <Pagination pagination={meta?.pagination} onPage={(p) => update({ page: p })} />
    </>
  );
}

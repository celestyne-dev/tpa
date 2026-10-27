import { Images } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatBytes } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { SelectField, TextField } from "../components/Fields";
import { MediaDetail } from "../components/media/MediaDetail";
import { MediaGrid } from "../components/media/MediaGrid";
import { MediaUploader } from "../components/media/MediaUploader";
import { PremiumFilesPanel } from "../components/media/PremiumFilesPanel";
import { Pagination } from "../components/Pagination";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const TYPE_OPTIONS = [
  { value: "", label: "All image types" },
  { value: "image/jpeg", label: "JPEG" },
  { value: "image/png", label: "PNG" },
  { value: "image/webp", label: "WebP" },
  { value: "image/avif", label: "AVIF" },
  { value: "image/svg+xml", label: "SVG (built-in)" },
];
const USAGE_OPTIONS = [
  { value: "", label: "Any usage" },
  { value: "used", label: "Used in content" },
  { value: "unused", label: "Not used" },
  { value: "missing_alt", label: "Missing alt text" },
];
const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
  { value: "all", label: "All" },
];
const SORT_OPTIONS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "filename", label: "File name" },
  { value: "size", label: "Largest first" },
];
const KEYS = [
  "q",
  "type",
  "usage",
  "status",
  "sort",
  "category",
  "uploaded_from",
  "uploaded_to",
  "page",
];

/**
 * Central library for public images and (tab "Premium files") protected resource files.
 * Images get public, cached URLs; premium files never do.
 */
export function MediaLibraryPage() {
  const { can } = usePermissions();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "premium" && can("products.view") ? "premium" : "images";
  const tabs = [
    ["images", "Images"],
    ...(can("products.view") ? [["premium", "Premium files"]] : []),
  ];
  return (
    <>
      <AdminPageHeader
        title="Media library"
        description="Public images are validated, stripped of private metadata and optimised into responsive WebP/AVIF versions automatically. Premium files stay in private storage."
        breadcrumbs={[{ label: "Media library" }]}
      />
      {tabs.length > 1 && (
        <div
          role="tablist"
          aria-label="Library sections"
          className="mb-5 flex gap-1 border-b border-charcoal/10"
        >
          {tabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => setParams(key === "premium" ? { tab: "premium" } : {})}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
                tab === key
                  ? "border-sage-700 text-charcoal"
                  : "border-transparent text-muted hover:text-charcoal"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <div role="tabpanel">{tab === "premium" ? <PremiumFilesPanel /> : <ImagesPanel />}</div>
    </>
  );
}

function ImagesPanel() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(KEYS.map((k) => [k, params.get(k) ?? ""]));
  const [search, setSearch] = useState(filters.q);
  const [openId, setOpenId] = useState(null);
  const [uploadCategory, setUploadCategory] = useState("general");

  const query = useAdminQuery(
    () =>
      api.media.list({
        q: filters.q || undefined,
        type: filters.type || undefined,
        usage: filters.usage || undefined,
        category: filters.category || undefined,
        status: filters.status || "active",
        sort: filters.sort || "newest",
        uploaded_from: filters.uploaded_from ? `${filters.uploaded_from}T00:00:00Z` : undefined,
        uploaded_to: filters.uploaded_to ? `${filters.uploaded_to}T00:00:00Z` : undefined,
        page: Number(filters.page) || 1,
        page_size: 30,
      }),
    KEYS.map((k) => filters[k]),
  );
  const stats = useAdminQuery(() => api.media.stats(), []);

  const update = (next) => {
    const merged = { ...filters, page: "", ...next };
    const out = new URLSearchParams();
    Object.entries(merged).forEach(([k, v]) => v && out.set(k, v));
    setParams(out);
  };

  const categories = stats.data?.categories ?? [];
  return (
    <>
      {can("media.upload") && (
        <section aria-label="Upload images" className="mb-6 space-y-3">
          {categories.length > 0 && (
            <div className="max-w-xs">
              <SelectField
                label="Category for new uploads"
                value={uploadCategory}
                options={categories.map((c) => ({ value: c.key, label: c.label }))}
                onChange={(e) => setUploadCategory(e.target.value)}
              />
            </div>
          )}
          <MediaUploader
            fields={{ category: uploadCategory }}
            maxMb={stats.data?.max_upload_mb}
            onUploaded={() => {
              query.reload();
              stats.reload();
            }}
          />
        </section>
      )}
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          update({ q: search.trim() });
        }}
        className="mb-4 grid gap-3 rounded-xl border border-charcoal/10 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        <TextField
          label="Search"
          type="search"
          placeholder="File name, title, alt text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <SelectField
          label="Type"
          options={TYPE_OPTIONS}
          value={filters.type}
          onChange={(e) => update({ type: e.target.value })}
        />
        <SelectField
          label="Category"
          options={[
            { value: "", label: "All categories" },
            ...categories.map((c) => ({
              value: c.key,
              label: `${c.label} (${stats.data?.category_counts?.[c.key] ?? 0})`,
            })),
          ]}
          value={filters.category}
          onChange={(e) => update({ category: e.target.value })}
        />
        <SelectField
          label="Usage"
          options={USAGE_OPTIONS}
          value={filters.usage}
          onChange={(e) => update({ usage: e.target.value })}
        />
        <SelectField
          label="Sort"
          options={SORT_OPTIONS}
          value={filters.sort || "newest"}
          onChange={(e) => update({ sort: e.target.value })}
        />
        <SelectField
          label="Status"
          options={STATUS_OPTIONS}
          value={filters.status || "active"}
          onChange={(e) => update({ status: e.target.value })}
        />
        <TextField
          label="Uploaded from"
          type="date"
          value={filters.uploaded_from}
          onChange={(e) => update({ uploaded_from: e.target.value })}
        />
        <TextField
          label="Uploaded until"
          type="date"
          value={filters.uploaded_to}
          onChange={(e) => update({ uploaded_to: e.target.value })}
        />
        <div className="flex items-end">
          <button
            type="submit"
            className="h-10 w-full rounded-lg bg-charcoal px-4 text-sm font-medium text-ivory hover:bg-ink"
          >
            Search
          </button>
        </div>
      </form>
      {stats.data && (
        <p className="mb-3 text-sm text-muted">
          {stats.data.assets} uploaded image{stats.data.assets === 1 ? "" : "s"} · optimised files{" "}
          {formatBytes(stats.data.variants_bytes)} · retained originals{" "}
          {formatBytes(stats.data.originals_bytes)}
          {stats.data.superseded_bytes > 0 &&
            ` · ${formatBytes(stats.data.superseded_bytes)} awaiting cleanup`}
          {stats.data.avif_enabled ? " · AVIF enabled" : ""}
        </p>
      )}
      {query.error ? (
        <ErrorState title="We couldn't load the media library" onRetry={query.reload} />
      ) : query.loading && !query.data ? (
        <div
          role="status"
          aria-label="Loading media"
          className="grid grid-cols-2 gap-3 sm:grid-cols-4"
        >
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="aspect-[4/3]" />
          ))}
        </div>
      ) : query.data?.length ? (
        <MediaGrid items={query.data} onOpen={(item) => setOpenId(item.id)} />
      ) : (
        <EmptyState
          icon={Images}
          title="No images found"
          description="Upload images or change the filters."
        />
      )}
      <Pagination pagination={query.meta?.pagination} onPage={(p) => update({ page: String(p) })} />
      {openId && (
        <MediaDetail
          mediaId={openId}
          categories={categories.length ? categories : undefined}
          onClose={() => setOpenId(null)}
          onChanged={() => {
            query.reload();
            stats.reload();
          }}
        />
      )}
    </>
  );
}

import { CircleAlert, ExternalLink, Search, TriangleAlert } from "lucide-react";
import { Link } from "react-router";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const TOTALS = [
  ["missing_meta_description", "Missing meta description"],
  ["missing_seo_title", "No custom SEO title (uses article title)"],
  ["missing_featured_image", "No featured image"],
  ["featured_alt_missing", "Featured image without alt text"],
  ["noindex", "Hidden from search (noindex)"],
  ["external_canonical", "Canonical points elsewhere"],
  ["broken_internal_link", "Broken internal links"],
];

function Stat({ label, value, tone }) {
  return (
    <div className="rounded-xl border border-charcoal/10 bg-white p-4">
      <p className="text-xs tracking-wide text-muted uppercase">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone ?? ""}`}>{value}</p>
    </div>
  );
}

/** SEO audit built from real CMS data (no search-console or ranking data is invented). */
export function SeoPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(() => api.seo.overview(), []);

  return (
    <>
      <AdminPageHeader
        title="SEO"
        description="Technical SEO health of published content: metadata, images, indexing, redirects and the sitemap. Search rankings and traffic are not tracked here."
        breadcrumbs={[{ label: "SEO" }]}
      />
      {error && <ErrorState title="We couldn't load the SEO audit" onRetry={reload} />}
      {loading && !data && <Skeleton className="h-64 w-full" />}
      {data && (
        <div className="space-y-6">
          <section aria-label="Summary" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Published articles" value={data.published_articles} />
            <Stat label="Sitemap URLs" value={data.sitemap.urls} />
            <Stat label="Images in sitemap" value={data.sitemap.images} />
            <Stat
              label="Active redirects"
              value={`${data.redirects.active} / ${data.redirects.total}`}
            />
          </section>

          <section
            aria-labelledby="checks-heading"
            className="rounded-xl border border-charcoal/10 bg-white p-5"
          >
            <h2 id="checks-heading" className="font-sans text-base font-semibold">
              Published articles needing attention
            </h2>
            <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              {TOTALS.map(([key, label]) => (
                <div
                  key={key}
                  className="flex justify-between gap-3 border-b border-charcoal/5 py-1"
                >
                  <dt>{label}</dt>
                  <dd className={data.totals[key] ? "font-semibold text-gold-700" : "text-muted"}>
                    {data.totals[key]}
                  </dd>
                </div>
              ))}
            </dl>
            {data.articles_with_issues.length > 0 ? (
              <ul className="mt-5 divide-y divide-charcoal/5">
                {data.articles_with_issues.map((a) => (
                  <li key={a.id} className="py-3 text-sm">
                    <Link
                      to={`/admin/articles/${a.id}/edit`}
                      className="font-medium hover:text-sage-700"
                    >
                      {a.title}
                    </Link>
                    <ul className="mt-1 space-y-0.5">
                      {a.issues.map((i) => (
                        <li key={i.code + i.message} className="flex gap-1.5 text-muted">
                          {i.severity === "error" ? (
                            <CircleAlert
                              aria-hidden
                              className="mt-0.5 size-3.5 shrink-0 text-red-800"
                            />
                          ) : (
                            <TriangleAlert
                              aria-hidden
                              className="mt-0.5 size-3.5 shrink-0 text-gold-700"
                            />
                          )}
                          {i.message}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-sage-800">No warnings on published articles.</p>
            )}
          </section>

          <section aria-labelledby="build-heading" className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-charcoal/10 bg-white p-5 text-sm">
              <h2 id="build-heading" className="font-sans text-base font-semibold">
                Sitemap and static build
              </h2>
              <dl className="mt-3 space-y-1">
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">Last successful build</dt>
                  <dd>
                    {data.build.last_build_at ? formatDateTime(data.build.last_build_at) : "Never"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">Indexing enabled in the build</dt>
                  <dd>
                    {data.build.indexing_enabled == null
                      ? "Unknown"
                      : data.build.indexing_enabled
                        ? "Yes"
                        : "No (robots.txt disallows crawling)"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">Unpublished public changes</dt>
                  <dd>{data.build.rebuild_required ? "Yes — a rebuild is pending" : "No"}</dd>
                </div>
              </dl>
              <p className="mt-3 text-xs text-muted">
                The sitemap lists only published, indexable articles whose canonical URL is their
                own, plus their images.
              </p>
              {can("publishing.view") && (
                <Link to="/admin/publishing" className="mt-3 inline-block text-sage-700 underline">
                  Publishing jobs
                </Link>
              )}
            </div>
            <div className="rounded-xl border border-charcoal/10 bg-white p-5 text-sm">
              <h2 className="font-sans text-base font-semibold">Tools</h2>
              <ul className="mt-3 space-y-2">
                {(can("redirects.manage") || can("seo.view")) && (
                  <li>
                    <Link to="/admin/redirects" className="text-sage-700 underline">
                      Redirect manager
                    </Link>{" "}
                    <span className="text-muted">— keep old URLs working with real 301/308s.</span>
                  </li>
                )}
                {can("seo.manage") && (
                  <li>
                    <Link to="/admin/settings" className="text-sage-700 underline">
                      SEO defaults
                    </Link>{" "}
                    <span className="text-muted">
                      — default title, description and sharing image.
                    </span>
                  </li>
                )}
                <li className="flex items-center gap-1 text-muted">
                  <Search aria-hidden className="size-4" />
                  Per-article checks are in each article&apos;s SEO tab.
                </li>
                <li className="flex items-center gap-1 text-muted">
                  <ExternalLink aria-hidden className="size-4" />
                  Search Console data is not connected (planned).
                </li>
              </ul>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { siteConfig } from "@/config/site";
import { cn } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { CheckboxField, TextAreaField, TextField } from "./Fields";
import { ImageChooser, MediaThumb } from "./media/ImageChooser";

const SEVERITY = {
  error: { icon: CircleAlert, className: "text-red-800", label: "Problem" },
  warning: { icon: TriangleAlert, className: "text-gold-700", label: "Warning" },
  info: { icon: Info, className: "text-sage-700", label: "Suggestion" },
};

function Counter({ value, soft }) {
  const length = (value ?? "").length;
  return (
    <span className={cn("text-xs", length > soft ? "text-gold-700" : "text-muted")}>
      {length} characters{length > soft ? " · may be shortened in results" : ""}
    </span>
  );
}

/** Search/social previews, metadata fields and non-blocking SEO checks. */
export function SeoPanel({ articleId, form, set, can, slugLocked, checks, err, onRefreshChecks }) {
  const api = useAdminApi();
  const [slugStatus, setSlugStatus] = useState(null);
  const title = form.seo_title || form.title || "Untitled article";
  const description = form.meta_description || form.excerpt || "";
  const url = `${siteConfig.url.replace(/^https?:\/\//, "")}/articles/${form.slug || "…"}`;
  const socialTitle = form.social_title || title;
  const socialDescription = form.social_description || description;

  useEffect(() => {
    if (!form.slug || slugLocked) return undefined;
    const timer = setTimeout(() => {
      api.articles
        .slugCheck(form.slug, articleId)
        .then((res) => setSlugStatus(res.data))
        .catch(() => setSlugStatus(null));
    }, 400);
    return () => clearTimeout(timer);
  }, [api, form.slug, articleId, slugLocked]);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 space-y-5">
        <section
          aria-labelledby="search-preview-heading"
          className="rounded-xl border border-charcoal/10 bg-white p-5"
        >
          <h3 id="search-preview-heading" className="font-sans text-sm font-semibold">
            Search result preview
          </h3>
          <div
            className="mt-3 rounded-lg border border-charcoal/10 p-4"
            data-testid="search-preview"
          >
            <p className="truncate text-xs text-muted">{url}</p>
            <p className="mt-1 line-clamp-1 text-lg text-[#1a0dab]">{title}</p>
            <p className="mt-1 line-clamp-2 text-sm text-ink">
              {description || "Add a meta description or excerpt."}
            </p>
          </div>
          <p className="mt-2 text-xs text-muted">
            An approximation: search engines choose how to display results and may rewrite titles
            and snippets.
          </p>
        </section>

        <div className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5">
          <div>
            <TextField
              label="SEO title"
              hint="Defaults to the article title."
              value={form.seo_title}
              onChange={set("seo_title")}
              error={err("seo_title")}
            />
            <Counter value={form.seo_title || form.title} soft={65} />
          </div>
          <div>
            <TextAreaField
              label="Meta description"
              hint="A plain summary of what readers will learn. Defaults to the excerpt."
              value={form.meta_description}
              onChange={set("meta_description")}
              error={err("meta_description")}
            />
            <Counter value={form.meta_description} soft={160} />
          </div>
          <div>
            <TextField
              label="URL slug"
              value={form.slug}
              onChange={set("slug")}
              error={err("slug")}
              disabled={slugLocked}
              hint={
                slugLocked
                  ? "Locked after publication. Someone with the SEO permission can change it; a 301 redirect is then created automatically."
                  : form.first_published
                    ? "Changing a published slug creates a 301 redirect from the old URL."
                    : "Leave empty to generate it from the title."
              }
            />
            {slugStatus && slugStatus.slug === form.slug && !slugLocked && (
              <p
                className={cn(
                  "mt-1 text-xs",
                  slugStatus.valid && slugStatus.available ? "text-sage-800" : "text-red-800",
                )}
              >
                {!slugStatus.valid
                  ? "Use lowercase letters, numbers and hyphens."
                  : !slugStatus.available
                    ? "This slug is already used by another article."
                    : slugStatus.redirect_destination
                      ? `Available, but an active redirect currently sends this URL to ${slugStatus.redirect_destination}.`
                      : "Available."}
              </p>
            )}
          </div>
          <TextField
            label="Canonical URL"
            placeholder="https://"
            hint={
              can?.edit_indexing
                ? "Only set this when the original lives elsewhere (e.g. syndicated). Leave empty for the article's own URL."
                : "Requires the SEO permission."
            }
            value={form.canonical_url}
            onChange={set("canonical_url")}
            error={err("canonical_url")}
            disabled={!can?.edit_indexing}
          />
          <CheckboxField
            label="Hide from search engines (noindex)"
            hint={
              can?.edit_indexing
                ? "The article is also left out of the sitemap."
                : "Requires the SEO permission."
            }
            checked={form.noindex}
            onChange={set("noindex")}
            disabled={!can?.edit_indexing}
          />
        </div>

        <div className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5">
          <h3 className="font-sans text-sm font-semibold">Social sharing (Open Graph / X)</h3>
          <TextField
            label="Social title"
            hint="Defaults to the SEO title."
            value={form.social_title}
            onChange={set("social_title")}
            error={err("social_title")}
          />
          <TextAreaField
            label="Social description"
            hint="Defaults to the meta description."
            value={form.social_description}
            onChange={set("social_description")}
            error={err("social_description")}
          />
          <div>
            <p className="mb-1 text-sm font-medium">Social image</p>
            <ImageChooser
              label="social image"
              mediaId={form.social_image_id ? Number(form.social_image_id) : null}
              onChange={(id) => set("social_image_id")(id ?? "")}
            />
            <p className="mt-1 text-xs text-muted">
              Defaults to the featured image. A 1200×630 version is generated automatically.
            </p>
          </div>
          <div
            className="overflow-hidden rounded-lg border border-charcoal/10"
            data-testid="social-preview"
          >
            <div className="aspect-[1200/630] bg-beige">
              {(form.social_image_id || form.featured_image_id) && (
                <MediaThumb
                  id={Number(form.social_image_id || form.featured_image_id)}
                  className="h-full w-full"
                />
              )}
            </div>
            <div className="p-3">
              <p className="text-xs text-muted uppercase">
                {siteConfig.url.replace(/^https?:\/\//, "")}
              </p>
              <p className="line-clamp-1 font-semibold">{socialTitle}</p>
              <p className="line-clamp-2 text-sm text-muted">{socialDescription}</p>
            </div>
          </div>
        </div>
      </div>

      <aside aria-labelledby="seo-checks-heading" className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 id="seo-checks-heading" className="font-sans text-sm font-semibold">
            SEO checks
          </h3>
          {onRefreshChecks && (
            <button
              type="button"
              className="text-xs text-sage-700 underline"
              onClick={onRefreshChecks}
            >
              Refresh
            </button>
          )}
        </div>
        {!checks ? (
          <p className="text-sm text-muted">Save the article to run checks.</p>
        ) : checks.checks.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-sage-800">
            <CircleCheck aria-hidden className="size-4" /> No issues found.
          </p>
        ) : (
          <ul className="space-y-2" aria-label="SEO check results">
            {checks.checks.map((c) => {
              const s = SEVERITY[c.severity] ?? SEVERITY.info;
              const Icon = s.icon;
              return (
                <li key={`${c.code}-${c.message}`} className="flex gap-2 text-sm">
                  <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", s.className)} />
                  <span>
                    <span className="sr-only">{s.label}: </span>
                    {c.message}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-xs text-muted">
          Checks reflect the last saved version. They are guidance, not ranking guarantees.
        </p>
      </aside>
    </div>
  );
}

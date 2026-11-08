import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SectionList } from "@/components/sections/SectionList";
import { ArticleSidebar } from "@/components/sidebar/ArticleSidebar";
import { Container } from "@/components/ui/Container";
import { useSite } from "@/hooks/useContent";

/**
 * The article sidebar previewed in place: a placeholder article column beside it on wide
 * screens, and the sidebar sections below it on phones and tablets (as on the website).
 */
function SidebarPreview({ page }) {
  return (
    <Container size="wide" className="py-10">
      <h1 className="sr-only">{page.title}</h1>
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_19rem] lg:gap-12 xl:grid-cols-[minmax(0,1fr)_21rem] xl:gap-16">
        <div
          aria-hidden
          className="grid min-h-64 place-items-center rounded-[var(--radius-card)] border border-dashed border-charcoal/15 p-8 text-center text-sm text-muted"
        >
          The article appears here. The sidebar is previewed beside the newest article.
        </div>
        <ArticleSidebar
          sections={page.sections}
          preview
          className="mt-12 border-t border-charcoal/10 pt-10 lg:mt-0 lg:border-t-0 lg:pt-0"
        />
      </div>
    </Container>
  );
}

/**
 * The public page chrome around a draft. Links are inert inside previews so an
 * editor never navigates away from their work by accident.
 */
export function PreviewShell({ page }) {
  const { data: site } = useSite();
  const branding = site?.branding ?? {};
  return (
    <div
      className="flex min-h-dvh flex-col bg-ivory"
      data-palette={branding.palette ?? "classic"}
      data-type={branding.typography ?? "classic"}
      data-buttons={branding.button_shape ?? "pill"}
      data-images={branding.image_style ?? "rounded"}
      onClickCapture={(event) => {
        if (event.target.closest?.("a[href]")) event.preventDefault();
      }}
    >
      <SiteHeader />
      <main className="flex-1">
        {page?.template === "sidebar" ? (
          <SidebarPreview page={page} />
        ) : (
          <SectionList page={page} preview />
        )}
      </main>
      <SiteFooter site={site} />
    </div>
  );
}

import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SectionList } from "@/components/sections/SectionList";
import { useSite } from "@/hooks/useContent";

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
        <SectionList page={page} preview />
      </main>
      <SiteFooter site={site} />
    </div>
  );
}

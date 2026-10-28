import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router";
import { usePageViewTracking } from "@/analytics/pageViews";
import { JsonLd } from "@/components/ui/JsonLd";
import { useSite } from "@/hooks/useContent";
import { siteJsonLd } from "@/utils/structuredData";
import { AnnouncementBar } from "./AnnouncementBar";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";
import { SkipLink } from "./SkipLink";

/** Public site shell. Site settings failures degrade gracefully (no social links). */
export function RootLayout() {
  const { data: site } = useSite();
  const branding = site?.branding ?? {};
  const { pathname } = useLocation();
  const mainRef = useRef(null);
  const firstRender = useRef(true);
  usePageViewTracking();

  // On client-side navigation: scroll to top and move focus to the new content.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    window.scrollTo?.(0, 0);
    mainRef.current?.focus({ preventScroll: true });
  }, [pathname]);

  return (
    <div
      className="flex min-h-dvh flex-col overflow-x-clip bg-ivory"
      data-palette={branding.palette ?? "classic"}
      data-type={branding.typography ?? "classic"}
      data-buttons={branding.button_shape ?? "pill"}
      data-images={branding.image_style ?? "rounded"}
    >
      <SkipLink />
      <AnnouncementBar site={site} />
      <SiteHeader />
      <main ref={mainRef} id="main-content" tabIndex={-1} className="flex-1 focus:outline-none">
        <Outlet />
      </main>
      <SiteFooter site={site} />
      <JsonLd data={siteJsonLd(site)} />
    </div>
  );
}

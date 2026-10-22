import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router";
import { JsonLd } from "@/components/ui/JsonLd";
import { useSite } from "@/hooks/useContent";
import { organizationJsonLd, websiteJsonLd } from "@/utils/structuredData";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";
import { SkipLink } from "./SkipLink";

/** Public site shell. Site settings failures degrade gracefully (no social links). */
export function RootLayout() {
  const { data: site } = useSite();
  const socialLinks = site?.social_links ?? [];
  const { pathname } = useLocation();
  const mainRef = useRef(null);
  const firstRender = useRef(true);

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
    <div className="flex min-h-dvh flex-col overflow-x-clip">
      <SkipLink />
      <SiteHeader />
      <main ref={mainRef} id="main-content" tabIndex={-1} className="flex-1 focus:outline-none">
        <Outlet />
      </main>
      <SiteFooter socialLinks={socialLinks} />
      <JsonLd data={[organizationJsonLd(socialLinks), websiteJsonLd()]} />
    </div>
  );
}

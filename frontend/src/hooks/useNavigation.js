import { footerNav, mainNav } from "@/config/navigation";
import { useSite } from "./useContent";

const fromConfig = (item) => ({
  label: item.label,
  href: item.href,
  external: false,
  newTab: false,
});
const fromApi = (item) => ({
  label: item.label,
  href: item.url,
  external: item.external,
  newTab: item.open_in_new_tab,
});

/** CMS-managed navigation (from GET /api/v1/site) with built-in fallbacks. */
export function useNavigation() {
  const { data: site } = useSite();
  const nav = site?.navigation;
  return {
    primary: nav?.primary?.length ? nav.primary.map(fromApi) : mainNav.map(fromConfig),
    footer: nav?.footer?.length
      ? nav.footer.map((g) => ({ title: g.title, items: g.items.map(fromApi) }))
      : footerNav.map((g) => ({ title: g.title, items: g.items.map(fromConfig) })),
  };
}

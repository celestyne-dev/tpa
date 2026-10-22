import { footerNav, mainNav } from "@/config/navigation";
import { useSite } from "./useContent";

const fromConfig = (item) => ({
  label: item.label,
  href: item.href,
  external: false,
  newTab: false,
  visibility: "all",
});

function fromApi(item) {
  const node = {
    label: item.label,
    href: item.url,
    external: item.external ?? false,
    newTab: item.open_in_new_tab ?? false,
    visibility: item.visibility ?? "all",
  };
  if (item.children) node.children = item.children.map(fromApi);
  return node;
}

/** CMS-managed navigation (published, from GET /api/v1/site) with built-in fallbacks. */
export function useNavigation() {
  const { data: site } = useSite();
  const nav = site?.navigation;
  const primary = nav?.primary?.length ? nav.primary.map(fromApi) : mainNav.map(fromConfig);
  return {
    primary,
    // The mobile menu falls back to the header menu when it has not been customised.
    mobile: nav?.mobile?.length ? nav.mobile.map(fromApi) : primary,
    footer: nav?.footer?.length
      ? nav.footer.map((g) => ({ title: g.title, items: g.items.map(fromApi) }))
      : footerNav.map((g) => ({ title: g.title, items: g.items.map(fromConfig) })),
    legal: (nav?.legal ?? []).map(fromApi),
  };
}

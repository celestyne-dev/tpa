import { footerNav, mainNav, routes } from "@/config/navigation";
import { useSite, useTopics } from "./useContent";

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

/**
 * The header link shipped by default before the "Resources" rename ("Free Resources" to
 * /free-resources). Only that exact, unedited default is shown as "Resources", leading to
 * the Resource library (free and premium); any link an editor has relabelled or pointed
 * elsewhere is shown exactly as configured. Admin › Navigation changes it for good.
 */
export const LEGACY_RESOURCES_LINK = { label: "Free Resources", href: "/free-resources" };

function readerLabels(item) {
  if (item.label === LEGACY_RESOURCES_LINK.label && item.href === LEGACY_RESOURCES_LINK.href) {
    return { ...item, label: "Resources", href: routes.resources };
  }
  return item.children ? { ...item, children: item.children.map(readerLabels) } : item;
}

const TOPIC_PREFIX = routes.topic("");

/**
 * A menu group made only of topic links (the header's "Topics") also lists the other
 * published topics that have articles, after the editor's own links and in the site's
 * topic order, so every category can be reached. Nothing is removed or renamed, and only
 * real topic pages are linked.
 */
function withAllTopics(item, topics) {
  const isTopicGroup =
    item.children?.length > 0 &&
    item.children.every((child) => child.href?.startsWith(TOPIC_PREFIX));
  if (!isTopicGroup || !topics?.length) return item;
  const listed = new Set(item.children.map((child) => child.href));
  const more = topics
    .filter((t) => t.article_count > 0 && !listed.has(routes.topic(t.slug)))
    .map((t) => fromConfig({ label: t.name, href: routes.topic(t.slug) }));
  return more.length ? { ...item, children: [...item.children, ...more] } : item;
}

/** CMS-managed navigation (published, from GET /api/v1/site) with built-in fallbacks. */
export function useNavigation() {
  const { data: site } = useSite();
  const { data: topics } = useTopics();
  const nav = site?.navigation;
  const upgrade = (item) => withAllTopics(readerLabels(item), topics);
  const primary = (nav?.primary?.length ? nav.primary.map(fromApi) : mainNav.map(fromConfig)).map(
    upgrade,
  );
  return {
    primary,
    // The mobile menu falls back to the header menu when it has not been customised.
    mobile: nav?.mobile?.length ? nav.mobile.map(fromApi).map(upgrade) : primary,
    footer: nav?.footer?.length
      ? nav.footer.map((g) => ({ title: g.title, items: g.items.map(fromApi) }))
      : footerNav.map((g) => ({ title: g.title, items: g.items.map(fromConfig) })),
    legal: (nav?.legal ?? []).map(fromApi),
  };
}

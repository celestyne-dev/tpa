import { footerNav, mainNav, routes } from "@/config/navigation";
import { useSelector } from "react-redux";
import { selectTopicList } from "@/store/slices/topicsSlice";
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

/** The slug in a /topics/<slug>[/page/N][?…][#…] link, or null for any other link. */
export function topicSlugOf(href) {
  if (!href?.startsWith(TOPIC_PREFIX)) return null;
  return href.slice(TOPIC_PREFIX.length).split(/[/?#]/)[0] || null;
}

/**
 * Leaves out links to topics that are not published. The server already drops them (and
 * points renamed topics at their new address); this covers menus cached before a topic
 * was hidden. Until the topic list has loaded every link is kept.
 */
export function liveLinks(items, topics) {
  if (!topics) return items;
  const live = new Set(topics.map((t) => t.slug));
  return items.filter((item) => {
    const slug = topicSlugOf(item.href);
    return slug === null || live.has(slug);
  });
}

/** Built-in footer: the Explore column also links the first published topics with articles. */
function fallbackFooter(topics) {
  const extra = (topics ?? [])
    .filter((t) => t.article_count > 0)
    .slice(0, 3)
    .map((t) => ({ label: t.name, href: routes.topic(t.slug) }));
  return footerNav.map((g, i) => ({
    title: g.title,
    items: [...g.items, ...(i === 0 ? extra : [])].map(fromConfig),
  }));
}

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
  if (!isTopicGroup)
    return item.children ? { ...item, children: liveLinks(item.children, topics) } : item;
  // The menu loads topics when first opened (see NavDropdown), not on every page view.
  item = { ...item, topicGroup: true, children: liveLinks(item.children, topics) };
  if (!topics?.length) return item;
  const listed = new Set(item.children.map((child) => child.href));
  const more = topics
    .filter((t) => t.article_count > 0 && !listed.has(routes.topic(t.slug)))
    .map((t) => fromConfig({ label: t.name, href: routes.topic(t.slug) }));
  return more.length ? { ...item, children: [...item.children, ...more] } : item;
}

/** CMS-managed navigation (published, from GET /api/v1/site) with built-in fallbacks. */
export function useNavigation() {
  const { data: site } = useSite();
  const topics = useSelector(selectTopicList)?.items;
  const nav = site?.navigation;
  const upgrade = (item) => withAllTopics(readerLabels(item), topics);
  const menu = (items) =>
    liveLinks(items, topics)
      .map(upgrade)
      .filter((item) => !item.children || item.children.length > 0);
  const primary = menu(nav?.primary?.length ? nav.primary.map(fromApi) : mainNav.map(fromConfig));
  return {
    primary,
    // The mobile menu falls back to the header menu when it has not been customised.
    mobile: nav?.mobile?.length ? menu(nav.mobile.map(fromApi)) : primary,
    footer: nav?.footer?.length
      ? nav.footer.map((g) => ({ title: g.title, items: liveLinks(g.items.map(fromApi), topics) }))
      : fallbackFooter(topics),
    legal: (nav?.legal ?? []).map(fromApi),
  };
}

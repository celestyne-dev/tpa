import { matchRoutes } from "react-router";
import { routes } from "@/config/navigation";
import {
  ARTICLE_LIST_QUERY,
  FEATURED_QUERY,
  LATEST_QUERY,
  topicArticlesQuery,
} from "@/data/queries";
import { AboutPage } from "@/pages/AboutPage";
import { AffiliateDisclosurePage } from "@/pages/AffiliateDisclosurePage";
import { ArticleDetailPage } from "@/pages/ArticleDetailPage";
import { ArticlesPage } from "@/pages/ArticlesPage";
import { ContactPage } from "@/pages/ContactPage";
import { FreeResourcesPage } from "@/pages/FreeResourcesPage";
import { HomePage } from "@/pages/HomePage";
import { NewsletterPage } from "@/pages/NewsletterPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PartnerPage } from "@/pages/PartnerPage";
import { PrivacyPolicyPage } from "@/pages/PrivacyPolicyPage";
import { ShopPage } from "@/pages/ShopPage";
import { TermsPage } from "@/pages/TermsPage";
import { TopicPage } from "@/pages/TopicPage";
import { fetchArticle, fetchArticles } from "@/store/slices/articlesSlice";
import { fetchProducts } from "@/store/slices/productsSlice";
import { fetchSite } from "@/store/slices/siteSlice";
import { fetchTopic, fetchTopics } from "@/store/slices/topicsSlice";

/**
 * Public route table. `load` returns the thunks whose data a page needs; the
 * prerenderer awaits them before rendering so the static HTML contains the
 * full content. In the browser the same data is fetched by page hooks.
 */
export const routeTable = [
  {
    path: routes.home,
    Component: HomePage,
    load: () => [fetchTopics(), fetchArticles(FEATURED_QUERY), fetchProducts()],
  },
  {
    path: routes.articles,
    Component: ArticlesPage,
    load: () => [fetchTopics(), fetchArticles(FEATURED_QUERY), fetchArticles(ARTICLE_LIST_QUERY)],
  },
  {
    path: "/articles/:slug",
    Component: ArticleDetailPage,
    load: ({ slug }) => [fetchArticle({ slug })],
  },
  {
    path: "/topics/:slug",
    Component: TopicPage,
    load: ({ slug }) => [
      fetchTopic({ slug }),
      fetchTopics(),
      fetchArticles(topicArticlesQuery(slug)),
    ],
  },
  { path: routes.shop, Component: ShopPage, load: () => [fetchProducts()] },
  {
    path: routes.freeResources,
    Component: FreeResourcesPage,
    load: () => [fetchArticles(LATEST_QUERY)],
  },
  { path: routes.newsletter, Component: NewsletterPage },
  { path: routes.partner, Component: PartnerPage },
  { path: routes.about, Component: AboutPage, load: () => [fetchTopics()] },
  { path: routes.contact, Component: ContactPage },
  { path: routes.privacy, Component: PrivacyPolicyPage },
  { path: routes.terms, Component: TermsPage },
  { path: routes.affiliate, Component: AffiliateDisclosurePage },
  { path: "*", Component: NotFoundPage },
];

/** Thunks to dispatch before rendering `pathname` (site settings are always needed). */
export function getRouteLoaders(pathname) {
  const matches = matchRoutes(routeTable, pathname) ?? [];
  const match = matches[matches.length - 1];
  const extra = match?.route.load ? match.route.load(match.params) : [];
  return [fetchSite(), ...extra];
}

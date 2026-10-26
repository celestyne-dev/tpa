import { matchRoutes } from "react-router";
import { legacyAuthRoutes, routes } from "@/config/navigation";
import {
  ARTICLE_LIST_QUERY,
  FEATURED_QUERY,
  LATEST_QUERY,
  topicArticlesQuery,
} from "@/data/queries";
import { AboutPage } from "@/pages/AboutPage";
import { AdvertisePage } from "@/pages/AdvertisePage";
import { AffiliateDisclosurePage } from "@/pages/AffiliateDisclosurePage";
import { ArticleDetailPage } from "@/pages/ArticleDetailPage";
import { ArticlesPage } from "@/pages/ArticlesPage";
import { ContactPage } from "@/pages/ContactPage";
import { FreeResourcesPage } from "@/pages/FreeResourcesPage";
import { HomePage } from "@/pages/HomePage";
import { NewsletterPage } from "@/pages/NewsletterPage";
import { CmsRoute } from "@/pages/CmsPage";
import { PartnerPage } from "@/pages/PartnerPage";
import { PrivacyPolicyPage } from "@/pages/PrivacyPolicyPage";
import { CollectionPage } from "@/pages/CollectionPage";
import { ProductPage } from "@/pages/ProductPage";
import { ShopPage } from "@/pages/ShopPage";
import { TermsPage } from "@/pages/TermsPage";
import { TopicPage } from "@/pages/TopicPage";
import { withCmsOverride } from "@/routes/cmsOverride";
import { LegacyAuthRedirect } from "@/routes/LegacyAuthRedirect";
import * as commerce from "@/routes/commerceRoutes";
import { fetchArticle, fetchArticles } from "@/store/slices/articlesSlice";
import { fetchMediaKit } from "@/store/slices/mediaKitSlice";
import { fetchPage } from "@/store/slices/pagesSlice";
import { fetchCollection, fetchProduct, fetchProducts } from "@/store/slices/productsSlice";
import { fetchSite } from "@/store/slices/siteSlice";
import { fetchTopic, fetchTopics } from "@/store/slices/topicsSlice";
import { normalisePath } from "@/utils/pagePath";

/**
 * Public route table. `load` returns the thunks whose data a page needs; the
 * prerenderer awaits them before rendering so the static HTML contains the
 * full content. In the browser the same data is fetched by page hooks.
 */
export const routeTable = [
  {
    path: routes.home,
    Component: HomePage,
    load: () => [fetchPage({ path: "/" })],
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
    path: "/shop/collections/:slug",
    Component: CollectionPage,
    load: ({ slug }) => [fetchCollection({ slug })],
  },
  {
    path: "/shop/:productSlug",
    Component: ProductPage,
    load: ({ productSlug }) => [fetchProduct({ slug: productSlug })],
  },
  // Private customer pages: rendered as shells (no customer data is ever prerendered).
  ...[
    [routes.cart, commerce.CartRoute],
    [routes.checkout, commerce.CheckoutRoute],
    [routes.checkoutComplete, commerce.CheckoutCompleteRoute],
    [routes.purchases, commerce.PurchasesRoute],
    [routes.account, commerce.AccountRoute],
    [routes.accountLibrary, commerce.AccountLibraryRoute],
    [routes.accountOrders, commerce.AccountOrdersRoute],
    [routes.accountSettings, commerce.AccountSettingsRoute],
    [routes.signIn, commerce.SignInRoute],
    [routes.register, commerce.RegisterRoute],
    [routes.verifyEmail, commerce.VerifyEmailRoute],
    [routes.forgotPassword, commerce.ForgotPasswordRoute],
    [routes.resetPassword, commerce.ResetPasswordRoute],
    ...Object.keys(legacyAuthRoutes).map((path) => [path, LegacyAuthRedirect]),
    [routes.newsletterConfirm, commerce.NewsletterConfirmRoute],
    [routes.newsletterPreferences, commerce.NewsletterPreferencesRoute],
    [routes.newsletterUnsubscribe, commerce.NewsletterUnsubscribeRoute],
    [routes.resourceAccess, commerce.ResourceAccessRoute],
  ].map(([path, Component]) => ({ path, Component, private: true })),
  {
    path: routes.freeResources,
    Component: withCmsOverride(FreeResourcesPage, routes.freeResources),
    load: () => [fetchArticles(LATEST_QUERY), fetchPage({ path: routes.freeResources })],
  },
  ...[
    [routes.newsletter, NewsletterPage],
    [routes.partner, PartnerPage],
    [routes.contact, ContactPage],
    [routes.privacy, PrivacyPolicyPage],
    [routes.terms, TermsPage],
    [routes.affiliate, AffiliateDisclosurePage],
  ].map(([path, Page]) => ({
    path,
    Component: withCmsOverride(Page, path),
    load: () =>
      path === routes.partner ? [fetchPage({ path }), fetchMediaKit()] : [fetchPage({ path })],
  })),
  {
    path: routes.advertise,
    Component: withCmsOverride(AdvertisePage, routes.advertise),
    load: () => [fetchMediaKit(), fetchPage({ path: routes.advertise })],
  },
  {
    path: routes.about,
    Component: withCmsOverride(AboutPage, routes.about),
    load: () => [fetchTopics(), fetchPage({ path: routes.about })],
  },
  {
    path: "*",
    Component: CmsRoute,
    load: (_params, pathname) => {
      const path = normalisePath(pathname);
      return path && path !== "/" ? [fetchPage({ path })] : [];
    },
  },
];

/** Thunks to dispatch before rendering `pathname` (site settings are always needed). */
export function getRouteLoaders(pathname) {
  const matches = matchRoutes(routeTable, pathname) ?? [];
  const match = matches[matches.length - 1];
  const extra = match?.route.load ? match.route.load(match.params, pathname) : [];
  return [fetchSite(), ...extra];
}

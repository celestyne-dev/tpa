/** The /topics anchor of a menu group: "Career & Growth" -> "career-growth" (mirrors
 * topic_links.group_anchor on the server). */
export function topicGroupAnchor(label) {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export const routes = {
  home: "/",
  articles: "/articles",
  /** Archive page N (page 1 is /articles itself: one URL per page). */
  articlesPage: (page) => (page > 1 ? `/articles/page/${page}` : "/articles"),
  article: (slug) => `/articles/${slug}`,
  /** All topics, grouped as in the header menu (anchors: topicGroup). */
  topics: "/topics",
  topicGroup: (label) => `/topics#${topicGroupAnchor(label)}`,
  topic: (slug) => `/topics/${slug}`,
  topicPage: (slug, page) => (page > 1 ? `/topics/${slug}/page/${page}` : `/topics/${slug}`),
  authors: "/authors",
  author: (slug) => `/authors/${slug}`,
  authorPage: (slug, page) => (page > 1 ? `/authors/${slug}/page/${page}` : `/authors/${slug}`),
  search: "/search",
  shop: "/shop",
  product: (slug) => `/shop/${slug}`,
  collection: (slug) => `/shop/collections/${slug}`,
  cart: "/cart",
  checkout: "/checkout",
  checkoutComplete: "/checkout/complete",
  purchases: "/purchases",
  account: "/account",
  accountOrders: "/account/orders",
  accountLibrary: "/account/library",
  accountSettings: "/account/settings",
  accountMembership: "/account/membership",
  signIn: "/login",
  register: "/register",
  verifyEmail: "/verify-email",
  forgotPassword: "/forgot-password",
  resetPassword: "/reset-password",
  freeResources: "/free-resources",
  resources: "/resources",
  courses: "/courses",
  membership: "/membership",
  course: (slug) => `/courses/${slug}`,
  learn: (courseSlug, lessonSlug) =>
    lessonSlug ? `/learn/${courseSlug}/${lessonSlug}` : `/learn/${courseSlug}`,
  accountLearning: "/account/learning",
  notebook: "/account/learning/notebook",
  assessmentHistory: "/account/learning/history",
  learnAssignment: (courseSlug, id) => `/learn/${courseSlug}/assignments/${id}`,
  learnSearch: "/learn/search",
  certificate: (code) => `/certificates/${code}`,
  newsletter: "/newsletter",
  newsletterConfirm: "/newsletter/confirm",
  newsletterPreferences: "/newsletter/preferences",
  newsletterUnsubscribe: "/newsletter/unsubscribe",
  resourceAccess: "/resources/access",
  partner: "/partner-with-us",
  advertise: "/advertise",
  about: "/about",
  contact: "/contact",
  privacy: "/privacy-policy",
  terms: "/terms",
  affiliate: "/affiliate-disclosure",
  cookiePolicy: "/cookie-policy",
  editorialPolicy: "/editorial-policy",
  disclaimer: "/disclaimer",
  advertisingPolicy: "/advertising-policy",
  refundPolicy: "/refund-policy",
  accessibility: "/accessibility",
  communityGuidelines: "/community-guidelines",
  copyrightPolicy: "/copyright-policy",
};

/**
 * Policy pages (Batch 13), with their key in data/legal/legalDocuments.json. Until a CMS
 * page is published at the address, the built-in page is a draft: it answers with
 * "noindex", is left out of the sitemap and is not linked from the menus. Mirrors
 * POLICY_DOCUMENTS in backend/app/cms/templates.py (a backend test checks).
 */
export const policyPages = [
  { key: "cookies", label: "Cookie Policy", path: routes.cookiePolicy },
  { key: "editorial", label: "Editorial Policy", path: routes.editorialPolicy },
  { key: "disclaimer", label: "Disclaimer", path: routes.disclaimer },
  { key: "advertising", label: "Advertising Policy", path: routes.advertisingPolicy },
  { key: "refunds", label: "Refund Policy", path: routes.refundPolicy },
  { key: "accessibility", label: "Accessibility", path: routes.accessibility },
  { key: "community", label: "Community Guidelines", path: routes.communityGuidelines },
  { key: "copyright", label: "Copyright Policy", path: routes.copyrightPolicy },
];

export const mainNav = [
  { label: "Home", href: routes.home },
  { label: "Articles", href: routes.articles },
  { label: "Shop", href: routes.shop },
  { label: "Resources", href: routes.resources },
  { label: "Newsletter", href: routes.newsletter },
  { label: "Partner With Us", href: routes.partner },
  { label: "About", href: routes.about },
];

export const footerNav = [
  {
    title: "Explore",
    items: [
      { label: "Home", href: routes.home },
      { label: "Articles", href: routes.articles },
      { label: "Authors", href: routes.authors },
      { label: "Search", href: routes.search },
      // Topic links are added from the published topics (useNavigation), never hardcoded.
    ],
  },
  {
    title: "Resources",
    items: [
      { label: "Shop", href: routes.shop },
      { label: "Courses", href: routes.courses },
      { label: "Resource Library", href: routes.resources },
      { label: "Free Resources", href: routes.freeResources },
      { label: "The Positive Reset Newsletter", href: routes.newsletter },
    ],
  },
  {
    title: "Company",
    items: [
      { label: "About", href: routes.about },
      { label: "Partner With Us", href: routes.partner },
      { label: "Contact", href: routes.contact },
    ],
  },
  {
    title: "Legal",
    items: [
      { label: "Privacy Policy", href: routes.privacy },
      { label: "Terms of Use", href: routes.terms },
      { label: "Affiliate Disclosure", href: routes.affiliate },
    ],
  },
];

/**
 * Batch 05 account addresses, kept so bookmarks and links in emails already sent keep
 * working. Each redirects (in the browser, keeping ?next= and the #token fragment) to the
 * current address; "/account/reset-password" without a token meant "forgot password".
 */
export const legacyAuthRoutes = {
  "/account/login": routes.signIn,
  "/account/register": routes.register,
  "/account/verify-email": routes.verifyEmail,
  "/account/reset-password": routes.resetPassword,
};

/** Private customer pages, prerendered as noindex shells (data loads in the browser). */
export const privateRoutes = [
  // Site search: a noindex shell; results load in the browser for each query.
  routes.search,
  routes.cart,
  routes.checkout,
  routes.checkoutComplete,
  routes.purchases,
  routes.account,
  routes.accountLibrary,
  routes.accountOrders,
  routes.accountSettings,
  routes.accountMembership,
  routes.signIn,
  routes.register,
  routes.verifyEmail,
  routes.forgotPassword,
  routes.resetPassword,
  ...Object.keys(legacyAuthRoutes),
  routes.newsletterConfirm,
  routes.newsletterPreferences,
  routes.newsletterUnsubscribe,
  routes.resourceAccess,
  routes.accountLearning,
  routes.notebook,
  routes.assessmentHistory,
];

/** Static, indexable routes (dynamic article/topic routes come from the API). */
export const staticRoutes = [
  { path: routes.home, priority: 1, changefreq: "weekly" },
  { path: routes.articles, priority: 0.9, changefreq: "daily" },
  { path: routes.authors, priority: 0.5, changefreq: "weekly" },
  { path: routes.topics, priority: 0.7, changefreq: "weekly" },
  { path: routes.shop, priority: 0.8, changefreq: "weekly" },
  { path: routes.freeResources, priority: 0.8, changefreq: "monthly" },
  { path: routes.resources, priority: 0.8, changefreq: "weekly" },
  { path: routes.courses, priority: 0.8, changefreq: "weekly" },
  { path: routes.membership, priority: 0.7, changefreq: "weekly" },
  { path: routes.newsletter, priority: 0.7, changefreq: "monthly" },
  { path: routes.partner, priority: 0.6, changefreq: "monthly" },
  { path: routes.advertise, priority: 0.5, changefreq: "monthly" },
  { path: routes.about, priority: 0.6, changefreq: "monthly" },
  { path: routes.contact, priority: 0.5, changefreq: "yearly" },
  { path: routes.privacy, priority: 0.2, changefreq: "yearly" },
  { path: routes.terms, priority: 0.2, changefreq: "yearly" },
  { path: routes.affiliate, priority: 0.2, changefreq: "yearly" },
];

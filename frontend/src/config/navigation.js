export const routes = {
  home: "/",
  articles: "/articles",
  article: (slug) => `/articles/${slug}`,
  topic: (slug) => `/topics/${slug}`,
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
};

export const mainNav = [
  { label: "Home", href: routes.home },
  { label: "Articles", href: routes.articles },
  { label: "Shop", href: routes.shop },
  { label: "Free Resources", href: routes.freeResources },
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
      { label: "Positive Mindset", href: routes.topic("positive-mindset") },
      { label: "Personal Growth", href: routes.topic("personal-growth") },
      { label: "Resilience & Starting Over", href: routes.topic("resilience-starting-over") },
    ],
  },
  {
    title: "Shop & Resources",
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
  routes.cart,
  routes.checkout,
  routes.checkoutComplete,
  routes.purchases,
  routes.account,
  routes.accountLibrary,
  routes.accountOrders,
  routes.accountSettings,
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

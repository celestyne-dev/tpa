export const routes = {
  home: "/",
  articles: "/articles",
  article: (slug) => `/articles/${slug}`,
  topic: (slug) => `/topics/${slug}`,
  shop: "/shop",
  freeResources: "/free-resources",
  newsletter: "/newsletter",
  partner: "/partner-with-us",
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

/** Static, indexable routes (dynamic article/topic routes come from the API). */
export const staticRoutes = [
  { path: routes.home, priority: 1, changefreq: "weekly" },
  { path: routes.articles, priority: 0.9, changefreq: "daily" },
  { path: routes.shop, priority: 0.8, changefreq: "weekly" },
  { path: routes.freeResources, priority: 0.8, changefreq: "monthly" },
  { path: routes.newsletter, priority: 0.7, changefreq: "monthly" },
  { path: routes.partner, priority: 0.6, changefreq: "monthly" },
  { path: routes.about, priority: 0.6, changefreq: "monthly" },
  { path: routes.contact, priority: 0.5, changefreq: "yearly" },
  { path: routes.privacy, priority: 0.2, changefreq: "yearly" },
  { path: routes.terms, priority: 0.2, changefreq: "yearly" },
  { path: routes.affiliate, priority: 0.2, changefreq: "yearly" },
];

import type { NavGroup, NavItem } from "@/types";

export const routes = {
  home: "/",
  articles: "/articles",
  article: (slug: string) => `/articles/${slug}`,
  topic: (slug: string) => `/topics/${slug}`,
  shop: "/shop",
  freeResources: "/free-resources",
  newsletter: "/newsletter",
  partner: "/partner-with-us",
  about: "/about",
  contact: "/contact",
  privacy: "/privacy-policy",
  terms: "/terms",
  affiliate: "/affiliate-disclosure",
} as const;

export const mainNav: NavItem[] = [
  { label: "Home", href: routes.home },
  { label: "Articles", href: routes.articles },
  { label: "Shop", href: routes.shop },
  { label: "Free Resources", href: routes.freeResources },
  { label: "Newsletter", href: routes.newsletter },
  { label: "Partner With Us", href: routes.partner },
  { label: "About", href: routes.about },
];

export const footerNav: NavGroup[] = [
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

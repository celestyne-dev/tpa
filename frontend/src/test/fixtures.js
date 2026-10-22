export const topics = [
  {
    slug: "positive-mindset",
    name: "Positive Mindset",
    description: "Reframe difficult moments.",
    intro: "A positive mindset is a practice.",
    icon: "sun",
    featured: true,
    article_count: 2,
  },
  {
    slug: "personal-growth",
    name: "Personal Growth",
    description: "Become more self-aware.",
    intro: "Growth happens in ordinary days.",
    icon: "sprout",
    featured: true,
    article_count: 1,
  },
  {
    slug: "emotional-well-being",
    name: "Emotional Well-being",
    description: "Care for your inner life.",
    intro: "Permission to feel.",
    icon: "leaf",
    featured: false,
    article_count: 0,
  },
];

const image = (slug) => ({
  src: `/images/articles/${slug}.svg`,
  alt: `Illustration for ${slug}`,
  width: 1600,
  height: 1000,
});

export const articles = [
  {
    id: "a1",
    slug: "reframing-negative-thoughts",
    title: "How to Reframe a Negative Thought",
    excerpt: "Realistic optimism starts with curiosity.",
    topic_slug: "positive-mindset",
    topic: { slug: "positive-mindset", name: "Positive Mindset" },
    secondary_topic_slugs: [],
    author: { slug: "tpa-editorial", name: "Think Positive Always Editorial" },
    published_at: "2026-09-22T09:00:00.000Z",
    featured: true,
    reading_time_minutes: 3,
    image: image("reframing-negative-thoughts"),
    source: "sample",
  },
  {
    id: "a2",
    slug: "designing-an-intentional-morning",
    title: "Designing an Intentional Morning",
    excerpt: "Build a routine that fits real life.",
    topic_slug: "positive-mindset",
    topic: { slug: "positive-mindset", name: "Positive Mindset" },
    secondary_topic_slugs: [],
    author: { slug: "tpa-editorial", name: "Think Positive Always Editorial" },
    published_at: "2026-09-01T09:00:00.000Z",
    featured: true,
    reading_time_minutes: 3,
    image: image("designing-an-intentional-morning"),
    source: "sample",
  },
  {
    id: "a3",
    slug: "growth-through-weekly-reflection",
    title: "Why a Weekly Reflection Helps",
    excerpt: "Fifteen minutes of honest review.",
    topic_slug: "personal-growth",
    topic: { slug: "personal-growth", name: "Personal Growth" },
    secondary_topic_slugs: [],
    author: { slug: "tpa-editorial", name: "Think Positive Always Editorial" },
    published_at: "2026-08-25T09:00:00.000Z",
    featured: false,
    reading_time_minutes: 2,
    image: image("growth-through-weekly-reflection"),
    source: "sample",
  },
];

export const articleDetail = {
  ...articles[0],
  subtitle: "Curiosity, not forced positivity.",
  tags: ["mindset"],
  canonical_url: null,
  body: [
    { type: "paragraph", text: "Thinking positively does not mean ignoring what is hard." },
    { type: "heading", text: "Notice the thought first" },
    { type: "list", ordered: true, items: ["Is it true?", "What is the evidence?"] },
    { type: "quote", text: "Your actions still matter." },
  ],
  seo: {
    og_image: { src: "/og/reframing-negative-thoughts.png", alt: "OG", width: 1200, height: 630 },
  },
};

export const products = [
  {
    id: "p1",
    slug: "know-your-worth",
    title: "Know Your Worth",
    subtitle: "Confidence from the inside out",
    description: "An encouraging guide.",
    format: "eBook",
    availability: "coming-soon",
    topic_slugs: ["positive-mindset"],
    highlights: ["Exercises"],
    cover_theme: "olive",
  },
];

export const site = {
  name: "Think Positive Always",
  community: {
    linkedin_followers_label: "280,000+",
    linkedin_followers_text: "more than 280,000 people",
  },
  newsletter: { name: "The Positive Reset", cadence: "weekly", is_open: false },
  contact: { email: null, partnerships_email: null },
  social_links: [],
  media_kit_url: null,
};

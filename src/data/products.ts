import type { ProductPreview } from "@/types";

/**
 * Planned digital products. All are upcoming — no prices, ratings, reviews
 * or purchase actions until the real catalog and checkout ship (Batch 04).
 */
export const products: ProductPreview[] = [
  {
    id: "prd-power-of-starting-again",
    slug: "the-power-of-starting-again",
    title: "The Power of Starting Again",
    subtitle: "A guide to rebuilding with hope and intention",
    description:
      "A compassionate, practical guide for anyone facing a new chapter after loss, change, or disappointment, with reflections and steps to help you rebuild at your own pace.",
    format: "eBook",
    availability: "coming-soon",
    topicSlugs: ["resilience-starting-over", "personal-growth"],
    highlights: [
      "Reflections for processing endings honestly",
      "Practical steps for rebuilding routines and direction",
      "Prompts to reconnect with your values and hopes",
    ],
    coverTheme: "sage",
  },
  {
    id: "prd-30-day-positive-mindset-reset",
    slug: "the-30-day-positive-mindset-reset",
    title: "The 30-Day Positive Mindset Reset",
    subtitle: "Daily prompts for a calmer, more hopeful outlook",
    description:
      "A guided 30-day workbook with short daily exercises to help you notice unhelpful thought patterns, practise gratitude, and build a more balanced perspective.",
    format: "Workbook",
    availability: "coming-soon",
    topicSlugs: ["positive-mindset", "habits-intentional-living"],
    highlights: [
      "One focused exercise for each day",
      "Space to journal and track what you notice",
      "Weekly reflections to consolidate progress",
    ],
    coverTheme: "gold",
  },
  {
    id: "prd-know-your-worth",
    slug: "know-your-worth",
    title: "Know Your Worth",
    subtitle: "Building confidence from the inside out",
    description:
      "An encouraging guide to recognising your value, setting healthy boundaries, and building confidence that does not depend on other people's approval.",
    format: "eBook",
    availability: "coming-soon",
    topicSlugs: ["confidence-self-worth", "relationships-boundaries"],
    highlights: [
      "Exercises for quieting the inner critic",
      "Guidance on boundaries and self-respect",
      "Reflection prompts for everyday confidence",
    ],
    coverTheme: "olive",
  },
  {
    id: "prd-stronger-than-your-setbacks",
    slug: "stronger-than-your-setbacks",
    title: "Stronger Than Your Setbacks",
    subtitle: "A resilience workbook for difficult seasons",
    description:
      "A practical workbook for navigating setbacks with more steadiness, with tools to reframe challenges, care for yourself under pressure, and take your next step forward.",
    format: "Workbook",
    availability: "coming-soon",
    topicSlugs: ["resilience-starting-over", "emotional-well-being"],
    highlights: [
      "Tools for reframing obstacles",
      "Self-care planning for stressful periods",
      "Action plans for moving forward",
    ],
    coverTheme: "charcoal",
  },
];

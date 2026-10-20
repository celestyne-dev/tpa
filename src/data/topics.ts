import type { Topic } from "@/types";

/** Local topic data. Will be replaced by CMS queries in a later batch. */
export const topics: Topic[] = [
  {
    slug: "positive-mindset",
    name: "Positive Mindset",
    description:
      "Reframe difficult moments and train your attention toward what helps you move forward.",
    intro:
      "A positive mindset is not about ignoring hard things. It is the practice of noticing your thoughts, questioning the unhelpful ones, and choosing a perspective that gives you room to act. These articles explore realistic optimism, gratitude, and the small mental habits that shape a brighter outlook.",
    icon: "sun",
    featured: true,
  },
  {
    slug: "personal-growth",
    name: "Personal Growth",
    description: "Thoughtful ideas for becoming more self-aware, capable, and true to who you are.",
    intro:
      "Personal growth happens in ordinary days: in the questions you ask yourself, the feedback you are willing to hear, and the commitments you keep. Explore reflections and practical guidance for growing with intention rather than pressure.",
    icon: "sprout",
    featured: true,
  },
  {
    slug: "confidence-self-worth",
    name: "Confidence & Self-Worth",
    description:
      "Build steady confidence that does not depend on approval, comparison, or perfection.",
    intro:
      "Confidence grows from evidence, self-respect, and the willingness to try before you feel ready. These articles help you recognise your worth, quiet the inner critic, and show up as yourself with more ease.",
    icon: "gem",
    featured: true,
  },
  {
    slug: "resilience-starting-over",
    name: "Resilience & Starting Over",
    description:
      "Encouragement and practical steps for rebuilding after setbacks, loss, and change.",
    intro:
      "Every life includes chapters that end before we are ready. Resilience is the ability to feel what happened, find your footing, and begin again. Here you will find honest encouragement and steady, practical guidance for starting over.",
    icon: "sunrise",
    featured: true,
  },
  {
    slug: "relationships-boundaries",
    name: "Relationships & Boundaries",
    description:
      "Navigate connection with clarity, kindness, and healthy limits that protect your peace.",
    intro:
      "Healthy relationships need both warmth and boundaries. Explore how to communicate needs clearly, let go of guilt for protecting your energy, and build connections grounded in mutual respect.",
    icon: "heart-handshake",
    featured: true,
  },
  {
    slug: "habits-intentional-living",
    name: "Habits & Intentional Living",
    description: "Design simple routines and daily choices that reflect what matters most to you.",
    intro:
      "Intentional living is about aligning your days with your values. These articles cover sustainable habits, mindful routines, and gentle ways to simplify so you have more energy for what matters.",
    icon: "calendar-check",
    featured: true,
  },
  {
    slug: "motivation-inspiration",
    name: "Motivation & Inspiration",
    description:
      "Fresh perspective and encouragement for the days when you need a reason to keep going.",
    intro:
      "Motivation rises and falls. Inspiration can help you reconnect with your reasons and take the next small step. Find perspective, encouragement, and ideas to keep moving when progress feels slow.",
    icon: "flame",
    featured: false,
  },
  {
    slug: "emotional-well-being",
    name: "Emotional Well-being",
    description: "Gentle guidance for understanding your emotions and caring for your inner life.",
    intro:
      "Emotional well-being begins with permission to feel. Explore ways to name your emotions, respond to stress with compassion, and build a calmer relationship with yourself. This content is educational and is not a substitute for professional care.",
    icon: "leaf",
    featured: false,
  },
];

import type { Article } from "@/types";
import { editorialTeam } from "./_shared";

export const growthThroughReflection: Article = {
  id: "sample-006",
  slug: "growth-through-weekly-reflection",
  title: "Why a Weekly Reflection Can Change the Way You Grow",
  subtitle: "Fifteen minutes of honest review can turn busy weeks into meaningful progress.",
  excerpt:
    "Growth does not only happen when we push forward. It also happens when we pause long enough to notice what we are learning. A weekly reflection makes that pause a habit.",
  topicSlug: "personal-growth",
  secondaryTopicSlugs: ["habits-intentional-living"],
  tags: ["reflection", "journaling", "self-awareness"],
  author: editorialTeam,
  publishedAt: "2026-08-25T09:00:00.000Z",
  status: "published",
  featured: false,
  image: {
    src: "/images/articles/growth-through-weekly-reflection.svg",
    alt: "Abstract illustration of an open journal with a sprouting stem",
    width: 1600,
    height: 1000,
  },
  source: "sample",
  body: [
    {
      type: "paragraph",
      text: "Weeks can pass in a blur of tasks, messages, and obligations. We stay busy, yet it can be hard to say what we actually learned or how we have grown. A short weekly reflection gives you a chance to step back, notice patterns, and make thoughtful adjustments.",
    },
    { type: "heading", text: "Why reflection matters" },
    {
      type: "paragraph",
      text: "Experience alone does not guarantee growth. Reflection is what turns experience into insight. When you look back on your week with honesty and curiosity, you begin to see what gives you energy, what drains it, and where your choices align with the person you want to become.",
    },
    { type: "heading", text: "Five questions to guide you" },
    {
      type: "list",
      ordered: true,
      items: [
        "What went well this week, and what helped it go well?",
        "What felt difficult, and what did it teach me?",
        "When did I feel most like myself?",
        "What do I want to do differently next week?",
        "What am I grateful for right now?",
      ],
    },
    {
      type: "paragraph",
      text: "You do not need to answer every question every week. Choose the two or three that feel most relevant and write freely for a few minutes.",
    },
    {
      type: "quote",
      text: "Looking back with kindness is one of the most practical ways to move forward with wisdom.",
    },
    { type: "heading", text: "Make it easy to return to" },
    {
      type: "paragraph",
      text: "Choose a consistent time, such as Sunday evening or Friday afternoon, and keep your notes in one place. A simple notebook works well. Over time, those pages become a record of your growth that you can revisit when you need perspective or encouragement.",
    },
    { type: "heading", text: "Be honest, and be kind" },
    {
      type: "paragraph",
      text: "Reflection is not an opportunity to criticise yourself. If something went poorly, describe it plainly and look for the lesson. Treat yourself the way a supportive mentor would: honest about what needs attention, and generous about the effort you are making.",
    },
    {
      type: "paragraph",
      text: "Try it this week. Set aside fifteen minutes, answer a few questions, and notice how it feels to end the week with intention rather than exhaustion.",
    },
  ],
};

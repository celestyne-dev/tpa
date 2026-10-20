import type { Article } from "@/types";
import { editorialTeam } from "./_shared";

export const boundariesWithoutGuilt: Article = {
  id: "sample-004",
  slug: "setting-boundaries-without-guilt",
  title: "Setting Boundaries Without Carrying the Guilt",
  subtitle: "Healthy limits are not walls. They are the foundation for honest connection.",
  excerpt:
    "Saying no can feel uncomfortable, especially to people you care about. Learn why boundaries protect your relationships and how to set them with clarity and kindness.",
  topicSlug: "relationships-boundaries",
  secondaryTopicSlugs: ["confidence-self-worth"],
  tags: ["boundaries", "relationships", "communication"],
  author: editorialTeam,
  publishedAt: "2026-09-08T09:00:00.000Z",
  status: "published",
  featured: true,
  image: {
    src: "/images/articles/setting-boundaries-without-guilt.svg",
    alt: "Abstract illustration of two overlapping circles in sage and gold",
    width: 1600,
    height: 1000,
  },
  source: "sample",
  body: [
    {
      type: "paragraph",
      text: "Many people struggle to set boundaries because they worry about disappointing others. Saying yes feels kinder in the moment, even when it leaves us exhausted, resentful, or stretched too thin. Over time, though, a lack of boundaries can quietly damage the very relationships we were trying to protect.",
    },
    { type: "heading", text: "What a boundary really is" },
    {
      type: "paragraph",
      text: "A boundary is a clear statement of what you will and will not do. It is not a demand that someone else change. 'You need to stop calling me so late' is a request. 'I am not available for calls after 9 p.m.; I will reply the next morning' is a boundary, because it describes your own action.",
    },
    { type: "heading", text: "Why guilt shows up" },
    {
      type: "paragraph",
      text: "Guilt often appears when we act differently from what others expect or from roles we have played for years. Feeling guilty does not necessarily mean you have done something wrong. Sometimes it simply means you are doing something new.",
    },
    {
      type: "quote",
      text: "A boundary that protects your peace is not an act of rejection. It is an act of honesty.",
    },
    { type: "heading", text: "A simple framework" },
    {
      type: "list",
      ordered: true,
      items: [
        "Get clear on what you need and why it matters to you.",
        "State it briefly and kindly, without over-explaining.",
        "Describe what you will do, not what they must do.",
        "Follow through consistently, even when it is uncomfortable.",
      ],
    },
    {
      type: "paragraph",
      text: "For example: 'I would love to help, but I cannot take this on this week. I could help next Thursday if that works.' It is warm, clear, and honest about your capacity.",
    },
    { type: "heading", text: "Expect some adjustment" },
    {
      type: "paragraph",
      text: "When you begin setting boundaries, some people may be surprised. That is normal. Most healthy relationships adapt and even improve, because both people know where they stand. If someone consistently ignores or punishes your boundaries, that is important information about the relationship.",
    },
    { type: "heading", text: "Start small" },
    {
      type: "paragraph",
      text: "You do not need to overhaul every relationship overnight. Choose one area where a boundary would make a meaningful difference, perhaps your evenings, your weekends, or a recurring request, and practise there first. Each time you honour your own limits, it becomes a little easier, and the guilt a little lighter.",
    },
  ],
};

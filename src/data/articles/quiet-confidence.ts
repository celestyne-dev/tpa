import type { Article } from "@/types";
import { editorialTeam } from "./_shared";

export const quietConfidence: Article = {
  id: "sample-003",
  slug: "building-quiet-confidence",
  title: "Building Quiet Confidence That Does Not Need Applause",
  subtitle: "Steady self-belief grows from evidence, self-respect, and kept promises.",
  excerpt:
    "Confidence is often mistaken for loudness. The most durable kind is quieter: a steady sense that you can handle what comes, even without anyone else's approval.",
  topicSlug: "confidence-self-worth",
  secondaryTopicSlugs: ["personal-growth"],
  tags: ["confidence", "self-worth", "self-trust"],
  author: editorialTeam,
  publishedAt: "2026-09-15T09:00:00.000Z",
  status: "published",
  featured: true,
  image: {
    src: "/images/articles/building-quiet-confidence.svg",
    alt: "Abstract illustration of a single olive leaf beside a calm circular form",
    width: 1600,
    height: 1000,
  },
  source: "sample",
  body: [
    {
      type: "paragraph",
      text: "When we picture confidence, we often imagine someone commanding a room: speaking first, never hesitating, seemingly free of doubt. But many genuinely confident people are calm rather than loud. Their confidence is not a performance. It is a quiet trust in themselves.",
    },
    { type: "heading", text: "Confidence follows action" },
    {
      type: "paragraph",
      text: "A common trap is waiting to feel confident before trying something new. In practice, the order is usually reversed. We act, we survive the discomfort, we learn, and confidence grows from the evidence. Each time you do something slightly outside your comfort zone, you add to a private record that says: I can handle this.",
    },
    { type: "heading", text: "Keep small promises to yourself" },
    {
      type: "paragraph",
      text: "Self-trust works much like trust in any relationship. It grows when promises are kept. If you regularly tell yourself you will do something and then do not, part of you learns not to believe your own word. Start with commitments so small they are almost impossible to break, then build from there.",
    },
    { type: "heading", text: "Separate your worth from your results" },
    {
      type: "paragraph",
      text: "Your performance on a given day is information about that day. It is not a verdict on your value as a person. When you can hold that distinction, mistakes become less threatening, and you become more willing to take the risks that growth requires.",
    },
    {
      type: "list",
      items: [
        "Notice when you link a single outcome to your whole identity.",
        "Replace 'I am a failure' with 'That attempt did not work.'",
        "Remember qualities you value in yourself that have nothing to do with achievement.",
      ],
    },
    {
      type: "quote",
      text: "You do not have to earn the right to take up space. You only have to decide to stop shrinking.",
    },
    { type: "heading", text: "Limit the comparison loop" },
    {
      type: "paragraph",
      text: "Comparison can quietly erode confidence, especially when we compare our everyday reality to someone else's highlights. Try comparing yourself with who you were a year ago instead. What have you learned? What can you do now that once felt difficult?",
    },
    { type: "heading", text: "A practice for this week" },
    {
      type: "paragraph",
      text: "Each evening, write down one thing you did that took a little courage, no matter how small. Speaking up in a meeting, setting a boundary, trying something unfamiliar. At the end of the week, read the list. That is your evidence. That is what quiet confidence is made of.",
    },
  ],
};

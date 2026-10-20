import type { Article } from "@/types";
import { editorialTeam } from "./_shared";

export const intentionalMornings: Article = {
  id: "sample-005",
  slug: "designing-an-intentional-morning",
  title: "Designing an Intentional Morning You Will Actually Keep",
  subtitle: "Forget the perfect routine. Build one that fits your real life.",
  excerpt:
    "The best morning routine is not the one with the most steps. It is the one that helps you start the day feeling grounded, and that you can return to even on busy days.",
  topicSlug: "habits-intentional-living",
  secondaryTopicSlugs: ["positive-mindset"],
  tags: ["habits", "routines", "intentional living"],
  author: editorialTeam,
  publishedAt: "2026-09-01T09:00:00.000Z",
  status: "published",
  featured: true,
  image: {
    src: "/images/articles/designing-an-intentional-morning.svg",
    alt: "Abstract illustration of a rising sun framed by a window arch",
    width: 1600,
    height: 1000,
  },
  source: "sample",
  body: [
    {
      type: "paragraph",
      text: "Online, morning routines can look elaborate: early alarms, long workouts, meditation, journaling, cold showers, and a carefully prepared breakfast. For most people, that is not realistic every day. The good news is that an intentional morning does not need to be long. It needs to be yours.",
    },
    { type: "heading", text: "Start with how you want to feel" },
    {
      type: "paragraph",
      text: "Instead of copying someone else's checklist, ask how you would like to feel by the time your day properly begins. Calm? Focused? Energised? Connected? Your answer helps you choose activities that serve a purpose rather than adding tasks for their own sake.",
    },
    { type: "heading", text: "Choose one anchor habit" },
    {
      type: "paragraph",
      text: "An anchor habit is a single, simple practice you do most mornings, regardless of how the rest of the day unfolds. It might be drinking a glass of water before checking your phone, stepping outside for a few minutes of daylight, or writing one intention for the day.",
    },
    {
      type: "list",
      items: [
        "Pick something that takes five minutes or less.",
        "Attach it to something you already do, such as making coffee.",
        "Keep it the same for at least two weeks before adding more.",
      ],
    },
    { type: "heading", text: "Protect the first few minutes" },
    {
      type: "paragraph",
      text: "For many of us, the phone is the first thing we reach for. Messages, news, and notifications can pull us into other people's priorities before we have had a chance to set our own. Even delaying screens by ten minutes can make the start of the day feel noticeably calmer.",
    },
    {
      type: "quote",
      text: "How you begin the day does not decide everything, but it gives you a steadier place to begin from.",
    },
    { type: "heading", text: "Have a minimum version" },
    {
      type: "paragraph",
      text: "Some mornings will be rushed. Children need attention, you oversleep, or work starts early. Decide in advance what the minimum version of your routine looks like, perhaps one deep breath and one intention. Keeping the habit alive, even briefly, matters more than doing it perfectly.",
    },
    { type: "heading", text: "Review and adjust" },
    {
      type: "paragraph",
      text: "At the end of each week, ask what helped and what felt like a chore. Keep what works and let go of the rest. An intentional morning is not a fixed formula; it evolves as your life does.",
    },
  ],
};

import type { Article } from "@/types";
import { editorialTeam } from "./_shared";

export const reframingNegativeThoughts: Article = {
  id: "sample-002",
  slug: "reframing-negative-thoughts",
  title: "How to Reframe a Negative Thought Without Pretending",
  subtitle: "Realistic optimism starts with curiosity, not forced positivity.",
  excerpt:
    "Thinking positively does not mean ignoring what is hard. It means learning to question unhelpful thoughts and choose a perspective that gives you room to act.",
  topicSlug: "positive-mindset",
  secondaryTopicSlugs: ["emotional-well-being"],
  tags: ["mindset", "reframing", "realistic optimism"],
  author: editorialTeam,
  publishedAt: "2026-09-22T09:00:00.000Z",
  status: "published",
  featured: true,
  image: {
    src: "/images/articles/reframing-negative-thoughts.svg",
    alt: "Abstract illustration of a warm gold sun partly hidden behind soft clouds",
    width: 1600,
    height: 1000,
  },
  source: "sample",
  body: [
    {
      type: "paragraph",
      text: "Most of us have heard the advice to 'just think positive.' It sounds simple, but when you are disappointed, worried, or exhausted, being told to look on the bright side can feel dismissive. A healthier approach is not to replace every negative thought with a cheerful one. It is to look at your thoughts with curiosity and ask whether they are telling the whole story.",
    },
    { type: "heading", text: "Notice the thought first" },
    {
      type: "paragraph",
      text: "Thoughts often arrive so quickly that they feel like facts. 'I always mess this up.' 'Nobody cares what I think.' 'Things never work out for me.' The first step is simply to notice the thought and name it: I am having the thought that I always mess this up.",
    },
    {
      type: "paragraph",
      text: "That small shift creates distance. You are no longer inside the thought; you are observing it. From there, you can decide what to do with it.",
    },
    { type: "heading", text: "Ask three honest questions" },
    {
      type: "list",
      ordered: true,
      items: [
        "Is this thought completely true, or is it partly true?",
        "What evidence do I have for and against it?",
        "What would I say to a friend who had this thought?",
      ],
    },
    {
      type: "paragraph",
      text: "These questions are not designed to talk you out of real problems. They help you separate the situation from the story you are telling about it. Often you will find that 'always' was really 'sometimes,' and 'never' was really 'not yet.'",
    },
    { type: "heading", text: "Choose a more balanced alternative" },
    {
      type: "paragraph",
      text: "A useful reframe is believable. If 'I am amazing at everything' feels false, your mind will reject it. Try something balanced instead: 'This did not go the way I hoped, and I can learn from it.' Or: 'I am finding this difficult, and I have handled difficult things before.'",
    },
    {
      type: "quote",
      text: "Realistic optimism is the belief that, while things may be hard, your actions still matter.",
    },
    { type: "heading", text: "Turn perspective into action" },
    {
      type: "paragraph",
      text: "The value of a reframe is that it opens up possibilities. Once your thought shifts from 'this is hopeless' to 'this is hard, and there is something I can try,' ask yourself what that something is. A helpful perspective should lead naturally to a next step, however small.",
    },
    { type: "heading", text: "Practise, do not perfect" },
    {
      type: "paragraph",
      text: "Like any skill, reframing gets easier with practice. You might try it once a day, perhaps by writing down one difficult thought each evening and working through the three questions. Over time, you may notice that you catch unhelpful patterns sooner and recover from them more quickly.",
    },
    {
      type: "paragraph",
      text: "A positive mindset is not a mood you must maintain. It is a practice you can return to, especially on the days when it is hardest.",
    },
  ],
};

/**
 * Static marketing copy for public pages. Dynamic content (articles, topics,
 * products, site settings) comes from the Flask API.
 */
import {
  BookOpen,
  Compass,
  Download,
  Handshake,
  HeartHandshake,
  Leaf,
  Lightbulb,
  Megaphone,
  Newspaper,
  PenTool,
  ShieldCheck,
  Sparkles,
  Sprout,
  Sun,
} from "lucide-react";

export const partnershipFormats = [
  {
    icon: PenTool,
    title: "Sponsored content",
    text: "Thoughtful articles and posts that share your message in a way that genuinely serves our readers.",
  },
  {
    icon: Sparkles,
    title: "Brand storytelling",
    text: "Collaborative stories that connect your brand's purpose with themes of growth, resilience, and well-being.",
  },
  {
    icon: Megaphone,
    title: "Digital campaigns",
    text: "Multi-channel campaigns designed around a shared goal, from awareness to community engagement.",
  },
  {
    icon: Newspaper,
    title: "Newsletter sponsorships",
    text: "Placement in The Positive Reset, our daily email, once the newsletter has launched.",
  },
  {
    icon: Handshake,
    title: "Resource partnerships",
    text: "Co-created guides, challenges, or tools that offer real value to people investing in their growth.",
  },
];

export const brandAlignment = [
  "Products, services, or causes that support well-being, growth, learning, or positive change.",
  "A commitment to honest claims and respectful, inclusive messaging.",
  "Respect for our audience: no misleading offers, pressure tactics, or harmful products.",
  "Willingness to clearly disclose sponsored and affiliate relationships.",
];

/** "What you'll receive" on the /newsletter page. */
export const newsletterReceive = [
  {
    icon: Sun,
    title: "Daily Encouragement",
    text: "A few warm, honest words to help you begin the day with steadier footing and a little more hope.",
  },
  {
    icon: Leaf,
    title: "Mindset & Wellbeing",
    text: "Gentle ideas for calmer thinking, kinder self-talk and looking after your energy.",
  },
  {
    icon: Sprout,
    title: "Personal Growth",
    text: "Reflections and prompts that help you build confidence, habits and direction over time.",
  },
  {
    icon: Lightbulb,
    title: "Practical Wisdom",
    text: "One small, realistic step you can try in a few minutes, plus useful articles and free resources.",
  },
];

/**
 * The shape of a typical Positive Reset email, shown on /newsletter. Written as an
 * illustration of the format; it is not, and is not presented as, a past issue.
 */
export const dailyResetExample = [
  {
    label: "Today's thought",
    text: "Progress rarely announces itself. Most days it looks like showing up, doing a little, and being patient with yourself.",
  },
  {
    label: "A moment to reflect",
    text: "What is one thing you handled well recently that you haven't given yourself credit for?",
  },
  {
    label: "One small step",
    text: "Before you open your messages, take two slow breaths and choose the one task that matters most today.",
  },
  {
    label: "Something useful",
    text: "A link to a Think Positive Always article or free resource that goes deeper on the day's theme.",
  },
];

export const shopPromise = [
  {
    icon: BookOpen,
    title: "Thoughtfully written",
    text: "Original content created with care, combining encouragement with practical guidance.",
  },
  {
    icon: Sparkles,
    title: "Built for action",
    text: "Prompts, exercises, and reflections that help you apply what you read.",
  },
  {
    icon: Download,
    title: "Digital delivery",
    text: "Purchased resources stay in your account library, ready to download again whenever you need them.",
  },
  {
    icon: ShieldCheck,
    title: "Secure checkout",
    text: "Payments are handled on Paystack's secure hosted page. We never see or store your card details.",
  },
];

export const aboutValues = [
  {
    icon: HeartHandshake,
    title: "Honest encouragement",
    text: "We believe in hope that tells the truth. Our content acknowledges real challenges and meets people where they are.",
  },
  {
    icon: Lightbulb,
    title: "Practical wisdom",
    text: "Inspiration should be useful. We focus on ideas, tools, and small steps that people can apply in everyday life.",
  },
  {
    icon: Sprout,
    title: "Growth at your own pace",
    text: "Personal growth is not a race. We encourage progress over perfection and self-compassion over pressure.",
  },
  {
    icon: Compass,
    title: "Inclusive by design",
    text: "Think Positive Always is for adults of every gender, background, and stage of life who want to grow with intention.",
  },
];

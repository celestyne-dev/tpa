/**
 * Static marketing copy for public pages. Dynamic content (articles, topics,
 * products, site settings) comes from the Flask API.
 */
import {
  BookOpen,
  Download,
  Leaf,
  Lightbulb,
  ShieldCheck,
  Sparkles,
  Sprout,
  Sun,
} from "lucide-react";

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

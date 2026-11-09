/**
 * Copy for the built-in company pages. The same wording is in the CMS page templates
 * (backend/app/cms/templates.py), so a page created from a template starts identical.
 * Nothing here states figures, achievements or biography details: audience figures come
 * only from verified, dated measurements (Partnerships › Audience metrics).
 */
import {
  BookOpen,
  Handshake,
  MessageCircle,
  PenLine,
  ShieldCheck,
  Users,
  HeartHandshake,
} from "lucide-react";

export { aboutValues, brandAlignment, partnershipFormats } from "./marketing";

export const aboutIntro =
  "Practical inspiration for a stronger mindset, more confidence, and intentional personal growth.";

export const DEFAULT_MISSION =
  "Helping people develop a healthier mindset, navigate life's challenges, build confidence, and move forward through encouragement, thoughtful content, and useful personal development tools.";

export const DEFAULT_COMMUNITY =
  "more than 280,000 people who follow Think Positive Always on LinkedIn";

export const beliefLine =
  "We believe that thinking positively is not about pretending life is easy. It is about choosing a perspective that helps you keep going, and pairing that perspective with practical steps that make a real difference.";

export const whoWeServe =
  "Our readers are adults around the world who want to build a healthier mindset, strengthen their confidence, recover from setbacks, nurture better relationships, and live more intentionally. Some are navigating a difficult season. Others simply want to keep growing. All are welcome here.";

export const editorialApproach = [
  {
    icon: BookOpen,
    title: "Written to encourage and educate",
    text: "Our articles and resources are designed to encourage and educate.",
  },
  {
    icon: ShieldCheck,
    title: "Not a substitute for professional advice",
    text: "Our content is not a substitute for professional medical, psychological, or financial advice. If you are struggling, please reach out to a qualified professional.",
  },
  {
    icon: Handshake,
    title: "Partnerships clearly labelled",
    text: "When content is sponsored or created in partnership with a brand, it will be clearly labelled. Sponsorship does not guarantee a positive review, and our editorial opinions remain our own.",
  },
];

export const contactCards = [
  {
    key: "general",
    icon: MessageCircle,
    title: "General inquiries",
    text: "For questions, feedback, or support, email us.",
    email: "general",
  },
  {
    key: "editorial",
    icon: PenLine,
    title: "Editorial feedback and corrections",
    text: "Spotted something that needs correcting, or have feedback on an article? Let us know, including the article's title or link.",
    email: "general",
    subject: "Editorial feedback",
  },
  {
    key: "partnerships",
    icon: Handshake,
    title: "Advertising and partnerships",
    text: "Interested in collaborating with Think Positive Always? Learn about partnership formats and how to make an inquiry.",
    email: "partnerships",
    subject: "Partnership inquiry",
    action: { label: "Partner with us", href: "/partner-with-us" },
  },
];

export const contactFallback =
  "We are setting up dedicated contact channels for the new website. They will be published on this page shortly.";

export const urgentSupport =
  "Think Positive Always is not a crisis or counselling service. If you are in immediate danger or need urgent emotional support, please contact your local emergency services or a licensed mental health professional. In the United States, you can call or text 988 to reach the 988 Suicide & Crisis Lifeline.";

export const partnerIntro =
  "We collaborate with brands, organisations, and publishers who share our belief that encouragement and practical tools can help people live better lives.";

export const partnerAudience = [
  "Think Positive Always speaks to an international, primarily English-speaking audience, including readers across the United States. Our community is made up of adults of all genders who are interested in mindset, confidence, resilience, relationships, and intentional living.",
  "They come to us for encouragement and practical perspective, which is why we only partner on messages we believe will be genuinely useful to them.",
];

export const partnerReasons = [
  {
    icon: Users,
    title: "An audience focused on growth",
    text: "Adults interested in mindset, confidence, resilience, relationships, and intentional living.",
  },
  {
    icon: HeartHandshake,
    title: "Trust comes first",
    text: "Readers come to us for encouragement and practical perspective, so we only partner on messages we believe will be genuinely useful to them.",
  },
  {
    icon: ShieldCheck,
    title: "Transparent by default",
    text: "Sponsored content is clearly labelled, and paid and affiliate links are marked as sponsored links for search engines.",
  },
];

export const metricsNote =
  "Each figure is a measurement taken on the date shown, not a live count. Social media followers are not website visitors.";

export const METRIC_GROUPS = {
  social: ["social_followers"],
  website: ["website_users", "website_pageviews"],
  newsletter: ["newsletter_subscribers", "email_open_rate"],
};

export const byGroup = (metrics, group) =>
  (metrics ?? []).filter((m) => !group || METRIC_GROUPS[group]?.includes(m.metric_type));

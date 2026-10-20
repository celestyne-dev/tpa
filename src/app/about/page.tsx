import { ArrowRight, Compass, HeartHandshake, Lightbulb, Sprout } from "lucide-react";
import type { Metadata } from "next";
import { TopicCard } from "@/components/topics/topic-card";
import { ButtonLink } from "@/components/ui/button";
import { IconFeature } from "@/components/ui/icon-feature";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { getTopics } from "@/lib/content";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "About Think Positive Always",
  description:
    "Think Positive Always offers practical inspiration for a stronger mindset, more confidence, and intentional personal growth. Learn what we stand for and who we serve.",
  path: routes.about,
});

const values = [
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

export default async function AboutPage() {
  const topics = await getTopics();
  return (
    <>
      <PageHeader
        eyebrow="About us"
        title="Practical Inspiration for Real Life"
        description={siteConfig.tagline}
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "About", href: routes.about },
        ]}
      />

      <Section aria-labelledby="story-heading">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.3fr] lg:gap-20">
          <SectionHeading id="story-heading" eyebrow="What we stand for" title="Our mission" />
          <div className="space-y-6 text-lg text-muted">
            <p className="font-serif text-2xl leading-snug text-charcoal">{siteConfig.mission}</p>
            <p>
              Think Positive Always began as a place for daily encouragement and has grown into a
              community of {siteConfig.community.linkedinFollowersText}, with audiences on other
              social platforms as well. This website is our new home: a place to go deeper than a
              single post and offer thoughtful articles and practical resources.
            </p>
            <p>
              We believe that thinking positively is not about pretending life is easy. It is about
              choosing a perspective that helps you keep going, and pairing that perspective with
              practical steps that make a real difference.
            </p>
          </div>
        </div>
      </Section>

      <Section tone="cream" aria-labelledby="who-heading">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-20">
          <div>
            <SectionHeading
              id="who-heading"
              eyebrow="Who we serve"
              title="For anyone ready to grow"
            />
            <p className="mt-6 text-lg text-muted">
              Our readers are adults around the world who want to build a healthier mindset,
              strengthen their confidence, recover from setbacks, nurture better relationships, and
              live more intentionally. Some are navigating a difficult season. Others simply want to
              keep growing. All are welcome here.
            </p>
          </div>
          <ul className="grid gap-8 sm:grid-cols-2">
            {values.map((v) => (
              <li key={v.title}>
                <IconFeature icon={v.icon} title={v.title} className="flex-col">
                  {v.text}
                </IconFeature>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      <Section aria-labelledby="about-topics-heading">
        <SectionHeading
          id="about-topics-heading"
          eyebrow="What we write about"
          title="The topics at the heart of our work"
        />
        <ul className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {topics.map((t) => (
            <li key={t.slug}>
              <TopicCard topic={t} />
            </li>
          ))}
        </ul>
      </Section>

      <Section
        tone="beige"
        size="narrow"
        containerClassName="text-center"
        aria-labelledby="about-cta-heading"
      >
        <h2 id="about-cta-heading" className="text-3xl font-medium sm:text-4xl">
          A note on our content
        </h2>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-muted">
          Our articles and resources are designed to encourage and educate. They are not a
          substitute for professional medical, psychological, or financial advice. If you are
          struggling, please reach out to a qualified professional.
        </p>
        <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
          <ButtonLink href={routes.articles}>
            Read our articles
            <ArrowRight aria-hidden />
          </ButtonLink>
          <ButtonLink href={routes.contact} variant="outline">
            Get in touch
          </ButtonLink>
        </div>
      </Section>
    </>
  );
}

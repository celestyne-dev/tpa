import { ArrowRight } from "lucide-react";
import { Seo } from "@/components/seo/Seo";
import { TopicGrid } from "@/components/topics/TopicGrid";
import { ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconFeature } from "@/components/ui/IconFeature";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { aboutValues } from "@/data/marketing";
import { useSite, useTopics } from "@/hooks/useContent";

const DEFAULT_MISSION =
  "Helping people develop a healthier mindset, navigate life's challenges, build confidence, and move forward through encouragement, thoughtful content, and useful personal development tools.";

export function AboutPage() {
  const { data: site } = useSite();
  const topics = useTopics();
  return (
    <>
      <Seo
        title="About Think Positive Always"
        description="Think Positive Always offers practical inspiration for a stronger mindset, more confidence, and intentional personal growth. Learn what we stand for and who we serve."
        path={routes.about}
      />
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
            <p className="font-serif text-2xl leading-snug text-charcoal">
              {site?.mission ?? DEFAULT_MISSION}
            </p>
            <p>
              Think Positive Always began as a place for daily encouragement and has grown into a
              community of{" "}
              {site?.community?.linkedin_followers_text ??
                "more than 280,000 people who follow Think Positive Always on LinkedIn"}
              , with audiences on other social platforms as well. This website is our new home: a
              place to go deeper than a single post and offer thoughtful articles and practical
              resources.
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
            {aboutValues.map((v) => (
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
        <div className="mt-12">
          {topics.isLoading && <CardGridSkeleton count={4} className="lg:grid-cols-4" />}
          {topics.isError && (
            <ErrorState onRetry={topics.retry} title="We couldn't load the topics" />
          )}
          {topics.data && <TopicGrid topics={topics.data} className="lg:grid-cols-4" />}
        </div>
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
          <ButtonLink to={routes.articles}>
            Read our articles
            <ArrowRight aria-hidden />
          </ButtonLink>
          <ButtonLink to={routes.contact} variant="outline">
            Get in touch
          </ButtonLink>
        </div>
      </Section>
    </>
  );
}

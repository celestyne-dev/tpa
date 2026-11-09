import { ArrowRight, Quote } from "lucide-react";
import { Link } from "react-router";
import {
  ActionLink,
  CompanyHero,
  CtaBand,
  IconCard,
  MetricCards,
} from "@/components/company/CompanyUI";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { routes } from "@/config/navigation";
import {
  DEFAULT_COMMUNITY,
  DEFAULT_MISSION,
  aboutIntro,
  aboutValues,
  beliefLine,
  editorialApproach,
  metricsNote,
  whoWeServe,
} from "@/data/companyPages";
import { useMediaKit, useSite, useTopics } from "@/hooks/useContent";
import { webPageJsonLd } from "@/utils/structuredData";

/**
 * The built-in About page. Every section is also available in the Page Builder (the
 * "About page" template): publishing a CMS page at /about replaces this one. The mission
 * and community wording come from Settings; audience figures appear only when verified,
 * dated measurements are published in the media kit.
 */
export function AboutPage() {
  const { data: site } = useSite();
  const { data: kit } = useMediaKit();
  const topics = useTopics();
  const metrics = kit?.metrics ?? [];
  return (
    <>
      <Seo
        title="About Think Positive Always"
        description="Think Positive Always offers practical inspiration for a stronger mindset, more confidence, and intentional personal growth. Learn what we stand for and who we serve."
        path={routes.about}
        jsonLd={webPageJsonLd({ title: "About Think Positive Always", path: routes.about })}
      />
      <CompanyHero
        eyebrow="About us"
        title="Practical Inspiration for Real Life"
        intro={aboutIntro}
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "About", href: routes.about },
        ]}
        actions={
          <>
            <ActionLink href={routes.articles}>
              Read our articles
              <ArrowRight aria-hidden />
            </ActionLink>
            <ActionLink href={routes.newsletter} variant="outline">
              Join The Positive Reset
            </ActionLink>
          </>
        }
      />

      <section aria-labelledby="story-heading" className="bg-ivory py-16 sm:py-20">
        <Container
          size="wide"
          className="grid gap-10 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:items-center lg:gap-16"
        >
          <div>
            <SectionHeading
              id="story-heading"
              eyebrow="Our story"
              title="From daily encouragement to a home for growth"
            />
            <div className="mt-6 space-y-5 text-lg text-muted">
              <p>
                Think Positive Always began as a place for daily encouragement and has grown into a
                community of {site?.community?.linkedin_followers_text ?? DEFAULT_COMMUNITY}, with
                audiences on other social platforms as well. This website is our new home: a place
                to go deeper than a single post and offer thoughtful articles and practical
                resources.
              </p>
            </div>
          </div>
          <figure className="rounded-[1.75rem] border border-charcoal/10 bg-cream p-7 sm:p-9">
            <Quote aria-hidden className="size-8 text-gold-500" />
            <blockquote className="mt-4 font-serif text-2xl leading-snug text-charcoal">
              {beliefLine}
            </blockquote>
          </figure>
        </Container>
      </section>

      <section aria-labelledby="mission-heading" className="bg-cream py-16 sm:py-20">
        <Container size="narrow" className="text-center">
          <p
            id="mission-heading"
            className="text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase"
          >
            Our mission
          </p>
          <div aria-hidden className="mx-auto mt-4 h-0.5 w-14 rounded-full bg-gold-400" />
          <p className="mt-6 font-serif text-2xl leading-snug text-balance text-charcoal sm:text-[2rem]">
            {site?.mission ?? DEFAULT_MISSION}
          </p>
        </Container>
      </section>

      <section aria-labelledby="believe-heading" className="bg-ivory py-16 sm:py-20">
        <Container size="wide">
          <SectionHeading
            id="believe-heading"
            eyebrow="What we believe"
            title="For anyone ready to grow"
            description={whoWeServe}
          />
          <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {aboutValues.map((v) => (
              <IconCard key={v.title} icon={v.icon} title={v.title}>
                {v.text}
              </IconCard>
            ))}
          </ul>
        </Container>
      </section>

      <section
        aria-labelledby="editorial-heading"
        className="border-y border-charcoal/[0.08] bg-cream py-16 sm:py-20"
      >
        <Container size="wide">
          <SectionHeading
            id="editorial-heading"
            eyebrow="Our editorial approach"
            title="Content you can trust"
          />
          <ul className="mt-10 grid gap-5 md:grid-cols-3">
            {editorialApproach.map((item) => (
              <IconCard key={item.title} icon={item.icon} title={item.title} tone="light">
                {item.text}
              </IconCard>
            ))}
          </ul>
        </Container>
      </section>

      {metrics.length > 0 && (
        <section aria-labelledby="community-heading" className="bg-ivory py-16 sm:py-20">
          <Container size="wide">
            <SectionHeading
              id="community-heading"
              eyebrow="Our community"
              title="The people we write for"
              description={metricsNote}
            />
            <MetricCards metrics={metrics.slice(0, 4)} className="mt-10" />
          </Container>
        </section>
      )}

      <section aria-labelledby="about-cta-heading" className="bg-ivory py-16 sm:py-20">
        <Container size="wide">
          <CtaBand
            id="about-cta-heading"
            title="Keep growing with us"
            actions={
              <>
                <ActionLink href={routes.articles} variant="light">
                  Read our articles
                  <ArrowRight aria-hidden />
                </ActionLink>
                <ActionLink href={routes.newsletter} variant="outlineLight">
                  Join The Positive Reset
                </ActionLink>
              </>
            }
          >
            Explore our articles, or join The Positive Reset for a little encouragement every day.
          </CtaBand>
          {topics.data?.length > 0 && (
            <nav aria-label="Topics we write about" className="mt-8 text-center">
              <p className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
                The topics at the heart of our work
              </p>
              <ul className="mt-4 flex flex-wrap justify-center gap-2">
                {topics.data.map((t) => (
                  <li key={t.slug}>
                    <Link
                      to={routes.topic(t.slug)}
                      className="inline-flex rounded-full border border-charcoal/15 bg-white/60 px-3.5 py-1.5 text-sm font-medium text-ink transition-colors hover:border-sage-600 hover:text-sage-800"
                    >
                      {t.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </Container>
      </section>
    </>
  );
}

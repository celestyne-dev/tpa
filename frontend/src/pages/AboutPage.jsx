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
import { about, aboutStory } from "@/data/companyPages";
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
        title={about.seo_title}
        description={about.meta_description}
        path={routes.about}
        jsonLd={webPageJsonLd({ title: about.seo_title, path: routes.about })}
      />
      <CompanyHero
        eyebrow={about.eyebrow}
        title={about.title}
        intro={about.intro}
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "About", href: routes.about },
        ]}
        actions={
          <>
            <ActionLink href={about.primary_action.href}>
              {about.primary_action.label}
              <ArrowRight aria-hidden />
            </ActionLink>
            <ActionLink href={about.secondary_action.href} variant="outline">
              {about.secondary_action.label}
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
              eyebrow={about.story.eyebrow}
              title={about.story.heading}
            />
            <div className="mt-6 space-y-5 text-lg text-muted">
              <p>{aboutStory(site?.community?.linkedin_followers_text)}</p>
            </div>
          </div>
          <figure className="rounded-[1.75rem] border border-charcoal/10 bg-cream p-7 sm:p-9">
            <Quote aria-hidden className="size-8 text-gold-500" />
            <blockquote className="mt-4 font-serif text-2xl leading-snug text-charcoal">
              {about.story.quote}
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
            {about.mission.eyebrow}
          </p>
          <div aria-hidden className="mx-auto mt-4 h-0.5 w-14 rounded-full bg-gold-400" />
          <p className="mt-6 font-serif text-2xl leading-snug text-balance text-charcoal sm:text-[2rem]">
            {site?.mission ?? about.mission.default}
          </p>
        </Container>
      </section>

      <section aria-labelledby="believe-heading" className="bg-ivory py-16 sm:py-20">
        <Container size="wide">
          <SectionHeading
            id="believe-heading"
            eyebrow={about.values.eyebrow}
            title={about.values.heading}
            description={about.values.description}
          />
          <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {about.values.items.map((v) => (
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
            eyebrow={about.editorial.eyebrow}
            title={about.editorial.heading}
          />
          <ul className="mt-10 grid gap-5 md:grid-cols-3">
            {about.editorial.items.map((item) => (
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
              eyebrow={about.community.eyebrow}
              title={about.community.heading}
              description={about.community.note}
            />
            <MetricCards metrics={metrics.slice(0, 4)} className="mt-10" />
          </Container>
        </section>
      )}

      <section aria-labelledby="about-cta-heading" className="bg-ivory py-16 sm:py-20">
        <Container size="wide">
          <CtaBand
            id="about-cta-heading"
            title={about.closing.heading}
            actions={
              <>
                <ActionLink href={about.primary_action.href} variant="light">
                  {about.primary_action.label}
                  <ArrowRight aria-hidden />
                </ActionLink>
                <ActionLink href={about.secondary_action.href} variant="outlineLight">
                  {about.secondary_action.label}
                </ActionLink>
              </>
            }
          >
            {about.closing.body}
          </CtaBand>
          {topics.data?.length > 0 && (
            <nav aria-label="Topics we write about" className="mt-8 text-center">
              <p className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
                {about.closing.topics_heading}
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

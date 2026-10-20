import { Linkedin } from "./linkedin-mark";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { ButtonLink } from "@/components/ui/button";
import { Section } from "@/components/ui/section";

export function BrandIntro() {
  return (
    <Section tone="cream" aria-labelledby="welcome-heading">
      <div className="grid gap-12 lg:grid-cols-[1.3fr_1fr] lg:items-center lg:gap-20">
        <div>
          <p className="mb-3 text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
            Our mission
          </p>
          <h2 id="welcome-heading" className="text-3xl font-medium sm:text-4xl lg:text-[2.75rem]">
            Welcome to Think Positive Always
          </h2>
          <div className="mt-6 space-y-5 text-lg text-muted">
            <p>
              Think Positive Always exists to help people develop a healthier mindset, navigate
              life&apos;s challenges, build confidence, and move forward with intention.
            </p>
            <p>
              Here you will find honest encouragement, mindset insights, and personal growth content
              written for real life, along with practical resources designed to help you turn
              reflection into meaningful action.
            </p>
          </div>
          <ButtonLink href={routes.about} variant="outline" className="mt-8">
            More about Think Positive Always
          </ButtonLink>
        </div>

        <figure className="relative rounded-[2rem] bg-ivory p-8 shadow-soft sm:p-10">
          <span className="grid size-12 place-items-center rounded-xl bg-sage-700 text-ivory">
            <Linkedin className="size-5" />
          </span>
          <p className="mt-6 font-serif text-6xl font-medium text-charcoal sm:text-7xl">
            {siteConfig.community.linkedinFollowersLabel}
          </p>
          <figcaption className="mt-3 text-lg text-muted">
            people follow Think Positive Always on LinkedIn, part of a growing international
            community that shows up for daily encouragement and perspective.
          </figcaption>
          <div aria-hidden className="absolute top-8 right-8 h-16 w-16 rounded-full bg-gold-100" />
        </figure>
      </div>
    </Section>
  );
}

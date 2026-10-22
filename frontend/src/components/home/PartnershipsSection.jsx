import { ArrowRight, Check } from "lucide-react";
import { ButtonLink } from "@/components/ui/Button";
import { Section } from "@/components/ui/Section";
import { routes } from "@/config/navigation";
import { partnershipOpportunities } from "@/data/marketing";

export function PartnershipsSection() {
  return (
    <Section tone="charcoal" aria-labelledby="partners-heading" spacing="lg">
      <div className="grid gap-12 lg:grid-cols-2 lg:items-center lg:gap-20">
        <div>
          <p className="mb-3 text-sm font-semibold tracking-[0.14em] text-gold-300 uppercase">
            Partner with us
          </p>
          <h2
            id="partners-heading"
            className="text-3xl font-medium text-ivory sm:text-4xl lg:text-5xl"
          >
            Let's Create Something Meaningful Together
          </h2>
          <p className="mt-6 text-lg text-sand">
            We welcome conversations with brands, organisations, and publishers whose values align
            with ours. Together we can share thoughtful, useful messages with a community that cares
            about personal growth, well-being, and positive change.
          </p>
          <ButtonLink to={routes.partner} variant="light" size="lg" className="mt-9">
            Explore partnerships
            <ArrowRight aria-hidden />
          </ButtonLink>
        </div>
        <div className="rounded-[2rem] border border-ivory/10 bg-ivory/[0.04] p-8 sm:p-10">
          <h3 className="font-sans text-sm font-semibold tracking-[0.14em] text-ivory uppercase">
            Collaboration opportunities
          </h3>
          <ul className="mt-6 divide-y divide-ivory/10">
            {partnershipOpportunities.map((item) => (
              <li key={item} className="flex items-center gap-4 py-4 font-serif text-xl text-ivory">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-gold-400/20 text-gold-300">
                  <Check aria-hidden className="size-4" />
                </span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}

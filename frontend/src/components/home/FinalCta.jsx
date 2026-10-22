import { ArrowRight } from "lucide-react";
import { ButtonLink } from "@/components/ui/Button";
import { Section } from "@/components/ui/Section";
import { routes } from "@/config/navigation";

export function FinalCta() {
  return (
    <Section
      aria-labelledby="final-cta-heading"
      spacing="lg"
      size="narrow"
      containerClassName="text-center"
    >
      <div aria-hidden className="mx-auto mb-8 flex items-center justify-center gap-3">
        <span className="h-px w-12 bg-gold-400" />
        <span className="size-2 rounded-full bg-gold-400" />
        <span className="h-px w-12 bg-gold-400" />
      </div>
      <h2 id="final-cta-heading" className="text-4xl font-medium sm:text-5xl">
        Your next chapter can start today
      </h2>
      <p className="mx-auto mt-6 max-w-xl text-lg text-muted">
        Wherever you are on your journey, there is something here to encourage you. Read an article,
        explore a topic that matters to you, and take one small step forward.
      </p>
      <div className="mt-10 flex flex-col justify-center gap-3 sm:flex-row">
        <ButtonLink to={routes.articles} size="lg">
          Start reading
          <ArrowRight aria-hidden />
        </ButtonLink>
        <ButtonLink to={routes.freeResources} size="lg" variant="outline">
          Explore free resources
        </ButtonLink>
      </div>
    </Section>
  );
}

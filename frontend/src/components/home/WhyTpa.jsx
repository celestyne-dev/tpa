import { IconFeature } from "@/components/ui/IconFeature";
import { Section } from "@/components/ui/Section";
import { whyPillars } from "@/data/marketing";

export function WhyTpa() {
  return (
    <Section tone="beige" aria-labelledby="why-heading">
      <div className="grid gap-14 lg:grid-cols-[1fr_1.4fr] lg:gap-20">
        <div className="lg:sticky lg:top-32 lg:self-start">
          <p className="mb-3 text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
            Why Think Positive Always?
          </p>
          <h2 id="why-heading" className="text-3xl font-medium sm:text-4xl lg:text-[2.75rem]">
            Inspiration That Goes Beyond Words
          </h2>
          <p className="mt-5 text-lg text-muted">
            Inspiration matters most when it helps you live differently. Everything we create is
            designed to encourage you and to help you act on that encouragement.
          </p>
          <blockquote className="mt-10 border-l-4 border-gold-400 pl-6 font-serif text-2xl leading-snug text-charcoal italic">
            Positive thinking is not pretending everything is fine. It is believing you can still
            move forward.
          </blockquote>
        </div>
        <ul className="grid gap-10 sm:grid-cols-2">
          {whyPillars.map((p) => (
            <li key={p.title} className="rounded-[var(--radius-card)] bg-ivory p-7 shadow-soft">
              <IconFeature icon={p.icon} title={p.title} className="flex-col">
                {p.text}
              </IconFeature>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  );
}

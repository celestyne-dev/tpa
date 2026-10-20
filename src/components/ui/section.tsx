import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";
import { Container } from "./container";

type Tone = "ivory" | "cream" | "beige" | "sage" | "charcoal";

const tones: Record<Tone, string> = {
  ivory: "bg-ivory",
  cream: "bg-cream",
  beige: "bg-beige",
  sage: "bg-sage-50",
  charcoal: "bg-charcoal text-ivory",
};

interface SectionProps extends ComponentPropsWithoutRef<"section"> {
  tone?: Tone;
  size?: "narrow" | "default" | "wide";
  spacing?: "sm" | "md" | "lg";
  containerClassName?: string;
}

const spacings = {
  sm: "py-12 sm:py-16",
  md: "py-16 sm:py-24",
  lg: "py-20 sm:py-28",
};

/** Consistent responsive section wrapper with background tone and container. */
export function Section({
  tone = "ivory",
  size = "default",
  spacing = "md",
  className,
  containerClassName,
  children,
  ...props
}: SectionProps) {
  return (
    <section className={cn(tones[tone], spacings[spacing], className)} {...props}>
      <Container size={size} className={containerClassName}>
        {children}
      </Container>
    </section>
  );
}

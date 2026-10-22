import { cn } from "@/utils/format";
import { Container } from "./Container";

const tones = {
  ivory: "bg-ivory",
  cream: "bg-cream",
  beige: "bg-beige",
  sage: "bg-sage-50",
  charcoal: "bg-charcoal text-ivory",
};

const spacings = { sm: "py-12 sm:py-16", md: "py-16 sm:py-24", lg: "py-20 sm:py-28" };

/** Consistent responsive section wrapper with background tone and container. */
export function Section({
  tone = "ivory",
  size = "default",
  spacing = "md",
  className,
  containerClassName,
  children,
  ...props
}) {
  return (
    <section className={cn(tones[tone], spacings[spacing], className)} {...props}>
      <Container size={size} className={containerClassName}>
        {children}
      </Container>
    </section>
  );
}

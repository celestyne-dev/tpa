import { cn } from "@/utils/format";

const tones = {
  ivory: "bg-ivory shadow-soft",
  cream: "bg-cream shadow-soft",
  white: "bg-white/70 shadow-soft",
  // CMS card styles: outlined or flat surfaces without a shadow.
  outline: "bg-transparent",
  flat: "bg-cream",
};

/** Base card surface. Interactive cards lift subtly on hover/focus-within. */
export function Card({ interactive = false, tone = "white", className, ...props }) {
  return (
    <div
      className={cn(
        "relative rounded-[var(--radius-card)] border border-charcoal/[0.08]",
        tones[tone],
        interactive &&
          "transition-[box-shadow,transform] duration-300 focus-within:shadow-lift hover:-translate-y-0.5 hover:shadow-lift motion-reduce:hover:translate-y-0",
        className,
      )}
      {...props}
    />
  );
}

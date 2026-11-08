import { cn } from "@/utils/format";

// `surface-light` marks light surfaces (dark text even inside a dark CMS section);
// `card-translucent` and `card-outline` let dark sections correct their surface and
// border (see the .section-dark rules in globals.css).
const tones = {
  ivory: "surface-light bg-ivory shadow-soft",
  cream: "surface-light bg-cream shadow-soft",
  white: "surface-light card-translucent bg-white/70 shadow-soft",
  // CMS card styles: outlined or flat surfaces without a shadow.
  outline: "card-outline bg-transparent",
  flat: "surface-light bg-cream",
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

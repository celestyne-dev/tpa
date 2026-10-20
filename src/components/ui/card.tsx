import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends ComponentPropsWithoutRef<"div"> {
  interactive?: boolean;
  tone?: "ivory" | "cream" | "white";
}

const tones = {
  ivory: "bg-ivory",
  cream: "bg-cream",
  white: "bg-white/70",
};

/** Base responsive card surface. Interactive cards lift subtly on hover/focus-within. */
export function Card({ interactive = false, tone = "white", className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "relative rounded-[var(--radius-card)] border border-charcoal/[0.08] shadow-soft",
        tones[tone],
        interactive &&
          "transition-[box-shadow,transform] duration-300 focus-within:shadow-lift hover:-translate-y-0.5 hover:shadow-lift motion-reduce:hover:translate-y-0",
        className,
      )}
      {...props}
    />
  );
}

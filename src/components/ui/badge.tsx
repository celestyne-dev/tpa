import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone = "sage" | "gold" | "neutral" | "outline" | "dark";

const tones: Record<Tone, string> = {
  sage: "bg-sage-100 text-sage-800",
  gold: "bg-gold-100 text-gold-700",
  neutral: "bg-beige text-ink",
  outline: "border border-charcoal/20 text-muted",
  dark: "bg-charcoal/85 text-ivory",
};

export function Badge({
  children,
  tone = "sage",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold tracking-wide",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

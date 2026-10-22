import { cn } from "@/utils/format";

const base =
  "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-60 [&_svg]:size-[1.1em] [&_svg]:shrink-0";

const variants = {
  primary: "bg-sage-700 text-ivory hover:bg-sage-800 shadow-soft",
  secondary: "bg-charcoal text-ivory hover:bg-ink",
  outline: "border border-charcoal/25 text-charcoal hover:border-charcoal hover:bg-charcoal/5",
  ghost: "text-sage-700 hover:bg-sage-100 hover:text-sage-800",
  light: "bg-ivory text-charcoal hover:bg-cream",
};

const sizes = {
  sm: "px-4 py-2 text-sm",
  md: "px-6 py-3 text-[0.95rem]",
  lg: "px-7 py-3.5 text-base",
};

export function buttonStyles({ variant = "primary", size = "md", className } = {}) {
  return cn(base, variants[variant], sizes[size], className);
}

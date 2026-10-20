import Link from "next/link";
import { siteConfig } from "@/config/site";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" aria-hidden className={cn("size-9", className)}>
      <circle cx="20" cy="20" r="19" className="fill-sage-700" />
      <path d="M9 25.5h22" className="stroke-ivory" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M13 25.5a7 7 0 0 1 14 0" className="fill-gold-300" />
      <path
        d="M20 12.5v2.6M12.3 15.7l1.8 1.8M27.7 15.7l-1.8 1.8"
        className="stroke-gold-300"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Logo({ invert = false }: { invert?: boolean }) {
  return (
    <Link
      href="/"
      className="group inline-flex items-center gap-3 rounded-md"
      aria-label={`${siteConfig.name} — home`}
    >
      <LogoMark />
      <span className="flex flex-col leading-none">
        <span
          className={cn(
            "font-serif text-[1.2rem] font-medium tracking-tight sm:text-[1.3rem]",
            invert ? "text-ivory" : "text-charcoal",
          )}
        >
          Think Positive Always
        </span>
        <span
          className={cn(
            "mt-1 text-[0.65rem] font-semibold tracking-[0.22em] uppercase",
            invert ? "text-gold-300" : "text-sage-700",
          )}
        >
          Mindset · Growth · Confidence
        </span>
      </span>
    </Link>
  );
}

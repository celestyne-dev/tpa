import { ContentImage } from "@/components/ui/ContentImage";
import { cn } from "@/utils/format";

const themes = {
  sage: { bg: "bg-sage-700", accent: "fill-gold-300", text: "text-ivory", sub: "text-sage-100" },
  olive: { bg: "bg-olive-600", accent: "fill-sage-200", text: "text-ivory", sub: "text-gold-100" },
  gold: { bg: "bg-gold-100", accent: "fill-sage-600", text: "text-charcoal", sub: "text-gold-700" },
  charcoal: { bg: "bg-charcoal", accent: "fill-gold-400", text: "text-ivory", sub: "text-sand" },
  cream: { bg: "bg-cream", accent: "fill-gold-300", text: "text-charcoal", sub: "text-sage-700" },
  blush: { bg: "bg-beige", accent: "fill-sage-300", text: "text-charcoal", sub: "text-gold-700" },
};

/**
 * Product cover: the uploaded cover image when there is one, otherwise the
 * designed brand placeholder. Decorative (the title is always shown as text).
 */
export function ProductCover({ product, className, priority = false, sizes }) {
  if (product.cover?.src) {
    return (
      <div
        className={cn(
          "relative aspect-[3/4] w-full overflow-hidden rounded-l-sm rounded-r-xl shadow-lift",
          className,
        )}
      >
        <ContentImage
          image={{ ...product.cover, alt: "" }}
          fill
          priority={priority}
          sizes={sizes ?? "(min-width: 1024px) 280px, 60vw"}
          className="object-cover"
        />
      </div>
    );
  }
  const theme = themes[product.cover_theme] ?? themes.sage;
  return (
    <div
      aria-hidden
      className={cn(
        "@container relative flex aspect-[3/4] w-full flex-col justify-between overflow-hidden rounded-l-sm rounded-r-xl p-[9%] pl-[13%] shadow-lift",
        theme.bg,
        className,
      )}
    >
      <span className="absolute inset-y-0 left-0 w-2.5 bg-black/15" />
      <svg viewBox="0 0 200 200" className="absolute -top-[14%] -right-[26%] w-[78%] opacity-80">
        <circle cx="100" cy="100" r="60" className={theme.accent} />
        <circle
          cx="100"
          cy="100"
          r="85"
          fill="none"
          strokeWidth="1.5"
          className="stroke-current opacity-30"
        />
      </svg>
      <p
        className={cn(
          "relative max-w-[55%] text-[5cqw] leading-relaxed font-semibold tracking-[0.2em] uppercase",
          theme.sub,
        )}
      >
        Think Positive Always
      </p>
      <div className="relative">
        <p className={cn("text-[5.5cqw] font-semibold tracking-[0.2em] uppercase", theme.sub)}>
          {product.format}
        </p>
        <p
          className={cn(
            "mt-[3cqw] font-serif text-[12.5cqw] leading-[1.1] font-medium",
            theme.text,
          )}
        >
          {product.title}
        </p>
      </div>
    </div>
  );
}

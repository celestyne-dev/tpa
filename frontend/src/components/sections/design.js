import { cn } from "@/utils/format";

/**
 * Approved CMS design presets -> Tailwind classes. Sections never carry CSS:
 * the backend only accepts these token names (app/cms/design.py), so every
 * combination stays on-brand and readable. Dark backgrounds switch the
 * section to light text and light-on-dark buttons automatically.
 */
export const BACKGROUNDS = {
  ivory: "bg-ivory",
  cream: "bg-cream",
  beige: "bg-beige",
  sage: "bg-sage-50",
  sage_dark: "bg-sage-800 text-ivory",
  charcoal: "bg-charcoal text-ivory",
};

export const SPACING = { sm: "py-12 sm:py-16", md: "py-16 sm:py-24", lg: "py-20 sm:py-28" };

/**
 * The homepage's tighter rhythm, as a `--section-y` padding (mobile / tablet / desktop):
 * Small 32/40/48px, Medium 36/44/56px, Large 40/48/64px. A section that follows one with
 * the same background starts with half its padding (`.home-section` in globals.css), so
 * two light sections in a row are not separated by a double gap.
 */
export const COMPACT_SPACING = {
  sm: "[--section-y:2rem] sm:[--section-y:2.5rem] lg:[--section-y:3rem]",
  md: "[--section-y:2.25rem] sm:[--section-y:2.75rem] lg:[--section-y:3.5rem]",
  lg: "[--section-y:2.5rem] sm:[--section-y:3rem] lg:[--section-y:4rem]",
};

/** Classes and data attribute that give a homepage section its compact padding. */
export function compactSpacing(spacing, background) {
  return {
    className: cn("home-section", COMPACT_SPACING[spacing] ?? COMPACT_SPACING.md),
    "data-bg": background ?? "ivory",
  };
}

export const ASPECT = {
  landscape: "aspect-[3/2]",
  wide: "aspect-video",
  square: "aspect-square",
  portrait: "aspect-[4/5]",
};

export const HEADING_SIZE = {
  small: "text-2xl sm:text-3xl",
  default: "text-3xl sm:text-4xl lg:text-[2.75rem]",
  large: "text-4xl sm:text-5xl lg:text-6xl",
};

export const DEVICES = { all: "", desktop: "hidden md:block", mobile: "md:hidden" };

/** Space between a section's header and its cards: 48px, or 32px on the homepage. */
export const headerGap = (compact) => (compact ? "mt-8" : "mt-12");

/**
 * Homepage content width: default and wide sections share one 1200px column (the hero
 * too), so every section starts on the same left edge. Narrow stays narrow.
 */
export const compactWidth = (width) => (width === "narrow" ? "narrow" : "page");

/**
 * What the website renders when a design key is not stored on a section (older sections
 * and the built-in layouts store only some keys). The editor shows these, so the
 * Appearance controls always match the page.
 */
export const DESIGN_FALLBACKS = {
  background: "ivory",
  spacing: "md",
  width: "default",
  align: "left",
  card_style: "soft",
  aspect_ratio: "landscape",
  heading_size: "default",
};

/** The value a section actually renders with: stored, else the type default, else the fallback. */
export function effectiveDesignValue(option, design, typeDefaults) {
  const stored = design?.[option.name];
  if (stored) return stored;
  const fallback = typeDefaults?.[option.name] ?? DESIGN_FALLBACKS[option.name];
  if (fallback && option.choices.some((c) => c.value === fallback)) return fallback;
  return option.choices[0]?.value ?? "";
}

export const isDark = (background) => background === "sage_dark" || background === "charcoal";

export function cardClass(style = "soft", dark = false) {
  if (dark) {
    return style === "outline"
      ? "border border-ivory/15"
      : "border border-ivory/10 bg-ivory/[0.06]";
  }
  return {
    soft: "bg-ivory shadow-soft",
    outline: "border border-charcoal/12 bg-transparent",
    flat: "bg-cream",
  }[style];
}

/** Button style preset -> buttonStyles variant (light-on-dark when needed). */
export function buttonVariant(style, dark = false, fallback = "primary") {
  const chosen = style || fallback;
  if (!dark) return chosen;
  if (chosen === "outline") return "outlineLight";
  if (chosen === "primary" || chosen === "secondary") return "light";
  return chosen;
}

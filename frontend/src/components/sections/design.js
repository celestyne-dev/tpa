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

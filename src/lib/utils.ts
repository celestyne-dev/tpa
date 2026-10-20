type ClassValue = string | boolean | null | undefined | 0 | 0n;

/** Minimal className joiner (avoids an extra dependency). */
export function cn(...classes: ClassValue[]): string {
  return classes.filter((c): c is string => typeof c === "string" && c.length > 0).join(" ");
}

export function formatDate(iso: string, style: "long" | "short" = "long"): string {
  const date = new Date(iso);
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: style === "long" ? "long" : "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function absoluteUrl(path: string, base: string): string {
  return new URL(path, base).toString();
}

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

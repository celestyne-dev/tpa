/** Joins truthy class names (strings only). */
export function cn(...classes) {
  return classes.filter((c) => typeof c === "string" && c.length > 0).join(" ");
}

export function formatDate(iso, style = "long") {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: style === "long" ? "long" : "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(iso));
}

export function slugify(value) {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function absoluteUrl(path, base) {
  return new URL(path, base).toString();
}

/** "45 min", "2 h", "3 h 20 min" (rounded to 5 minutes above an hour). */
export function formatMinutes(minutes) {
  const total = Math.max(1, Math.round(minutes ?? 0));
  if (total < 60) return `${total} min`;
  const rounded = Math.round(total / 5) * 5;
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

export const LEVEL_LABELS = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  all_levels: "All levels",
};

/** ISO 8601 duration for structured data (PT3H20M). */
export function isoDuration(minutes) {
  const total = Math.max(1, Math.round(minutes ?? 0));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return `PT${hours ? `${hours}H` : ""}${rest ? `${rest}M` : ""}`;
}

/** A course priced through its commerce product, in the shape PriceTag/priceIn expect. */
export function priceable(course) {
  if (course.is_free) return { availability: "free", prices: [] };
  return {
    availability: course.availability === "coming_soon" ? "coming-soon" : "available",
    prices: course.prices ?? [],
  };
}

/** First server-side validation message for a field, if any. */
export function fieldError(error, name) {
  const value = error?.details?.[name];
  if (!value) return undefined;
  return Array.isArray(value)
    ? value.join(" ")
    : typeof value === "string"
      ? value
      : "Invalid value.";
}

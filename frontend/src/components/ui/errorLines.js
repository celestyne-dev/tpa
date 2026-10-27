/** Flattens an API error's `details` into readable lines (field: message). */
export function errorLines(error) {
  const details = error?.details;
  if (!details || typeof details !== "object") return [];
  const lines = [];
  const walk = (value, label) => {
    if (value == null) return;
    if (typeof value === "string") lines.push(label ? `${label}: ${value}` : value);
    else if (Array.isArray(value)) value.forEach((v) => walk(v, label));
    else if (typeof value === "object")
      Object.entries(value).forEach(([k, v]) => walk(v, label ? `${label} ${k}` : k));
  };
  Object.entries(details).forEach(([field, value]) => {
    if (field === "code" || field === "lock_version") return;
    walk(
      value,
      ["requirements", "readiness", "grade", "answers", "_unknown"].includes(field)
        ? ""
        : field.replace(/_/g, " "),
    );
  });
  return lines;
}

/** Convert between form strings and API values (money in integer minor units, UTC times). */
const ZERO_DECIMALS = new Set(["JPY", "KRW", "UGX", "RWF"]);

export function toMinor(value, currency = "USD") {
  if (value === "" || value == null) return null;
  const digits = ZERO_DECIMALS.has(currency) ? 0 : 2;
  const number = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(number) ? Math.round(number * 10 ** digits) : NaN;
}

export function fromMinor(minor, currency = "USD") {
  if (minor == null) return "";
  const digits = ZERO_DECIMALS.has(currency) ? 0 : 2;
  return (minor / 10 ** digits).toFixed(digits);
}

export function toUtc(local) {
  return local ? new Date(local).toISOString() : null;
}

export function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Initial form state from a record and field specs. */
export function initialValues(fields, record = {}) {
  const values = {};
  for (const f of fields) {
    const raw = record?.[f.name];
    if (f.type === "money") values[f.name] = fromMinor(raw, record?.currency ?? "USD");
    else if (f.type === "datetime") values[f.name] = toLocalInput(raw);
    else if (f.type === "checkbox") values[f.name] = raw ?? f.default ?? false;
    else if (f.type === "lines") values[f.name] = (raw ?? []).join("\n");
    else values[f.name] = raw ?? f.default ?? "";
  }
  return values;
}

/** API body from form values (only fields not marked readOnly). */
export function toBody(fields, values) {
  const body = {};
  for (const f of fields) {
    if (f.readOnly) continue;
    const v = values[f.name];
    if (f.type === "money") body[f.name] = toMinor(v, values.currency || "USD");
    else if (f.type === "datetime") body[f.name] = toUtc(v);
    else if (f.type === "number") body[f.name] = v === "" ? null : Number(v);
    else if (f.type === "id") body[f.name] = v === "" ? null : Number(v);
    else if (f.type === "date") body[f.name] = v || null;
    else if (f.type === "lines")
      body[f.name] = String(v ?? "")
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean);
    else body[f.name] = v;
  }
  return body;
}

export const CURRENCIES = ["USD", "KES", "EUR", "GBP"].map((c) => ({ value: c, label: c }));

export function money(minor, currency) {
  if (minor == null) return "—";
  return `${currency} ${Number(fromMinor(minor, currency)).toLocaleString("en-US", {
    minimumFractionDigits: ZERO_DECIMALS.has(currency) ? 0 : 2,
  })}`;
}

export const label = (value) => String(value ?? "").replace(/_/g, " ");

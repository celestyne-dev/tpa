/** Exact decimal <-> minor-unit conversion (no floating point). */
export function toMinor(value, exponent = 2) {
  const text = String(value ?? "")
    .trim()
    .replace(/,/g, "");
  const match = new RegExp(`^(\\d+)(?:\\.(\\d{1,${exponent}}))?$`).exec(text);
  if (!match) return null;
  const frac = (match[2] ?? "").padEnd(exponent, "0");
  return Number(match[1]) * 10 ** exponent + Number(frac || 0);
}

export function fromMinor(minor, exponent = 2) {
  if (minor == null) return "";
  const s = String(minor).padStart(exponent + 1, "0");
  return `${s.slice(0, -exponent)}.${s.slice(-exponent)}`;
}

export const toLocalInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

export const fromLocalInput = (value) => (value ? new Date(value).toISOString() : null);

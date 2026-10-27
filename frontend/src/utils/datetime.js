/** Value for an <input type="datetime-local"> in the viewer's own time zone. */
export function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** ISO 8601 with an explicit offset (the API refuses date-times without a time zone). */
export function fromLocalInput(value) {
  return value ? new Date(value).toISOString() : null;
}

/** "3:05" / "1:02:09" for a number of seconds (never negative). */
export function formatCountdown(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** Spoken form for screen readers: "4 minutes 30 seconds". */
export function spokenDuration(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const parts = [];
  if (h) parts.push(`${h} hour${h === 1 ? "" : "s"}`);
  if (m) parts.push(`${m} minute${m === 1 ? "" : "s"}`);
  if (!h && s % 60) parts.push(`${s % 60} second${s % 60 === 1 ? "" : "s"}`);
  return parts.join(" ") || "0 seconds";
}

export function formatDateTimeLocal(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

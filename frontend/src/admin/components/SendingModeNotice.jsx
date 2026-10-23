import { MODE_LABELS } from "./newsletterLabels";

export function SendingModeNotice({ mode }) {
  if (!mode) return null;
  const tone =
    mode === "live" ? "bg-sage-100 text-sage-900" : mode === "test" ? "bg-gold-100" : "bg-beige";
  return (
    <p role="status" className={`mb-4 rounded-xl px-4 py-3 text-sm ${tone}`}>
      <strong>Sending mode:</strong> {MODE_LABELS[mode]}
    </p>
  );
}

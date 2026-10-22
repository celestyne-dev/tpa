/** Simple "in" monogram for the LinkedIn community stat (decorative). */
export function LinkedinMark({ className }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <rect x="3" y="9" width="4" height="12" rx="0.5" />
      <circle cx="5" cy="4.5" r="2.2" />
      <path d="M10 9h3.8v1.7c.6-1 1.9-2 3.9-2 3.2 0 4.3 2 4.3 5.3V21h-4v-6.2c0-1.6-.3-2.8-1.9-2.8s-2.1 1.2-2.1 2.8V21h-4z" />
    </svg>
  );
}

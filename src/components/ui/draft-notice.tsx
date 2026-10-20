import { Info } from "lucide-react";
import type { ReactNode } from "react";

/** Visible notice for content that is pending review or not yet live. */
export function Notice({ title, children }: { title: string; children: ReactNode }) {
  return (
    <aside
      role="note"
      className="flex gap-4 rounded-2xl border border-gold-300 bg-gold-100/60 p-5 text-[0.95rem] text-ink"
    >
      <Info aria-hidden className="mt-0.5 size-5 shrink-0 text-gold-700" />
      <div>
        <p className="font-semibold text-charcoal">{title}</p>
        <div className="mt-1 text-muted">{children}</div>
      </div>
    </aside>
  );
}

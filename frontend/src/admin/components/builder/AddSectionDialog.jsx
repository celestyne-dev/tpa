import { Link2 } from "lucide-react";
import { useState } from "react";
import { cn } from "@/utils/format";
import { Modal } from "../Modal";
import { useBuilderLookups } from "./lookups";

/** Choose a section type (grouped by purpose) or insert a shared section. */
export function AddSectionDialog({ open, types, existing, onClose, onAddType, onAddShared }) {
  const { shared } = useBuilderLookups();
  const [tab, setTab] = useState("types");
  const usedSingles = new Set(existing.filter((s) => s.is_visible).map((s) => s.section_type));
  const categories = [...new Set(types.map((t) => t.category))].filter((c) => c !== "Shared");
  const insertable = shared.filter((s) => !["hero", "page_header"].includes(s.section_type));
  return (
    <Modal open={open} title="Add a section" onClose={onClose} size="lg">
      <div role="tablist" aria-label="Section source" className="mb-4 flex gap-2">
        {[
          ["types", "New section"],
          ["shared", `Shared sections (${insertable.length})`],
        ].map(([key, text]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "rounded-full px-4 py-1.5 text-sm font-medium",
              tab === key ? "bg-sage-700 text-ivory" : "bg-beige text-charcoal hover:bg-sand",
            )}
          >
            {text}
          </button>
        ))}
      </div>
      {tab === "types" ? (
        <div className="space-y-5">
          {categories.map((category) => (
            <section key={category} aria-label={category}>
              <h3 className="mb-2 font-sans text-xs font-semibold tracking-[0.14em] text-muted uppercase">
                {category}
              </h3>
              <ul className="grid gap-2 sm:grid-cols-2">
                {types
                  .filter((t) => t.category === category && !t.reusable_only)
                  .map((t) => {
                    const blocked = t.single_use && usedSingles.has(t.type);
                    return (
                      <li key={t.type}>
                        <button
                          type="button"
                          disabled={blocked}
                          onClick={() => onAddType(t)}
                          className="h-full w-full rounded-xl border border-charcoal/10 bg-white p-3 text-left hover:border-sage-600 hover:bg-sage-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <span className="block font-medium text-charcoal">{t.label}</span>
                          <span className="mt-1 block text-sm text-muted">
                            {blocked ? "Already on this page (one per page)." : t.description}
                          </span>
                        </button>
                      </li>
                    );
                  })}
              </ul>
            </section>
          ))}
        </div>
      ) : insertable.length === 0 ? (
        <p className="rounded-xl bg-cream p-6 text-center text-muted">
          No shared sections yet. Create them in Website › Shared sections, or save an existing
          section as shared from the section toolbar.
        </p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {insertable.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onAddShared(s)}
                className="h-full w-full rounded-xl border border-charcoal/10 bg-white p-3 text-left hover:border-sage-600 hover:bg-sage-50"
              >
                <span className="flex items-center gap-2 font-medium text-charcoal">
                  <Link2 aria-hidden className="size-4 text-sage-700" />
                  {s.name}
                </span>
                <span className="mt-1 block text-sm text-muted">
                  {s.type_label} · used on {s.usage?.length ?? 0} page(s)
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

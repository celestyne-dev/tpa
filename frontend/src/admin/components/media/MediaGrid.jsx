import { Check, ImageOff, TriangleAlert } from "lucide-react";
import { cn, formatBytes } from "@/utils/format";

/** Thumbnail grid. With `selectedIds` it behaves as an accessible multi/single picker. */
export function MediaGrid({ items, onOpen, selectedIds, label = "Media" }) {
  return (
    <ul
      aria-label={label}
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
    >
      {items.map((item) => {
        const selected = selectedIds?.includes(item.id);
        return (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onOpen(item)}
              aria-pressed={selectedIds ? Boolean(selected) : undefined}
              aria-label={`${selectedIds ? "Select" : "Open"} ${item.title || item.filename}`}
              className={cn(
                "group block w-full overflow-hidden rounded-xl border bg-white text-left transition-shadow hover:shadow-soft focus-visible:outline-3 focus-visible:outline-sage-600",
                selected ? "border-sage-600 ring-2 ring-sage-600" : "border-charcoal/10",
              )}
            >
              <span className="relative block aspect-[4/3] bg-beige">
                {item.thumbnail_url ? (
                  <img
                    src={item.thumbnail_url}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    width={item.width ?? undefined}
                    height={item.height ?? undefined}
                    className="absolute inset-0 h-full w-full object-cover"
                  />
                ) : (
                  <ImageOff aria-hidden className="absolute inset-0 m-auto size-6 text-muted" />
                )}
                {selected && (
                  <span className="absolute top-2 right-2 grid size-6 place-items-center rounded-full bg-sage-700 text-ivory">
                    <Check aria-hidden className="size-4" />
                  </span>
                )}
                {item.status === "archived" && (
                  <span className="absolute top-2 left-2 rounded-full bg-charcoal/80 px-2 py-0.5 text-xs text-ivory">
                    Archived
                  </span>
                )}
              </span>
              <span className="block p-2">
                <span className="block truncate text-sm font-medium">
                  {item.title || item.filename}
                </span>
                <span className="flex items-center justify-between gap-2 text-xs text-muted">
                  <span>
                    {item.width && item.height ? `${item.width}×${item.height}` : "—"} ·{" "}
                    {formatBytes(item.size_bytes)}
                  </span>
                  {item.missing_alt && (
                    <span
                      title="Missing alt text"
                      className="flex items-center gap-0.5 text-gold-700"
                    >
                      <TriangleAlert aria-hidden className="size-3.5" />
                      <span className="sr-only">Missing alt text</span>
                    </span>
                  )}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

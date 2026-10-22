import {
  ArrowDown,
  ArrowUp,
  Copy,
  Eye,
  EyeOff,
  GripVertical,
  Link2,
  Link2Off,
  Plus,
  Share2,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/utils/format";
import { duplicateSection, move } from "./draft";

function IconButton({ label, onClick, disabled, children, danger = false }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "rounded p-1.5 text-muted disabled:opacity-40",
        danger ? "hover:bg-red-50 hover:text-red-800" : "hover:bg-beige hover:text-charcoal",
      )}
    >
      {children}
    </button>
  );
}

/**
 * Ordered section list. Reorder by dragging the handle, with the arrow buttons, or
 * with Alt+Arrow keys on a focused section; moves are announced to screen readers.
 */
export function SectionOutline({
  sections,
  selected,
  onSelect,
  onChange,
  onAdd,
  onShare,
  onDetach,
  errorCounts = {},
  disabled = false,
  canShare = false,
}) {
  const [dragIndex, setDragIndex] = useState(null);
  const [overIndex, setOverIndex] = useState(null);
  const [announcement, setAnnouncement] = useState("");

  const label = (s) => s.name || s.type_label || s.section_type;
  const moveTo = (from, to) => {
    if (to < 0 || to >= sections.length) return;
    onChange(move(sections, from, to));
    setAnnouncement(`${label(sections[from])} moved to position ${to + 1} of ${sections.length}.`);
  };

  return (
    <div>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
      <ol aria-label="Page sections" className="space-y-2">
        {sections.map((section, index) => {
          const active = section.cid === selected;
          const errors = errorCounts[index] ?? 0;
          return (
            <li
              key={section.cid}
              draggable={!disabled}
              onDragStart={(e) => {
                setDragIndex(index);
                e.dataTransfer.effectAllowed = "move";
              }}
              onDragOver={(e) => {
                if (dragIndex === null) return;
                e.preventDefault();
                setOverIndex(index);
              }}
              onDragLeave={() => setOverIndex(null)}
              onDrop={(e) => {
                e.preventDefault();
                if (dragIndex !== null) moveTo(dragIndex, index);
                setDragIndex(null);
                setOverIndex(null);
              }}
              onDragEnd={() => {
                setDragIndex(null);
                setOverIndex(null);
              }}
              className={cn(
                "group rounded-xl border bg-white transition-colors",
                active ? "border-sage-600 ring-2 ring-sage-600/20" : "border-charcoal/10",
                overIndex === index && dragIndex !== index && "border-dashed border-gold-500",
                !section.is_visible && "opacity-70",
              )}
            >
              <div className="flex items-center gap-1 p-2">
                <span
                  aria-hidden
                  className="cursor-grab p-1 text-muted active:cursor-grabbing"
                  title="Drag to reorder"
                >
                  <GripVertical className="size-4" />
                </span>
                <button
                  type="button"
                  aria-current={active ? "true" : undefined}
                  aria-label={`Edit section ${index + 1}: ${label(section)}`}
                  onClick={() => onSelect(section.cid)}
                  onKeyDown={(e) => {
                    if (!e.altKey || disabled) return;
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      moveTo(index, index - 1);
                    } else if (e.key === "ArrowDown") {
                      e.preventDefault();
                      moveTo(index, index + 1);
                    }
                  }}
                  className="min-w-0 flex-1 rounded-md px-1 py-1 text-left"
                >
                  <span className="block truncate text-sm font-medium text-charcoal">
                    {label(section)}
                  </span>
                  <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                    {section.type_label ?? section.section_type}
                    {section.reusable_section_id && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-sage-100 px-2 text-sage-800">
                        <Link2 aria-hidden className="size-3" /> Shared
                      </span>
                    )}
                    {!section.is_visible && (
                      <span className="rounded-full bg-beige px-2 text-charcoal">Hidden</span>
                    )}
                    {errors > 0 && (
                      <span className="rounded-full bg-red-50 px-2 text-red-800">
                        {errors} {errors === 1 ? "issue" : "issues"}
                      </span>
                    )}
                  </span>
                </button>
                <div className="flex shrink-0 items-center">
                  <IconButton
                    label={`Move ${label(section)} up`}
                    disabled={disabled || index === 0}
                    onClick={() => moveTo(index, index - 1)}
                  >
                    <ArrowUp aria-hidden className="size-4" />
                  </IconButton>
                  <IconButton
                    label={`Move ${label(section)} down`}
                    disabled={disabled || index === sections.length - 1}
                    onClick={() => moveTo(index, index + 1)}
                  >
                    <ArrowDown aria-hidden className="size-4" />
                  </IconButton>
                </div>
              </div>
              {active && (
                <div className="flex flex-wrap gap-1 border-t border-charcoal/10 px-2 py-1.5">
                  <IconButton
                    label={section.is_visible ? `Hide ${label(section)}` : `Show ${label(section)}`}
                    disabled={disabled}
                    onClick={() =>
                      onChange(
                        sections.map((s, i) =>
                          i === index ? { ...s, is_visible: !s.is_visible } : s,
                        ),
                      )
                    }
                  >
                    {section.is_visible ? (
                      <EyeOff aria-hidden className="size-4" />
                    ) : (
                      <Eye aria-hidden className="size-4" />
                    )}
                  </IconButton>
                  <IconButton
                    label={`Duplicate ${label(section)}`}
                    disabled={disabled}
                    onClick={() => {
                      const next = [...sections];
                      const copy = duplicateSection(section);
                      next.splice(index + 1, 0, copy);
                      onChange(next);
                      onSelect(copy.cid);
                    }}
                  >
                    <Copy aria-hidden className="size-4" />
                  </IconButton>
                  {section.reusable_section_id ? (
                    <IconButton
                      label={`Detach ${label(section)} from the shared section`}
                      disabled={disabled}
                      onClick={() => onDetach(index)}
                    >
                      <Link2Off aria-hidden className="size-4" />
                    </IconButton>
                  ) : (
                    canShare &&
                    section.id && (
                      <IconButton
                        label={`Save ${label(section)} as a shared section`}
                        disabled={disabled}
                        onClick={() => onShare(section)}
                      >
                        <Share2 aria-hidden className="size-4" />
                      </IconButton>
                    )
                  )}
                  <IconButton
                    label={`Delete ${label(section)}`}
                    danger
                    disabled={disabled}
                    onClick={() => {
                      onChange(sections.filter((_, i) => i !== index));
                      setAnnouncement(`${label(section)} removed.`);
                    }}
                  >
                    <Trash2 aria-hidden className="size-4" />
                  </IconButton>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-3 w-full"
        disabled={disabled}
        onClick={onAdd}
      >
        <Plus aria-hidden />
        Add section
      </Button>
      <p className="mt-2 text-xs text-muted">
        Tip: drag the handle, use the arrows, or press Alt+↑/↓ on a section to reorder.
      </p>
    </div>
  );
}

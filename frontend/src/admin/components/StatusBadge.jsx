import { cn } from "@/utils/format";

const tones = {
  published: "bg-sage-100 text-sage-800",
  active: "bg-sage-100 text-sage-800",
  scheduled: "bg-gold-100 text-gold-700",
  draft: "bg-beige text-ink",
  hidden: "bg-beige text-ink",
  archived: "bg-charcoal/10 text-muted",
  disabled: "bg-red-50 text-red-800",
  inactive: "bg-charcoal/10 text-muted",
};

export function StatusBadge({ status, className }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize",
        tones[status] ?? "bg-beige text-ink",
        className,
      )}
    >
      {status}
    </span>
  );
}

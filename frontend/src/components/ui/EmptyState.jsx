import { cn } from "@/utils/format";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  headingLevel: Heading = "h3",
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-[var(--radius-card)] border border-dashed border-charcoal/20 bg-cream/60 px-6 py-14 text-center",
        className,
      )}
    >
      <span className="mb-5 grid size-14 place-items-center rounded-full bg-sage-100 text-sage-700">
        <Icon aria-hidden className="size-6" />
      </span>
      <Heading className="text-2xl font-medium">{title}</Heading>
      <div className="mt-3 max-w-md text-muted">{description}</div>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

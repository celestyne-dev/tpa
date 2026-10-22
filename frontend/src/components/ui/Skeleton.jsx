import { cn } from "@/utils/format";

export function Skeleton({ className }) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-lg bg-beige/80 motion-reduce:animate-none", className)}
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="overflow-hidden rounded-[var(--radius-card)] border border-charcoal/[0.08] bg-white/60">
      <Skeleton className="aspect-[16/10] rounded-none" />
      <div className="space-y-3 p-6">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-6 w-4/5" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  );
}

export function CardGridSkeleton({ count = 3, className }) {
  return (
    <div
      role="status"
      aria-label="Loading content"
      className={cn("grid gap-8 sm:grid-cols-2 lg:grid-cols-3", className)}
    >
      {Array.from({ length: count }, (_, i) => (
        <CardSkeleton key={i} />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function ArticleSkeleton() {
  return (
    <div role="status" aria-label="Loading article">
      <div className="bg-cream">
        <div className="mx-auto max-w-3xl space-y-5 px-5 py-14 sm:px-8">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-3/4" />
          <Skeleton className="h-5 w-2/3" />
        </div>
      </div>
      <div className="mx-auto max-w-3xl space-y-4 px-5 py-12 sm:px-8">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-4 w-full" />
        ))}
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

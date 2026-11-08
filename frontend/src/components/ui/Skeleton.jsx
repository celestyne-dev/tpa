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

/** Same frame as the article page (two columns on wide screens), so nothing jumps. */
export function ArticleSkeleton() {
  return (
    <div role="status" aria-label="Loading article">
      <div className="mx-auto w-full max-w-7xl px-5 pt-8 pb-16 sm:px-8 sm:pt-10">
        <Skeleton className="h-4 w-56" />
        <div className="mt-8 lg:grid lg:grid-cols-[minmax(0,1fr)_19rem] lg:gap-12 xl:grid-cols-[minmax(0,1fr)_21rem] xl:gap-16">
          <div className="space-y-5">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-3/4" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="aspect-[16/10] w-full" />
            <div className="max-w-[46rem] space-y-4 pt-6">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-4 w-full" />
              ))}
            </div>
          </div>
          <div className="mt-16 hidden space-y-4 lg:mt-0 lg:block">
            <Skeleton className="h-6 w-40" />
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </div>
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

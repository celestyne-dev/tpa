import { Container } from "@/components/ui/container";
import { CardGridSkeleton, Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading page">
      <div className="bg-cream">
        <Container className="space-y-5 py-16 sm:py-20">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-12 w-3/4 max-w-xl" />
          <Skeleton className="h-5 w-full max-w-2xl" />
        </Container>
      </div>
      <Container className="py-16">
        <CardGridSkeleton count={3} />
      </Container>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

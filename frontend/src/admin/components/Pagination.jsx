import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/Button";

export function Pagination({ pagination, onPage }) {
  if (!pagination || pagination.total_pages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-4 text-sm">
      <Button
        variant="outline"
        size="sm"
        disabled={!pagination.has_prev}
        onClick={() => onPage(pagination.page - 1)}
      >
        <ChevronLeft aria-hidden />
        Previous
      </Button>
      <span className="text-muted">
        Page {pagination.page} of {pagination.total_pages} · {pagination.total} total
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={!pagination.has_next}
        onClick={() => onPage(pagination.page + 1)}
      >
        Next
        <ChevronRight aria-hidden />
      </Button>
    </nav>
  );
}

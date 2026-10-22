import { Inbox } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/utils/format";

/**
 * Responsive table: scrolls horizontally on narrow screens. `columns` are
 * { key, header, render?(row), className? }.
 */
export function DataTable({ caption, columns, rows, loading, empty, rowKey = (r) => r.id }) {
  if (loading && !rows) {
    return (
      <div
        role="status"
        aria-label="Loading"
        className="space-y-2 rounded-xl border border-charcoal/10 bg-white p-4"
      >
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }
  if (!rows?.length) {
    return (
      <EmptyState
        icon={empty?.icon ?? Inbox}
        title={empty?.title ?? "Nothing here yet"}
        description={empty?.description ?? ""}
        action={empty?.action}
      />
    );
  }
  return (
    <div className="relative overflow-x-auto rounded-xl border border-charcoal/10 bg-white">
      <table className="w-full min-w-[40rem] text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-charcoal/10 bg-cream/60 text-xs tracking-wide text-muted uppercase">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={cn("px-4 py-3 font-semibold", col.className)}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-charcoal/5">
          {rows.map((row) => (
            <tr key={rowKey(row)} className="align-top hover:bg-cream/40">
              {columns.map((col) => (
                <td key={col.key} className={cn("px-4 py-3", col.className)}>
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

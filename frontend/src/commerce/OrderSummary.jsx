import { X } from "lucide-react";
import { Link } from "react-router";
import { ProductCover } from "@/components/products/ProductCover";
import { routes } from "@/config/navigation";

/** Server-quoted cart lines with explicit currency labels. */
export function OrderSummary({ quote, onRemove, compact = false }) {
  return (
    <div>
      <ul className="divide-y divide-charcoal/10">
        {quote.lines.map((line) => (
          <li key={line.product_id} className="flex gap-4 py-4">
            {!compact && (
              <div className="w-16 shrink-0">
                <ProductCover product={{ ...line, format: "" }} className="shadow-none" />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="font-medium">
                {line.slug ? (
                  <Link to={routes.product(line.slug)} className="hover:underline">
                    {line.title}
                  </Link>
                ) : (
                  line.title
                )}
              </p>
              {line.problem ? (
                <p className="mt-1 text-sm text-red-800">{line.problem}</p>
              ) : (
                <p className="mt-1 text-sm text-muted">Digital download · single licence</p>
              )}
            </div>
            <div className="text-right">
              {line.unit && <p className="font-semibold">{line.unit.formatted}</p>}
              {line.compare_at && (
                <p className="text-sm text-muted line-through">{line.compare_at.formatted}</p>
              )}
              {onRemove && (
                <button
                  type="button"
                  onClick={() => onRemove(line.product_id)}
                  className="mt-2 inline-flex items-center gap-1 text-sm text-muted hover:text-charcoal"
                  aria-label={`Remove ${line.title}`}
                >
                  <X aria-hidden className="size-4" /> Remove
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <dl className="mt-4 space-y-2 border-t border-charcoal/10 pt-4 text-sm">
        <div className="flex justify-between">
          <dt className="text-muted">Subtotal</dt>
          <dd>{quote.subtotal.formatted}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Tax</dt>
          <dd className="text-right text-muted">{quote.tax ? quote.tax.formatted : "Included"}</dd>
        </div>
        <div className="flex justify-between text-lg font-semibold">
          <dt>Total</dt>
          <dd>{quote.total.formatted}</dd>
        </div>
      </dl>
      <p className="mt-2 text-xs text-muted">{quote.tax_note}</p>
    </div>
  );
}

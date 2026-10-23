import { useState } from "react";
import { Link, useParams } from "react-router";
import { ProductDetail } from "@/components/products/ProductDetail";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

/** Private preview of the current product draft with the public page components. */
export function ProductPreviewPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const { data, error, loading, reload } = useAdminQuery(() => api.products.preview(id), [id]);
  const [currency, setCurrency] = useState(null);
  if (error) return <ErrorState title="We couldn't load the preview" onRetry={reload} />;
  if (loading || !data)
    return (
      <p role="status" className="p-10 text-muted">
        Loading preview…
      </p>
    );
  const currencies = data.prices.length ? data.prices.map((p) => p.currency) : ["USD"];
  return (
    <div className="min-h-screen bg-ivory">
      <div className="sticky top-0 z-50 flex flex-wrap items-center justify-between gap-3 bg-charcoal px-4 py-2 text-sm text-ivory">
        <span>
          Private draft preview — not public, not indexed. Prices and availability are live values.
        </span>
        <Link to={`/admin/products/${id}`} className="underline">
          Back to editor
        </Link>
      </div>
      <ProductDetail
        product={data}
        currency={currency ?? currencies[0]}
        currencies={currencies}
        onCurrency={setCurrency}
        preview
      />
    </div>
  );
}

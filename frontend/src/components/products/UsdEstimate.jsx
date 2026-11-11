import { usdEstimate } from "@/commerce/currency";
import { useUsdEstimate } from "@/hooks/useShop";
import { cn } from "@/utils/format";

/**
 * "≈ US$15.06 (approx.)" next to a KES amount, when Settings › Shop has a valid rate.
 * Display only: the customer is always charged the KES amount. Renders nothing for other
 * currencies, without a rate, or for zero amounts.
 */
export function UsdEstimate({ money, className }) {
  const estimate = useUsdEstimate();
  const text = money ? usdEstimate(money.amount_minor, money.currency, estimate) : null;
  if (!text) return null;
  return (
    <span className={cn("text-sm text-muted", className)} data-usd-estimate>
      <span aria-hidden>≈ </span>
      <span className="sr-only">approximately </span>
      {text} <span className="text-xs">(approx.)</span>
    </span>
  );
}

/** The note that explains the estimate (shown once, near prices or the total). */
export function UsdEstimateNote({ className }) {
  const estimate = useUsdEstimate();
  if (!estimate) return null;
  return (
    <p className={cn("text-xs text-muted", className)}>
      US dollar amounts are approximate, for guidance only. You pay the price in Kenyan shillings
      (KES); your bank or card provider converts it at its own rate.
    </p>
  );
}

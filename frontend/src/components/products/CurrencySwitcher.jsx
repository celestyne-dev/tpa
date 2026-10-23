import { cn } from "@/utils/format";

/** Lets shoppers choose which currency prices are shown in (no conversion happens). */
export function CurrencySwitcher({ currency, currencies, onChange, className }) {
  if (currencies.length < 2) return null;
  return (
    <div
      role="group"
      aria-label="Show prices in"
      className={cn("flex items-center gap-2", className)}
    >
      <span className="text-sm text-muted">Prices in</span>
      <div className="inline-flex rounded-full border border-charcoal/15 bg-white p-0.5">
        {currencies.map((code) => (
          <button
            key={code}
            type="button"
            aria-pressed={code === currency}
            onClick={() => onChange(code)}
            className={cn(
              "rounded-full px-3 py-1 text-sm font-semibold transition-colors",
              code === currency ? "bg-sage-700 text-ivory" : "text-charcoal hover:bg-sage-50",
            )}
          >
            {code}
          </button>
        ))}
      </div>
    </div>
  );
}

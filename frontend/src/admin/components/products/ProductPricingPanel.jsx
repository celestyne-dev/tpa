import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../../adminApiContext";
import { fieldError } from "../fieldError";
import { SelectField, TextField } from "../Fields";
import { useNotify } from "../notifyContext";
import { fromLocalInput, fromMinor, toMinor } from "./money";

/**
 * Prices in each currency as exact minor units. Nothing is converted: a product is
 * only sold in the currencies it has a price for.
 */
export function ProductPricingPanel({ product, options, canPrice, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const currencies = options.currencies ?? [];
  const exponentOf = (code) => currencies.find((c) => c.code === code)?.exponent ?? 2;
  const empty = {
    currency: options.display_currencies?.[0] ?? "USD",
    kind: "regular",
    amount: "",
    compare: "",
    starts_at: "",
    ends_at: "",
  };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState(null);

  const save = async (event) => {
    event.preventDefault();
    setError(null);
    const exp = exponentOf(form.currency);
    const amount = toMinor(form.amount, exp);
    const compare = form.compare ? toMinor(form.compare, exp) : null;
    if (amount === null || (form.compare && compare === null)) {
      setError({
        message: `Enter amounts like 12.50 (at most ${exp} decimal places).`,
        details: {},
      });
      return;
    }
    try {
      await api.products.setPrice(product.id, {
        currency: form.currency,
        kind: form.kind,
        amount_minor: amount,
        ...(form.kind === "regular" && compare !== null && { compare_at_minor: compare }),
        ...(form.kind === "promotional" && {
          starts_at: fromLocalInput(form.starts_at),
          ends_at: fromLocalInput(form.ends_at),
        }),
      });
      notify(`${form.currency} ${form.kind} price saved.`);
      setForm(empty);
      onChanged();
    } catch (err) {
      setError(err);
    }
  };
  const setModel = async (model) => {
    try {
      await api.products.update(product.id, { pricing_model: model });
      notify(model === "free" ? "This product is now free." : "This product is now paid.");
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Pricing</span>
        {["paid", "free"].map((model) => (
          <Button
            key={model}
            size="sm"
            variant={product.pricing_model === model ? "primary" : "outline"}
            disabled={!canPrice || product.pricing_model === model}
            onClick={() => setModel(model)}
          >
            {model === "paid" ? "Paid" : "Free (no checkout)"}
          </Button>
        ))}
      </div>
      <p className="text-sm text-muted">{options.tax_note}</p>
      {product.pricing_model === "paid" && (
        <>
          <table className="w-full text-sm">
            <caption className="sr-only">Prices</caption>
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-1 font-medium">Currency</th>
                <th className="font-medium">Type</th>
                <th className="font-medium">Price</th>
                <th className="font-medium">Compare-at / window</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {product.price_records.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-3 text-muted">
                    No prices yet.
                  </td>
                </tr>
              )}
              {product.price_records.map((p) => (
                <tr key={p.id} className="border-t border-charcoal/5">
                  <td className="py-2 font-medium">{p.currency}</td>
                  <td className="capitalize">{p.kind}</td>
                  <td>{p.formatted}</td>
                  <td className="text-muted">
                    {p.kind === "regular"
                      ? p.compare_at_minor
                        ? `${p.currency} ${fromMinor(p.compare_at_minor, exponentOf(p.currency))}`
                        : "—"
                      : `${p.starts_at ? new Date(p.starts_at).toLocaleString() : "now"} → ${p.ends_at ? new Date(p.ends_at).toLocaleString() : "no end"}${p.is_active ? "" : " (inactive)"}`}
                  </td>
                  <td className="text-right">
                    {canPrice && (
                      <button
                        type="button"
                        className="text-red-800 underline"
                        onClick={async () => {
                          try {
                            await api.products.removePrice(product.id, p.id);
                            notify("Price removed.");
                            onChanged();
                          } catch (err) {
                            notify(err.message, "error");
                          }
                        }}
                      >
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {canPrice ? (
            <form
              onSubmit={save}
              className="grid gap-3 rounded-xl border border-charcoal/10 p-4 sm:grid-cols-3"
            >
              <SelectField
                label="Currency"
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
                options={currencies.map((c) => ({ value: c.code, label: `${c.code} — ${c.name}` }))}
              />
              <SelectField
                label="Type"
                value={form.kind}
                onChange={(e) => setForm({ ...form, kind: e.target.value })}
                options={[
                  { value: "regular", label: "Regular price" },
                  { value: "promotional", label: "Promotional price" },
                ]}
              />
              <TextField
                label={`Price (${form.currency})`}
                inputMode="decimal"
                placeholder="12.00"
                required
                value={form.amount}
                error={fieldError(error, "amount_minor")}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
              {form.kind === "regular" ? (
                <TextField
                  label="Compare-at price (optional)"
                  inputMode="decimal"
                  hint="Shown struck through. Only use a genuine previous price."
                  value={form.compare}
                  error={fieldError(error, "compare_at_minor")}
                  onChange={(e) => setForm({ ...form, compare: e.target.value })}
                />
              ) : (
                <>
                  <TextField
                    type="datetime-local"
                    label="Starts"
                    value={form.starts_at}
                    onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
                  />
                  <TextField
                    type="datetime-local"
                    label="Ends"
                    value={form.ends_at}
                    error={fieldError(error, "ends_at")}
                    onChange={(e) => setForm({ ...form, ends_at: e.target.value })}
                  />
                </>
              )}
              {error && (
                <p role="alert" className="text-sm text-red-800 sm:col-span-3">
                  {Object.values(error.details ?? {})
                    .flat()
                    .join(" ") || error.message}
                </p>
              )}
              <div className="sm:col-span-3">
                <Button type="submit" size="sm">
                  Save price
                </Button>
              </div>
            </form>
          ) : (
            <p className="text-sm text-muted">You can view prices but not change them.</p>
          )}
        </>
      )}
    </div>
  );
}

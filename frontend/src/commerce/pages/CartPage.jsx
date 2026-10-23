import { ShoppingBag } from "lucide-react";
import { cartStore } from "@/commerce/cartStore";
import { CurrencySwitcher } from "@/components/products/CurrencySwitcher";
import { Seo } from "@/components/seo/Seo";
import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Notice } from "@/components/ui/Notice";
import { routes } from "@/config/navigation";
import { useCart, useCustomer, useDisplayCurrency } from "@/hooks/useShop";
import { OrderSummary } from "../OrderSummary";
import { useQuote } from "../useQuote";

export function CartPage() {
  const items = useCart();
  useCustomer();
  const { currency, setCurrency, currencies } = useDisplayCurrency();
  const { quote, error, loading, empty, reload } = useQuote(items, currency);

  return (
    <>
      <Seo title="Your cart" path={routes.cart} noIndex />
      <Container size="wide" className="py-12 sm:py-16">
        <h1 className="text-4xl font-medium">Your cart</h1>
        {empty ? (
          <EmptyState
            className="mt-10"
            icon={ShoppingBag}
            title="Your cart is empty"
            description="Browse the shop for eBooks, workbooks and journals."
            action={<ButtonLink to={routes.shop}>Visit the shop</ButtonLink>}
          />
        ) : error ? (
          <ErrorState className="mt-10" title="We couldn't check your cart" onRetry={reload} />
        ) : !quote ? (
          <p role="status" className="mt-10 text-muted">
            Checking prices and availability…
          </p>
        ) : (
          <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_22rem]">
            <section
              aria-label="Cart items"
              className="rounded-2xl border border-charcoal/10 bg-white p-5 sm:p-7"
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-muted">{quote.lines.length} item(s)</p>
                <CurrencySwitcher
                  currency={currency}
                  currencies={currencies}
                  onChange={setCurrency}
                />
              </div>
              <OrderSummary quote={quote} onRemove={(id) => cartStore.remove(id)} />
            </section>
            <aside className="space-y-4">
              {quote.warnings.map((w) => (
                <Notice key={w} title="Please note">
                  {w}
                </Notice>
              ))}
              {!quote.checkout.open && (
                <Notice title="Checkout isn't open">
                  {quote.checkout.message ||
                    "Payments are not being taken yet. You can keep items in your cart."}
                </Notice>
              )}
              {quote.lines.some((l) => !l.available) && (
                <p className="text-sm text-red-800">Remove the items marked above to continue.</p>
              )}
              <ButtonLink
                to={routes.checkout}
                size="lg"
                className="w-full"
                aria-disabled={!quote.can_checkout || !quote.checkout.open || loading}
                onClick={(e) => {
                  if (!quote.can_checkout || !quote.checkout.open) e.preventDefault();
                }}
              >
                Continue to checkout
              </ButtonLink>
              <p className="text-center text-xs text-muted">
                Payment is completed on Paystack's secure page. Prices are in {currency}; no
                currency conversion is applied by us.
              </p>
            </aside>
          </div>
        )}
      </Container>
    </>
  );
}

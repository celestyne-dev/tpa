import { Lock } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { InputField } from "@/components/ui/FormField";
import { Notice } from "@/components/ui/Notice";
import { routes } from "@/config/navigation";
import { useCart, useCustomer, useDisplayCurrency } from "@/hooks/useShop";
import { guestOrders } from "../guestOrders";
import { newKey, redirectTo } from "../hooks";
import { OrderSummary } from "../OrderSummary";
import { RegisterForm, SignInForm } from "./AuthPages";
import { useQuote } from "../useQuote";

const CHANNEL_LABELS = {
  card: "Card",
  mobile_money: "Mobile money (e.g. M-Pesa)",
  bank: "Bank account",
  bank_transfer: "Bank transfer",
  ussd: "USSD",
  qr: "QR code",
  apple_pay: "Apple Pay",
  eft: "EFT",
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function ChoiceCard({ id, checked, onChange, title, description }) {
  return (
    <label
      htmlFor={id}
      className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors ${checked ? "border-sage-600 bg-sage-50" : "border-charcoal/15 hover:border-charcoal/30"}`}
    >
      <input
        id={id}
        type="radio"
        name="checkout-as"
        className="mt-1 size-4 accent-sage-700"
        checked={checked}
        onChange={onChange}
      />
      <span>
        <span className="block font-medium">{title}</span>
        <span className="mt-0.5 block text-sm text-muted">{description}</span>
      </span>
    </label>
  );
}

/** Signed-out shoppers choose: buy as a guest (email only) or use an account. */
function CheckoutAsStep({ mode, setMode, guest, setGuest }) {
  return (
    <section
      aria-labelledby="account-step"
      className="rounded-2xl border border-charcoal/10 bg-white p-6 sm:p-7"
    >
      <h2 id="account-step" className="text-xl font-medium">
        1. How would you like to check out?
      </h2>
      <fieldset className="mt-5">
        <legend className="sr-only">Check out as</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <ChoiceCard
            id="checkout-as-guest"
            checked={mode === "guest"}
            onChange={() => setMode("guest")}
            title="Continue as guest"
            description="No account needed. We'll email your receipt and a private download link."
          />
          <ChoiceCard
            id="checkout-as-account"
            checked={mode !== "guest"}
            onChange={() => setMode("signin")}
            title="Log in"
            description="Purchases are saved in your library to download again any time."
          />
        </div>
      </fieldset>
      <div className="mt-6">
        {mode === "guest" ? (
          <div className="space-y-4">
            <InputField
              label="Email address"
              type="email"
              autoComplete="email"
              required
              value={guest.email}
              onChange={(e) => setGuest({ ...guest, email: e.target.value })}
              hint="Your receipt and download link go here. Please check it's correct."
            />
            <InputField
              label="Name (optional)"
              autoComplete="name"
              value={guest.name}
              onChange={(e) => setGuest({ ...guest, name: e.target.value })}
            />
            <p className="text-sm text-muted">
              You can create an account later with the same email address; once you confirm it, your
              purchases appear in your library.
            </p>
          </div>
        ) : mode === "register" ? (
          <>
            <RegisterForm />
            <p className="mt-4 text-sm">
              Already have an account?{" "}
              <button
                type="button"
                className="font-medium underline underline-offset-4"
                onClick={() => setMode("signin")}
              >
                Log in
              </button>
            </p>
          </>
        ) : (
          <>
            <SignInForm compact />
            <p className="mt-4 text-sm">
              New here?{" "}
              <button
                type="button"
                className="font-medium underline underline-offset-4"
                onClick={() => setMode("register")}
              >
                Create an account
              </button>{" "}
              or{" "}
              <Link to={routes.forgotPassword} className="underline underline-offset-4">
                reset your password
              </Link>
              .
            </p>
          </>
        )}
      </div>
    </section>
  );
}

export function CheckoutPage() {
  const shopApi = useShopApi();
  const items = useCart();
  const { customer, isLoading: customerLoading, refresh } = useCustomer();
  const { currency } = useDisplayCurrency();
  const { quote, error: quoteError, reload, empty } = useQuote(items, currency);
  const navigate = useNavigate();
  const [accepted, setAccepted] = useState(false);
  const [mode, setMode] = useState("guest");
  const [guest, setGuest] = useState({ email: "", name: "" });
  const [state, setState] = useState({ busy: false, error: null, notice: "", orderId: null });
  // One checkout key per visit: retries of the same request never create a second order.
  const key = useMemo(() => newKey(), []);

  if (empty) {
    return (
      <Container className="py-20 text-center">
        <Seo title="Checkout" path={routes.checkout} noIndex />
        <h1 className="text-3xl font-medium">Your cart is empty</h1>
        <ButtonLink to={routes.shop} className="mt-6">
          Visit the shop
        </ButtonLink>
      </Container>
    );
  }

  const asGuest = !customer;
  const pay = async () => {
    setState({ busy: true, error: null, notice: "", orderId: null });
    const body = {
      items: quote.lines.map((l) => l.product_id),
      currency: quote.currency,
      expected_total_minor: quote.total.amount_minor,
      idempotency_key: key,
      accept_terms: accepted,
    };
    try {
      const res = asGuest
        ? await shopApi.guestCheckout({ ...body, email: guest.email.trim(), name: guest.name })
        : await shopApi.checkout(body);
      const { authorization_url: url, order } = res.data;
      if (asGuest) guestOrders.save(order.id, res.data.order_token);
      if (url) redirectTo.go(url);
      else if (asGuest) navigate(`${routes.checkoutComplete}?order=${order.id}&guest=1`);
      else
        setState({
          busy: false,
          error: null,
          notice: "This order no longer needs payment.",
          orderId: res.data.order.id,
        });
    } catch (error) {
      const code = error.details?.code ?? error.code;
      if (code === "price_changed" || code === "cart_changed") {
        await reload();
        setState({ busy: false, error: null, notice: error.message, orderId: null });
      } else {
        setState({ busy: false, error, notice: "", orderId: error.details?.order ?? null });
      }
    }
  };
  const resend = async () => {
    try {
      await shopApi.resendVerification();
      setState((s) => ({ ...s, notice: "We've sent a new confirmation email.", error: null }));
    } catch (error) {
      setState((s) => ({ ...s, error }));
    }
  };
  const status = quote?.checkout;
  const unverified = customer && !customer.email_verified;
  const guestReady = !customer && mode === "guest" && EMAIL_PATTERN.test(guest.email.trim());
  const canPay =
    quote?.can_checkout &&
    status?.open &&
    (guestReady || (customer && !unverified)) &&
    accepted &&
    !state.busy;

  return (
    <>
      <Seo title="Checkout" path={routes.checkout} noIndex />
      <Container size="wide" className="py-12 sm:py-16">
        <h1 className="text-4xl font-medium">Checkout</h1>
        {status?.test_mode && (
          <p className="mt-4 inline-block rounded-full bg-gold-100 px-3 py-1 text-sm font-semibold">
            Test mode — no real money will be charged
          </p>
        )}
        <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_24rem]">
          <div className="space-y-6">
            {customerLoading ? (
              <p role="status" className="text-muted">
                Checking your account…
              </p>
            ) : !customer ? (
              <CheckoutAsStep mode={mode} setMode={setMode} guest={guest} setGuest={setGuest} />
            ) : (
              <section
                aria-labelledby="account-step"
                className="rounded-2xl border border-charcoal/10 bg-white p-6 sm:p-7"
              >
                <h2 id="account-step" className="text-xl font-medium">
                  1. Your account
                </h2>
                <p className="mt-2">
                  Receipt and download instructions go to <strong>{customer.email}</strong>.
                </p>
                {unverified && (
                  <div className="mt-4 rounded-xl bg-gold-100/60 p-4 text-sm">
                    <p>
                      Please confirm your email address before paying, so your receipt reaches you.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-3">
                      <Button size="sm" variant="outline" onClick={resend}>
                        Resend confirmation email
                      </Button>
                      <Button size="sm" variant="ghost" onClick={refresh}>
                        I've confirmed it
                      </Button>
                    </div>
                  </div>
                )}
              </section>
            )}
            <section
              aria-labelledby="payment-step"
              className="rounded-2xl border border-charcoal/10 bg-white p-6 sm:p-7"
            >
              <h2 id="payment-step" className="text-xl font-medium">
                2. Payment
              </h2>
              {!status ? null : status.open ? (
                <>
                  <p className="mt-2 text-sm text-muted">
                    You'll pay {quote.total.formatted} on Paystack's secure page. We never see or
                    store card details.{" "}
                    {customer
                      ? "Your library updates as soon as Paystack confirms the payment to us."
                      : "Your downloads are ready as soon as Paystack confirms the payment to us."}
                  </p>
                  {status.currencies?.length > 0 && (
                    <p className="mt-2 text-sm text-muted">
                      Payment currency: <strong>{quote.currency}</strong>
                    </p>
                  )}
                  {status.channels?.length > 0 && (
                    <p className="mt-2 text-sm text-muted">
                      Methods: {status.channels.map((c) => CHANNEL_LABELS[c] ?? c).join(", ")}
                    </p>
                  )}
                  <label className="mt-5 flex items-start gap-3 text-sm">
                    <input
                      type="checkbox"
                      className="mt-1 size-4 accent-sage-700"
                      checked={accepted}
                      onChange={(e) => setAccepted(e.target.checked)}
                    />
                    <span>
                      I agree to the{" "}
                      <Link to={routes.terms} className="underline underline-offset-4">
                        terms of sale
                      </Link>{" "}
                      and understand that digital downloads are available immediately after payment.
                    </span>
                  </label>
                </>
              ) : (
                <Notice title="Checkout isn't open">{status.message}</Notice>
              )}
              {state.notice && (
                <p role="status" className="mt-4 text-sm text-sage-800">
                  {state.notice}
                </p>
              )}
              {state.error && (
                <div role="alert" className="mt-4 rounded-xl bg-red-50 p-4 text-sm text-red-900">
                  <p>{state.error.message}</p>
                  {state.orderId && asGuest && (
                    <p className="mt-2">
                      Your order was saved. You can try the payment again with the button below.
                    </p>
                  )}
                  {state.orderId && !asGuest && (
                    <p className="mt-2">
                      Your order was saved.{" "}
                      <Link
                        to={`${routes.checkoutComplete}?order=${state.orderId}`}
                        className="underline underline-offset-4"
                      >
                        Try the payment again
                      </Link>
                      .
                    </p>
                  )}
                </div>
              )}
              <Button size="lg" className="mt-6 w-full" disabled={!canPay} onClick={pay}>
                <Lock aria-hidden className="size-4" />
                {state.busy
                  ? "Starting secure payment…"
                  : quote
                    ? `Pay ${quote.total.formatted}`
                    : "Pay"}
              </Button>
            </section>
          </div>
          <aside
            aria-label="Order summary"
            className="h-fit rounded-2xl border border-charcoal/10 bg-white p-6"
          >
            <h2 className="text-lg font-medium">Order summary</h2>
            {quoteError ? (
              <p role="alert" className="mt-4 text-sm text-red-800">
                {quoteError.message}
              </p>
            ) : quote ? (
              <>
                <OrderSummary quote={quote} compact />
                {!quote.can_checkout && (
                  <p className="mt-4 text-sm text-red-800">
                    Some items can't be bought.{" "}
                    <Link to={routes.cart} className="underline">
                      Review your cart
                    </Link>
                    .
                  </p>
                )}
              </>
            ) : (
              <p role="status" className="mt-4 text-sm text-muted">
                Checking prices…
              </p>
            )}
          </aside>
        </div>
      </Container>
    </>
  );
}

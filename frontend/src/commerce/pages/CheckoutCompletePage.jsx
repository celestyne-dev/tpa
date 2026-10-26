import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { cartStore } from "@/commerce/cartStore";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { guestOrders } from "../guestOrders";
import { redirectTo } from "../hooks";
import { LibraryItems } from "../LibraryItems";
import { RequireCustomer } from "../RequireCustomer";

const POLL_MS = 3000;
const MAX_POLLS = 6;

/**
 * Result page after Paystack redirects back. The redirect itself proves nothing:
 * the page asks the server to verify the payment with Paystack and only shows
 * "confirmed" when the order is paid on the server.
 */
function Result({ orderId, cancelled, verify, retryPayment, paidView, notFoundAction }) {
  const [state, setState] = useState({ order: null, error: null, checking: true });
  const polls = useRef(0);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer;
    const check = () =>
      verify().then(
        (res) => {
          if (!alive) return;
          const order = res.data.order;
          setState({ order, error: null, checking: false });
          if (order.status === "paid") {
            cartStore.removeMany(order.items.map((i) => i.product_id));
          } else if (
            order.status === "awaiting_payment" &&
            !cancelled &&
            polls.current < MAX_POLLS
          ) {
            polls.current += 1;
            timer = setTimeout(check, POLL_MS);
          }
        },
        (error) => alive && setState({ order: null, error, checking: false }),
      );
    check();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId, cancelled]);

  const retry = async () => {
    setRetrying(true);
    try {
      const res = await retryPayment();
      if (res.data.authorization_url) redirectTo.go(res.data.authorization_url);
      else setState((s) => ({ ...s, order: res.data.order }));
    } catch (error) {
      setState((s) => ({ ...s, error }));
    } finally {
      setRetrying(false);
    }
  };

  const { order, error, checking } = state;
  if (checking) {
    return (
      <p role="status" className="text-muted">
        Checking your payment with Paystack…
      </p>
    );
  }
  if (error && !order) {
    return (
      <div role="alert">
        <h1 className="text-3xl font-medium">We couldn't find this order</h1>
        <p className="mt-3 text-muted">{error.message}</p>
        {notFoundAction}
      </div>
    );
  }
  const paid = ["paid", "partially_refunded", "refunded"].includes(order.status);
  return (
    <div>
      {order.test_mode && (
        <p className="mb-6 inline-block rounded-full bg-gold-100 px-3 py-1 text-sm font-semibold">
          Test mode — no real money was charged
        </p>
      )}
      {paid ? (
        paidView(order)
      ) : order.status === "awaiting_payment" && !cancelled ? (
        <div role="status">
          <Clock aria-hidden className="size-12 text-gold-700" />
          <h1 className="mt-4 text-3xl font-medium">Waiting for payment confirmation</h1>
          <p className="mt-3 text-muted">
            Paystack hasn't confirmed this payment yet. If you completed it, this usually takes a
            few seconds;{" "}
            {order.guest
              ? `we'll also email ${order.email_hint} as soon as it's confirmed.`
              : "you'll also find the order in your account once it's confirmed."}{" "}
            You have not been charged twice by refreshing this page.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button variant="outline" onClick={() => window.location.reload()}>
              Check again
            </Button>
            {order.can_retry && (
              <Button onClick={retry} disabled={retrying}>
                Pay now
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div role="alert">
          <XCircle aria-hidden className="size-12 text-red-700" />
          <h1 className="mt-4 text-3xl font-medium">
            {cancelled || order.status === "awaiting_payment"
              ? "Payment not completed"
              : order.status === "cancelled"
                ? "This order was cancelled"
                : "The payment didn't go through"}
          </h1>
          <p className="mt-3 text-muted">
            {order.payment.failure_reason ? `Paystack said: ${order.payment.failure_reason}. ` : ""}
            No payment was confirmed for order {order.number}.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            {order.can_retry && (
              <Button onClick={retry} disabled={retrying}>
                {retrying ? "Starting payment…" : "Try again"}
              </Button>
            )}
            <ButtonLink to={routes.cart} variant="outline">
              Back to cart
            </ButtonLink>
          </div>
        </div>
      )}
      <p className="mt-10 text-sm text-muted">
        Questions?{" "}
        <Link to={routes.contact} className="underline underline-offset-4">
          Contact us
        </Link>{" "}
        with your order number.
      </p>
    </div>
  );
}

function AccountResult({ orderId, cancelled }) {
  const shopApi = useShopApi();
  return (
    <Result
      orderId={orderId}
      cancelled={cancelled}
      verify={() => shopApi.verifyOrder(orderId)}
      retryPayment={() => shopApi.retryOrder(orderId)}
      notFoundAction={
        <ButtonLink to={routes.accountOrders} className="mt-6">
          See your orders
        </ButtonLink>
      }
      paidView={(order) => (
        <div role="status">
          <CheckCircle2 aria-hidden className="size-12 text-sage-600" />
          <h1 className="mt-4 text-3xl font-medium">Payment confirmed</h1>
          <p className="mt-3 text-muted">
            Order {order.number} · {order.total.formatted}. Your downloads are in your library, and
            we've recorded your receipt.
          </p>
          <ButtonLink to={routes.accountLibrary} size="lg" className="mt-6">
            Go to your library
          </ButtonLink>
        </div>
      )}
    />
  );
}

function GuestPaid({ order, orderId, token }) {
  const shopApi = useShopApi();
  return (
    <div>
      <div role="status">
        <CheckCircle2 aria-hidden className="size-12 text-sage-600" />
        <h1 className="mt-4 text-3xl font-medium">Payment confirmed</h1>
        <p className="mt-3 text-muted">
          Order {order.number} · {order.total.formatted}. We've emailed your receipt and a private
          download link to <strong>{order.email_hint}</strong>.
        </p>
      </div>
      {order.downloads_available && order.library.length > 0 ? (
        <div className="mt-8">
          <h2 className="text-xl font-medium">Your downloads</h2>
          <p className="mt-1 mb-5 text-sm text-muted">
            Download now, or use the link in your email later. Links expire after a few minutes, so
            please don't share them.
          </p>
          <LibraryItems
            items={order.library}
            headingLevel={3}
            authorize={(item, version) =>
              shopApi.guestOrderDownload(orderId, token, item.id, version.version_id)
            }
          />
        </div>
      ) : (
        <p className="mt-6 text-sm">
          Use the link in your email to download your purchases, or{" "}
          <Link to={routes.purchases} className="underline underline-offset-4">
            request a new link
          </Link>
          .
        </p>
      )}
      <div className="mt-8 rounded-2xl bg-sage-50 p-5 text-sm">
        <p className="font-medium">Keep everything in one place</p>
        <p className="mt-1 text-muted">
          Create a free account with the same email address. Once you confirm it, this purchase
          appears in your library.
        </p>
        <ButtonLink to={routes.register} variant="outline" size="sm" className="mt-3">
          Create an account
        </ButtonLink>
      </div>
    </div>
  );
}

function GuestResult({ orderId, cancelled }) {
  const shopApi = useShopApi();
  const token = guestOrders.token(orderId);
  if (!token) {
    return (
      <div>
        <h1 className="text-3xl font-medium">Order status</h1>
        <p className="mt-3 text-muted">
          This order was started in another browser or tab. If you completed the payment, we've
          emailed your receipt and a private download link.
        </p>
        <ButtonLink to={routes.purchases} className="mt-6">
          Get a new download link
        </ButtonLink>
      </div>
    );
  }
  return (
    <Result
      orderId={orderId}
      cancelled={cancelled}
      verify={() => shopApi.verifyGuestOrder(orderId, token)}
      retryPayment={() => shopApi.retryGuestOrder(orderId, token)}
      notFoundAction={
        <ButtonLink to={routes.purchases} className="mt-6">
          Find your purchases
        </ButtonLink>
      }
      paidView={(order) => <GuestPaid order={order} orderId={orderId} token={token} />}
    />
  );
}

export function CheckoutCompletePage() {
  const [params] = useSearchParams();
  const orderId = params.get("order") ?? "";
  const cancelled = params.get("cancelled") === "1";
  const guest = params.get("guest") === "1" || Boolean(orderId && guestOrders.token(orderId));
  return (
    <>
      <Seo title="Order status" path={routes.checkoutComplete} noIndex />
      <Container size="narrow" className="py-16 sm:py-24">
        {!orderId ? (
          <p>No order was specified.</p>
        ) : guest ? (
          <GuestResult orderId={orderId} cancelled={cancelled} />
        ) : (
          <RequireCustomer>
            <AccountResult orderId={orderId} cancelled={cancelled} />
          </RequireCustomer>
        )}
      </Container>
    </>
  );
}

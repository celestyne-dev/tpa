import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { cartStore } from "@/commerce/cartStore";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { redirectTo } from "../hooks";
import { RequireCustomer } from "../RequireCustomer";

const POLL_MS = 3000;
const MAX_POLLS = 6;

/**
 * Result page after Paystack redirects back. The redirect itself proves nothing:
 * the page asks the server to verify the payment with Paystack and only shows
 * "confirmed" when the order is paid on the server.
 */
function Result({ orderId, cancelled }) {
  const shopApi = useShopApi();
  const [state, setState] = useState({ order: null, error: null, checking: true });
  const polls = useRef(0);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer;
    const check = () =>
      shopApi.verifyOrder(orderId).then(
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
  }, [orderId, cancelled, shopApi]);

  const retry = async () => {
    setRetrying(true);
    try {
      const res = await shopApi.retryOrder(orderId);
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
        <ButtonLink to={routes.accountOrders} className="mt-6">
          See your orders
        </ButtonLink>
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
      ) : order.status === "awaiting_payment" && !cancelled ? (
        <div role="status">
          <Clock aria-hidden className="size-12 text-gold-700" />
          <h1 className="mt-4 text-3xl font-medium">Waiting for payment confirmation</h1>
          <p className="mt-3 text-muted">
            Paystack hasn't confirmed this payment yet. If you completed it, this usually takes a
            few seconds; you'll also find the order in your account once it's confirmed. You have
            not been charged twice by refreshing this page.
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

export function CheckoutCompletePage() {
  const [params] = useSearchParams();
  const orderId = params.get("order") ?? "";
  return (
    <>
      <Seo title="Order status" path={routes.checkoutComplete} noIndex />
      <Container size="narrow" className="py-16 sm:py-24">
        <RequireCustomer>
          {orderId ? (
            <Result orderId={orderId} cancelled={params.get("cancelled") === "1"} />
          ) : (
            <p>No order was specified.</p>
          )}
        </RequireCustomer>
      </Container>
    </>
  );
}

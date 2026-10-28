import { Crown, FileText, GraduationCap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useShopApi } from "@/components/products/shopApiContext";
import { ButtonLink } from "@/components/ui/Button";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Notice } from "@/components/ui/Notice";
import { routes } from "@/config/navigation";
import { formatDate } from "@/utils/format";
import { AccountShell } from "../AccountShell";
import { RequireCustomer } from "../RequireCustomer";
import { useLoad } from "../hooks";

const STATUS_LABEL = {
  pending: "Waiting for payment confirmation",
  active: "Active",
  past_due: "Payment overdue",
  grace: "Payment overdue",
  incomplete: "Not completed",
  ended: "Ended",
};
const EVENT_LABEL = {
  checkout_started: "Checkout started",
  provider_subscription_linked: "Paystack subscription set up",
  activated: "Membership activated",
  checkout_abandoned: "Checkout not completed",
  superseded: "Replaced by a newer checkout",
  duplicate_payment: "Extra payment flagged for review",
};
const INTERVAL = { month: "Monthly", year: "Yearly" };
/** Paystack can confirm a payment a few seconds after the customer returns. */
const POLL_MS = 3000;
const POLL_LIMIT = 10;

/**
 * After returning from Paystack (?subscription=<id>), ask the server to verify the
 * payment with Paystack and poll briefly. The page never treats the return itself as
 * proof of payment; only the server's verified status counts.
 */
function useReturnVerification(subscriptionId, onSettled) {
  const shopApi = useShopApi();
  const [state, setState] = useState(subscriptionId ? "checking" : "idle");
  const settled = useRef(onSettled);
  useEffect(() => {
    settled.current = onSettled;
  });
  useEffect(() => {
    if (!subscriptionId) return undefined;
    let alive = true;
    let timer = null;
    let tries = 0;
    const check = async () => {
      tries += 1;
      try {
        const res = await shopApi.verifyMembership(subscriptionId);
        if (!alive) return;
        const { outcome, subscription } = res.data;
        if (subscription?.status === "active") {
          setState("active");
          settled.current();
        } else if (outcome === "mismatch" || outcome === "failed") {
          setState("problem");
          settled.current();
        } else if (subscription?.status !== "pending" || tries >= POLL_LIMIT) {
          setState("waiting");
          settled.current();
        } else {
          timer = setTimeout(check, POLL_MS);
        }
      } catch {
        if (alive) setState("error");
      }
    };
    check();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [shopApi, subscriptionId]);
  return state;
}

function ReturnNotice({ state }) {
  if (state === "checking")
    return (
      <p role="status" className="rounded-2xl bg-white p-5">
        Checking your payment with Paystack…
      </p>
    );
  if (state === "active")
    return (
      <p role="status" className="text-sage-900 rounded-2xl bg-sage-100 p-5 font-medium">
        Payment confirmed. Welcome to the membership!
      </p>
    );
  if (state === "problem")
    return (
      <Notice title="We couldn't confirm this payment">
        Your membership hasn&apos;t started. Our team has been alerted and will look into it; you
        won&apos;t be charged twice.
      </Notice>
    );
  if (state === "waiting" || state === "error")
    return (
      <Notice title="Payment not confirmed yet">
        Paystack hasn&apos;t confirmed your payment yet. This page updates once it does; if you
        completed the payment, there&apos;s nothing else to do.
      </Notice>
    );
  return null;
}

function Included({ items }) {
  if (!items.length) return null;
  return (
    <section aria-labelledby="included-heading" className="mt-8">
      <h2 id="included-heading" className="text-xl font-medium">
        Included with your membership
      </h2>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2">
        {items.map((item) => {
          const Icon = item.kind === "course" ? GraduationCap : FileText;
          const to = item.course
            ? routes.learn(item.course.slug)
            : item.slug
              ? routes.accountLibrary
              : null;
          return (
            <li key={`${item.type}-${item.title}`} className="flex items-start gap-3">
              <Icon aria-hidden className="mt-0.5 size-5 shrink-0 text-sage-700" />
              <span>
                {to ? (
                  <Link to={to} className="font-medium underline-offset-4 hover:underline">
                    {item.course?.title ?? item.title}
                  </Link>
                ) : (
                  <span className="font-medium">{item.title}</span>
                )}
                <span className="block text-sm text-muted">{item.type_label}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function CurrentMembership({ data }) {
  const sub = data.subscription;
  return (
    <section
      aria-labelledby="membership-heading"
      className="rounded-2xl border border-charcoal/10 bg-white p-6"
    >
      <p className="flex items-center gap-2 text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
        <Crown aria-hidden className="size-4" /> {STATUS_LABEL[sub.status] ?? sub.status}
      </p>
      <h2 id="membership-heading" className="mt-2 text-2xl font-medium">
        {sub.plan.name}
      </h2>
      <p className="mt-1 text-muted">
        {INTERVAL[sub.interval]} · {sub.price.formatted}
        {sub.test_mode && " · Test mode (no real money)"}
      </p>
      {sub.status === "active" && sub.current_period_end && (
        <p className="mt-3">
          Current period: {formatDate(sub.current_period_start)} to{" "}
          {formatDate(sub.current_period_end)}
        </p>
      )}
      {sub.status === "pending" && (
        <div className="mt-4 space-y-3">
          <p>
            Your membership starts as soon as Paystack confirms your first payment. You won&apos;t
            get access before then.
          </p>
          {sub.checkout_url && (
            <a href={sub.checkout_url} className={buttonStyles({ variant: "outline" })}>
              Continue to payment
            </a>
          )}
        </div>
      )}
      {sub.receipt_order && (
        <p className="mt-3 text-sm">
          <Link to={routes.accountOrders} className="underline underline-offset-4">
            View your receipt in Orders
          </Link>
        </p>
      )}
      <Included items={data.included} />
      {data.events.length > 0 && (
        <section aria-labelledby="events-heading" className="mt-8">
          <h2 id="events-heading" className="text-xl font-medium">
            History
          </h2>
          <ol className="mt-3 space-y-1 text-sm">
            {data.events.map((e, i) => (
              <li key={`${e.type}-${i}`}>
                {formatDate(e.created_at)}: {EVENT_LABEL[e.type] ?? e.type}
              </li>
            ))}
          </ol>
        </section>
      )}
    </section>
  );
}

function MembershipContent() {
  const shopApi = useShopApi();
  const [params] = useSearchParams();
  const { data, error, loading, reload } = useLoad(() => shopApi.membership(), []);
  const returnState = useReturnVerification(params.get("subscription"), reload);
  if (error) return <ErrorState title="We couldn't load your membership" onRetry={reload} />;
  if (loading && !data)
    return (
      <p role="status" className="text-muted">
        Loading your membership…
      </p>
    );
  return (
    <div className="max-w-3xl space-y-6">
      <ReturnNotice state={returnState} />
      {data.subscription ? (
        <CurrentMembership data={data} />
      ) : (
        <EmptyState
          icon={Crown}
          title="You're not a member yet"
          description={
            data.billing.available
              ? "Join to read every included course and resource."
              : data.billing.message
          }
          action={<ButtonLink to={routes.membership}>See membership plans</ButtonLink>}
        />
      )}
      <p className="text-sm text-muted">
        Courses and resources you buy separately stay yours, whatever happens to your membership.
      </p>
    </div>
  );
}

/** Signed-in customer's membership: status, current period, included items, history. */
export function AccountMembershipPage() {
  return (
    <RequireCustomer>
      <AccountShell title="Membership" path={routes.accountMembership}>
        <MembershipContent />
      </AccountShell>
    </RequireCustomer>
  );
}

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
import { redirectTo, useLoad } from "../hooks";

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
  renewed: "Membership renewed",
  payment_failed: "Renewal payment failed",
  grace_started: "Paid period ended; payment still due",
  cancellation_scheduled: "Cancelled (access continues to the period end)",
  resumed: "Cancellation undone",
  ended: "Membership ended",
  refunded: "Payment refunded",
  payment_disputed: "Payment disputed",
  payment_method_link: "Opened payment method update",
};
const PERIOD_STATUS = {
  paid: "Paid",
  pending: "Awaiting payment",
  failed: "Failed",
  refunded: "Refunded",
  void: "Void",
};
const ACTION_ERROR = {
  subscription_not_linked:
    "Your membership is still being set up with Paystack. Please try again in a few minutes.",
  resume_unavailable: "Paystack couldn't resume this membership. You can join again once it ends.",
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

function BillingNotice({ sub }) {
  if (sub.cancel_at_period_end && sub.status !== "ended")
    return (
      <Notice title="Your membership is cancelled">
        It won&apos;t renew and you won&apos;t be charged again. You keep access until{" "}
        {formatDate(sub.access_until)}.
      </Notice>
    );
  if (sub.status === "past_due" || sub.status === "grace")
    return (
      <Notice title="Your renewal payment didn't go through">
        Paystack will try again. Update your card to keep your membership; otherwise access ends on{" "}
        {formatDate(sub.access_until)}.
      </Notice>
    );
  return null;
}

/** Cancel (at period end), resume, and the Paystack-hosted card update page. */
function ManageMembership({ sub, onChanged }) {
  const shopApi = useShopApi();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const run = async (name, action) => {
    setBusy(name);
    setError("");
    try {
      await action();
      setConfirming(false);
      onChanged();
    } catch (err) {
      setError(
        ACTION_ERROR[err?.details?.code] ??
          err?.message ??
          "Something went wrong. Please try again in a moment.",
      );
    } finally {
      setBusy(null);
    }
  };
  const body = sub.id;
  const updateCard = () =>
    run("card", async () => {
      const res = await shopApi.membershipPaymentMethod(body);
      redirectTo.go(res.data.url);
    });
  if (!sub.can_cancel && !sub.can_resume && !sub.can_update_payment_method) return null;
  return (
    <section aria-labelledby="manage-heading" className="mt-8 space-y-3">
      <h2 id="manage-heading" className="text-xl font-medium">
        Manage membership
      </h2>
      <div className="flex flex-wrap gap-3">
        {sub.can_update_payment_method && (
          <button
            type="button"
            onClick={updateCard}
            disabled={busy !== null}
            className={buttonStyles({ variant: "outline" })}
          >
            {busy === "card" ? "Opening Paystack…" : "Update payment method"}
          </button>
        )}
        {sub.can_resume && (
          <button
            type="button"
            onClick={() => run("resume", () => shopApi.resumeMembership(body))}
            disabled={busy !== null}
            className={buttonStyles({})}
          >
            {busy === "resume" ? "Resuming…" : "Resume membership"}
          </button>
        )}
        {sub.can_cancel && !confirming && (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={busy !== null}
            className={buttonStyles({ variant: "outline" })}
          >
            Cancel membership
          </button>
        )}
      </div>
      {confirming && (
        <div role="group" aria-label="Confirm cancellation" className="rounded-xl bg-cream p-4">
          <p>
            Cancel your membership? You won&apos;t be charged again and you keep access until{" "}
            {formatDate(sub.current_period_end)}.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => run("cancel", () => shopApi.cancelMembership(body))}
              disabled={busy !== null}
              className={buttonStyles({})}
            >
              {busy === "cancel" ? "Cancelling…" : "Yes, cancel at period end"}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className={buttonStyles({ variant: "outline" })}
            >
              Keep my membership
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {error}
        </p>
      )}
    </section>
  );
}

function BillingHistory({ periods }) {
  if (!periods?.length) return null;
  return (
    <section aria-labelledby="billing-heading" className="mt-8">
      <h2 id="billing-heading" className="text-xl font-medium">
        Billing history
      </h2>
      <table className="mt-3 w-full text-left text-sm">
        <caption className="sr-only">Billing periods</caption>
        <thead>
          <tr className="text-muted">
            <th scope="col" className="py-1 pr-3 font-medium">
              Period
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              Amount
            </th>
            <th scope="col" className="py-1 font-medium">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {periods.map((p) => (
            <tr key={p.sequence} className="border-t border-charcoal/10">
              <td className="py-2 pr-3">
                {p.period_start
                  ? `${formatDate(p.period_start)} – ${formatDate(p.period_end)}`
                  : "—"}
              </td>
              <td className="py-2 pr-3">{p.amount.formatted}</td>
              <td className="py-2">{PERIOD_STATUS[p.status] ?? p.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function CurrentMembership({ data, onChanged }) {
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
      <div className="mt-4">
        <BillingNotice sub={sub} />
      </div>
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
      <ManageMembership sub={sub} onChanged={onChanged} />
      <Included items={data.included} />
      <BillingHistory periods={data.periods} />
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
        <CurrentMembership data={data} onChanged={reload} />
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
      {data.complimentary?.some((g) => g.status === "active") && (
        <section aria-labelledby="comp-heading" className="rounded-2xl bg-white p-5">
          <h2 id="comp-heading" className="text-lg font-medium">
            Complimentary membership
          </h2>
          <ul className="mt-2 text-sm">
            {data.complimentary
              .filter((g) => g.status === "active")
              .map((g) => (
                <li key={`${g.plan}-${g.expires_at}`}>
                  {g.plan}: included courses and resources until {formatDate(g.expires_at)}
                </li>
              ))}
          </ul>
        </section>
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

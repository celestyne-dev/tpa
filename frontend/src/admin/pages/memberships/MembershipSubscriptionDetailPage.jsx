import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { formatDate, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { CheckboxField, SelectField, TextAreaField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { SUBSCRIPTION_STATUS } from "./subscriptionLabels";

const EVENT_LABEL = {
  checkout_started: "Checkout started",
  provider_subscription_linked: "Linked to Paystack subscription",
  activated: "Activated (first payment verified)",
  renewed: "Renewed (payment verified)",
  payment_failed: "Renewal payment failed",
  grace_started: "Grace period started",
  grace_extended: "Grace extended by staff",
  cancellation_scheduled: "Cancellation scheduled",
  cancelled_by_staff: "Cancelled by staff",
  resumed: "Cancellation undone",
  ended: "Ended",
  refunded: "Payment refunded",
  payment_disputed: "Payment disputed",
  reconciled_by_staff: "Reconciled by staff",
  checkout_abandoned: "Checkout abandoned",
  checkout_superseded: "Checkout superseded",
  duplicate_payment: "Duplicate payment flagged",
  renewal_after_end: "Charged after ending (flagged)",
  provider_disable_needed: "Paystack disable needs attention",
  payment_method_link: "Member opened card update",
};

function Fact({ label, children }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-medium">{children ?? "—"}</dd>
    </div>
  );
}

function ActionModal({ action, sub, onClose, onDone }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [reason, setReason] = useState("");
  const [days, setDays] = useState("7");
  const [immediate, setImmediate] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const titles = {
    cancel: "Cancel membership",
    extend: "Extend grace period",
  };
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = { lock_version: sub.lock_version, reason };
      const res =
        action === "cancel"
          ? await api.memberships.cancelSubscription(sub.id, { ...body, immediate })
          : await api.memberships.extendGrace(sub.id, { ...body, days: Number(days) });
      notify(action === "cancel" ? "Membership cancelled." : "Grace period extended.");
      onDone(res.data.subscription);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      title={titles[action]}
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Close
          </Button>
          <Button
            type="submit"
            form="membership-action"
            disabled={busy || reason.trim().length < 3}
          >
            {action === "cancel" ? "Cancel membership" : "Extend grace"}
          </Button>
        </>
      }
    >
      <form id="membership-action" onSubmit={submit} className="space-y-3">
        <ErrorSummary error={error} />
        {action === "cancel" ? (
          <>
            <p className="text-sm">
              Paystack is told to stop charging first; if it can&apos;t confirm, nothing changes.
              The member keeps access until the end of the period they paid for. Refunds are a
              separate action on the order.
            </p>
            <CheckboxField
              label="End access now instead of at the period end"
              checked={immediate}
              onChange={(e) => setImmediate(e.target.checked)}
            />
          </>
        ) : (
          <>
            <p className="text-sm">
              Gives the member more time to pay a failed renewal. Never more than{" "}
              {sub.grace.max_extension_until
                ? `until ${formatDate(sub.grace.max_extension_until)}`
                : "30 days after the paid period"}
              . This doesn&apos;t mark anything as paid.
            </p>
            <SelectField
              label="Extra days"
              value={days}
              onChange={(e) => setDays(e.target.value)}
              options={[3, 7, 14].map((d) => ({ value: String(d), label: `${d} days` }))}
            />
          </>
        )}
        <TextAreaField
          label="Reason (kept in the audit log)"
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </form>
    </Modal>
  );
}

/** One subscription: billing, payments, orders, refunds, timeline and staff actions. */
export function MembershipSubscriptionDetailPage() {
  const { subscriptionId } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const { data, error, loading, reload, setData } = useAdminQuery(
    () => api.memberships.subscription(subscriptionId),
    [subscriptionId],
  );
  const [action, setAction] = useState(null);
  const [reconcile, setReconcile] = useState({ busy: false, result: null, error: null });
  if (error) return <ErrorState title="We couldn't load this subscription" onRetry={reload} />;
  if (loading || !data)
    return (
      <p role="status" className="text-muted">
        Loading…
      </p>
    );
  const sub = data;
  const runReconcile = async () => {
    setReconcile({ busy: true, result: null, error: null });
    try {
      const res = await api.memberships.reconcile(sub.id, { lock_version: sub.lock_version });
      setReconcile({ busy: false, result: res.data.result, error: null });
      notify("Reconciled with Paystack.");
      (setData ?? reload)(res.data.subscription);
    } catch (err) {
      setReconcile({ busy: false, result: null, error: err });
    }
  };
  const done = (updated) => {
    setAction(null);
    if (setData) setData(updated);
    else reload();
  };
  return (
    <>
      <AdminPageHeader
        title={sub.customer.email}
        description={`${sub.plan.name} · ${sub.interval === "month" ? "Monthly" : "Yearly"} · ${sub.price.formatted}${sub.test_mode ? " · Paystack test mode" : ""}`}
        breadcrumbs={[
          { label: "Subscribers", to: "/admin/membership-subscriptions" },
          { label: sub.customer.email },
        ]}
        actions={
          sub.can.manage && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={runReconcile} disabled={reconcile.busy}>
                {reconcile.busy ? "Checking Paystack…" : "Reconcile with Paystack"}
              </Button>
              {sub.can.extend_grace && (
                <Button size="sm" variant="outline" onClick={() => setAction("extend")}>
                  Extend grace
                </Button>
              )}
              {sub.can.cancel && (
                <Button size="sm" variant="outline" onClick={() => setAction("cancel")}>
                  Cancel membership
                </Button>
              )}
            </div>
          )
        }
      />
      {!sub.can.manage && (
        <p className="mb-4 text-sm text-muted">
          Your role can view this membership but not change it.
        </p>
      )}
      <ErrorSummary error={reconcile.error} title="Reconciliation didn't run" />
      {reconcile.result && (
        <div role="status" className="mb-4 rounded-xl bg-cream p-3 text-sm">
          Paystack:{" "}
          {reconcile.result.provider?.error ??
            `${reconcile.result.provider?.status ?? "not linked"}${reconcile.result.provider?.next_payment_at ? `, next payment ${formatDate(reconcile.result.provider.next_payment_at)}` : ""}`}
          {Object.keys(reconcile.result.changes ?? {}).length === 0
            ? ". No changes were needed."
            : `. Changes: ${Object.keys(reconcile.result.changes).join(", ")}.`}
        </div>
      )}
      {(sub.status === "past_due" || sub.status === "grace") && (
        <p
          role="note"
          className="mb-4 rounded-xl border border-gold-300 bg-gold-100/40 p-3 text-sm"
        >
          Renewal payment failed{sub.past_due_since ? ` on ${formatDate(sub.past_due_since)}` : ""}.
          Access ends on {formatDate(sub.access_until)} unless Paystack collects the payment.
        </p>
      )}
      <div className="max-w-5xl space-y-8">
        <section
          aria-labelledby="sub-summary"
          className="rounded-xl border border-charcoal/10 bg-white p-5"
        >
          <h2 id="sub-summary" className="text-lg font-medium">
            Summary
          </h2>
          <dl className="mt-3 grid gap-4 sm:grid-cols-3">
            <Fact label="Status">
              <StatusBadge status={sub.status} /> {SUBSCRIPTION_STATUS[sub.status]}
              {sub.cancel_at_period_end && sub.status !== "ended" && " (cancelling)"}
            </Fact>
            <Fact label="Customer">
              <Link to={`/admin/customers/${sub.customer.id}`} className="hover:underline">
                {sub.customer.name || sub.customer.email}
              </Link>
            </Fact>
            <Fact label="Current period">
              {sub.current_period_start
                ? `${formatDate(sub.current_period_start)} – ${formatDate(sub.current_period_end)}`
                : null}
            </Fact>
            <Fact label="Access until">{sub.access_until && formatDate(sub.access_until)}</Fact>
            <Fact label="Next">
              {sub.next ? `${sub.next.type} ${formatDate(sub.next.at)}` : null}
            </Fact>
            <Fact label="Paystack">
              {sub.provider.linked ? sub.provider.subscription_code : "Not linked yet"}
            </Fact>
            <Fact label="Grace period">{`${sub.grace.days} days after the paid period`}</Fact>
            <Fact label="Ended">
              {sub.ended_at ? `${formatDate(sub.ended_at)} (${sub.end_reason})` : null}
            </Fact>
            <Fact label="Last reconciled">
              {sub.last_reconciled_at && formatDateTime(sub.last_reconciled_at)}
            </Fact>
          </dl>
        </section>

        <section aria-labelledby="sub-periods">
          <h2 id="sub-periods" className="text-lg font-medium">
            Billing periods
          </h2>
          <table className="mt-2 w-full text-left text-sm">
            <caption className="sr-only">Billing periods</caption>
            <thead className="text-muted">
              <tr>
                <th scope="col">#</th>
                <th scope="col">Period</th>
                <th scope="col">Amount</th>
                <th scope="col">Status</th>
                <th scope="col">Order</th>
              </tr>
            </thead>
            <tbody>
              {sub.periods.map((p) => (
                <tr key={p.sequence} className="border-t border-charcoal/10">
                  <td className="py-1">{p.sequence}</td>
                  <td>
                    {p.period_start
                      ? `${formatDate(p.period_start)} – ${formatDate(p.period_end)}`
                      : "—"}
                  </td>
                  <td>{p.amount.formatted}</td>
                  <td>{p.status}</td>
                  <td>{p.order_number ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section aria-labelledby="sub-orders">
          <h2 id="sub-orders" className="text-lg font-medium">
            Orders, receipts and refunds
          </h2>
          <ul className="mt-2 space-y-2 text-sm">
            {sub.orders.map((o) => (
              <li key={o.id} className="rounded-lg border border-charcoal/10 bg-white p-3">
                <Link to={`/admin/orders/${o.id}`} className="font-medium hover:underline">
                  {o.number}
                </Link>{" "}
                · {o.status} · {o.total.formatted}
                {o.receipt_number && ` · receipt ${o.receipt_number}`}
                {o.refunded.amount_minor > 0 && ` · refunded ${o.refunded.formatted}`}
                {o.needs_review && (
                  <span className="text-gold-800 block">Needs review: {o.review_reason}</span>
                )}
                {o.refunds.length > 0 && (
                  <ul className="mt-1 text-muted">
                    {o.refunds.map((r) => (
                      <li key={r.id}>
                        Refund {r.amount.formatted} · {r.status}
                        {r.revoke_access ? " · access revoked" : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted">
            {sub.can.refund
              ? "Refunds are issued from the order page."
              : "Refunds need the refund permission and are issued from the order page."}
          </p>
        </section>

        <section aria-labelledby="sub-events">
          <h2 id="sub-events" className="text-lg font-medium">
            Timeline
          </h2>
          <ol className="mt-2 space-y-1 text-sm">
            {sub.events.map((e) => (
              <li key={e.id}>
                <span className="text-muted">{formatDateTime(e.created_at)}</span> ·{" "}
                {EVENT_LABEL[e.type] ?? e.type}
                {e.to_status && ` → ${e.to_status}`}{" "}
                <span className="text-xs text-muted">({e.source})</span>
                {e.details?.reason && (
                  <span className="block text-xs">Reason: {e.details.reason}</span>
                )}
              </li>
            ))}
          </ol>
        </section>

        {sub.grants.length > 0 && (
          <section aria-labelledby="sub-grants">
            <h2 id="sub-grants" className="text-lg font-medium">
              Complimentary memberships
            </h2>
            <ul className="mt-2 text-sm">
              {sub.grants.map((g) => (
                <li key={g.id}>
                  {g.plan.name} · {g.status} · until {formatDate(g.expires_at)} · {g.reason}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
      {action && (
        <ActionModal action={action} sub={sub} onClose={() => setAction(null)} onDone={done} />
      )}
    </>
  );
}

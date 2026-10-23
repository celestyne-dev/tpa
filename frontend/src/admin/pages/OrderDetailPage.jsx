import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import {
  EMAIL_STATUS,
  newRequestKey,
  ORDER_STATUS,
  REFUND_STATUS,
} from "../components/commerceLabels";
import { fieldError } from "../components/fieldError";
import { CheckboxField, TextAreaField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { toMinor } from "../components/products/money";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";

function Card({ title, children }) {
  return (
    <section className="rounded-xl border border-charcoal/10 bg-white p-5">
      <h2 className="text-lg font-medium">{title}</h2>
      <div className="mt-3 text-sm">{children}</div>
    </section>
  );
}

function RefundDialog({ order, onClose, onDone }) {
  const api = useAdminApi();
  const [form, setForm] = useState({
    amount: order.refundable.amount,
    reason: "",
    revoke_access: order.refunded.amount_minor === 0,
  });
  const [key] = useState(newRequestKey);
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    const amount = toMinor(form.amount);
    if (amount === null) {
      setError({ message: "Enter an amount like 12.50.", details: {} });
      return;
    }
    try {
      const res = await api.orders.refund(order.id, {
        amount_minor: amount,
        reason: form.reason,
        revoke_access: form.revoke_access,
        idempotency_key: key,
      });
      onDone(res.data);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open
      size="lg"
      title={`Refund order ${order.number}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="refund-form">
            Request refund
          </Button>
        </>
      }
    >
      <form id="refund-form" onSubmit={submit} className="space-y-4">
        <p className="text-sm text-muted">
          Up to {order.refundable.formatted} can be refunded. The customer has downloaded files from
          this order {order.downloads} time(s). A refund is only marked as completed after Paystack
          confirms it, or after you record the Paystack refund reference.
        </p>
        <TextField
          label={`Amount (${order.currency})`}
          inputMode="decimal"
          value={form.amount}
          error={fieldError(error, "amount_minor")}
          onChange={(e) => setForm({ ...form, amount: e.target.value })}
        />
        <TextAreaField
          label="Reason"
          required
          rows={3}
          value={form.reason}
          error={fieldError(error, "reason")}
          onChange={(e) => setForm({ ...form, reason: e.target.value })}
        />
        <CheckboxField
          label="End download access once the refund is completed"
          hint="Usually yes for full refunds."
          checked={form.revoke_access}
          onChange={(e) => setForm({ ...form, revoke_access: e.target.checked })}
        />
        {error && !Object.keys(error.details ?? {}).length && (
          <p role="alert" className="text-sm text-red-800">
            {error.message}
          </p>
        )}
      </form>
    </Modal>
  );
}

function CompleteRefundDialog({ order, refund, onClose, onDone }) {
  const api = useAdminApi();
  const [reference, setReference] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    try {
      const res = await api.orders.refundAction(order.id, refund.id, "complete", {
        provider_reference: reference,
        confirm,
      });
      onDone(res.data);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open
      title="Record a completed refund"
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="complete-refund" disabled={!confirm}>
            Record as refunded
          </Button>
        </>
      }
    >
      <form id="complete-refund" onSubmit={submit} className="space-y-4">
        <p className="text-sm text-muted">
          Only do this after the refund of {refund.amount.formatted} has actually been made in the
          Paystack dashboard.
        </p>
        <TextField
          label="Paystack refund reference"
          required
          value={reference}
          error={fieldError(error, "provider_reference")}
          onChange={(e) => setReference(e.target.value)}
        />
        <CheckboxField
          label="I confirm this refund was completed in the Paystack dashboard."
          checked={confirm}
          onChange={(e) => setConfirm(e.target.checked)}
        />
        {error && (
          <p role="alert" className="text-sm text-red-800">
            {fieldError(error, "confirm") ?? error.message}
          </p>
        )}
      </form>
    </Modal>
  );
}

export function OrderDetailPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const {
    data: order,
    error,
    loading,
    reload,
    setData,
  } = useAdminQuery(() => api.orders.get(id), [id]);
  const [dialog, setDialog] = useState(null);
  const [note, setNote] = useState("");
  if (error) return <ErrorState title="We couldn't load this order" onRetry={reload} />;
  if (loading || !order)
    return (
      <p role="status" className="text-muted">
        Loading order…
      </p>
    );
  const run = async (fn, message) => {
    try {
      const res = await fn();
      if (res?.data?.order) setData(res.data.order);
      else if (res?.data?.number) setData(res.data);
      else reload();
      notify(typeof message === "function" ? message(res) : message);
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const unpaid = ["awaiting_payment", "failed", "pending"].includes(order.status);
  return (
    <>
      <AdminPageHeader
        title={`Order ${order.number}`}
        breadcrumbs={[{ label: "Orders", to: "/admin/orders" }, { label: order.number }]}
        description={`${order.email} · ${formatDateTime(order.created_at)}${order.mode === "test" ? " · TEST MODE (no real money)" : ""}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {order.can.manage && unpaid && (
              <Button
                variant="outline"
                onClick={() =>
                  run(
                    () => api.orders.verify(order.id),
                    (res) => `Paystack check: ${res.data.outcome.replace("_", " ")}.`,
                  )
                }
              >
                Re-check payment
              </Button>
            )}
            {order.can.manage && unpaid && (
              <Button
                variant="outline"
                onClick={() => run(() => api.orders.cancel(order.id), "Order cancelled.")}
              >
                Cancel order
              </Button>
            )}
            {order.can.manage && order.receipt && (
              <Button
                variant="outline"
                onClick={() =>
                  run(
                    () => api.orders.resendReceipt(order.id),
                    (res) => `Receipt: ${EMAIL_STATUS[res.data.delivery] ?? res.data.delivery}.`,
                  )
                }
              >
                Resend receipt
              </Button>
            )}
            {order.can.refund &&
              ["paid", "partially_refunded"].includes(order.status) &&
              order.refundable.amount_minor > 0 && (
                <Button onClick={() => setDialog({ type: "refund" })}>Refund</Button>
              )}
          </div>
        }
      />
      <div className="mb-5 flex flex-wrap gap-2">
        <StatusBadge status={ORDER_STATUS[order.status] ?? order.status} />
        {order.needs_review && (
          <span className="rounded-full bg-red-50 px-3 py-0.5 text-xs font-semibold text-red-800">
            Needs review: {order.review_reason}
          </span>
        )}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Items">
          <ul className="divide-y divide-charcoal/10">
            {order.items.map((i) => (
              <li key={i.id} className="flex justify-between gap-3 py-2">
                <span>
                  {i.title}
                  {i.includes.length > 0 && (
                    <span className="block text-xs text-muted">
                      Includes {i.includes.map((c) => c.title).join(", ")}
                    </span>
                  )}
                </span>
                <span>{i.amount.formatted}</span>
              </li>
            ))}
          </ul>
          <dl className="mt-3 space-y-1 border-t border-charcoal/10 pt-3">
            <div className="flex justify-between">
              <dt>Total</dt>
              <dd className="font-semibold">{order.total.formatted}</dd>
            </div>
            <div className="flex justify-between text-muted">
              <dt>Refunded</dt>
              <dd>{order.refunded.formatted}</dd>
            </div>
            <div className="flex justify-between text-muted">
              <dt>Terms accepted</dt>
              <dd>
                {order.terms_accepted_at
                  ? `${formatDateTime(order.terms_accepted_at)}${order.terms_version ? ` (v${order.terms_version})` : ""}`
                  : "—"}
              </dd>
            </div>
          </dl>
        </Card>
        <Card title="Customer">
          <p>
            <Link to={`/admin/customers/${order.customer.id}`} className="font-medium underline">
              {order.customer.display_name || order.customer.email}
            </Link>{" "}
            · {order.customer.email}
          </p>
          <p className="mt-2 text-muted">{order.downloads} file download(s) from this order.</p>
          {order.receipt && (
            <p className="mt-2">
              Receipt {order.receipt.number} · issued {formatDateTime(order.receipt.issued_at)}
            </p>
          )}
        </Card>
        <Card title="Payment verification">
          <ul className="space-y-2">
            {order.attempts.map((a) => (
              <li key={a.id}>
                <span className="font-mono text-xs">{a.reference}</span> ·{" "}
                <StatusBadge status={a.status} /> {a.amount.formatted}
                {a.failure_reason && (
                  <span className="block text-xs text-red-800">{a.failure_reason}</span>
                )}
                <span className="block text-xs text-muted">
                  Started {formatDateTime(a.created_at)}
                  {a.verified_at ? ` · verified ${formatDateTime(a.verified_at)}` : ""}
                </span>
              </li>
            ))}
          </ul>
          {order.transactions.length > 0 && (
            <div className="mt-3 border-t border-charcoal/10 pt-3">
              <p className="font-medium">Provider-confirmed transactions</p>
              {order.transactions.map((t) => (
                <p key={`${t.kind}-${t.provider_id}`} className="text-muted">
                  {t.kind} · {t.amount.formatted} · {t.channel || "—"} · Paystack id {t.provider_id}{" "}
                  · {t.mode}
                </p>
              ))}
            </div>
          )}
        </Card>
        <Card title="Refunds">
          {order.refunds.length === 0 ? (
            <p className="text-muted">No refunds.</p>
          ) : (
            <ul className="space-y-3">
              {order.refunds.map((r) => (
                <li key={r.id}>
                  <p>
                    {r.amount.formatted} · {REFUND_STATUS[r.status] ?? r.status} ({r.method}) ·{" "}
                    {r.reason}
                  </p>
                  <p className="text-xs text-muted">
                    Requested by {r.requested_by ?? "—"} {formatDateTime(r.created_at)}
                    {r.provider_refund_id ? ` · ref ${r.provider_refund_id}` : ""}
                    {r.failure_reason ? ` · ${r.failure_reason}` : ""}
                  </p>
                  {order.can.refund && r.status === "manual_review" && (
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" onClick={() => setDialog({ type: "complete", refund: r })}>
                        Record completed refund
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          run(
                            () =>
                              api.orders.refundAction(order.id, r.id, "cancel", {
                                reason: "Cancelled by staff",
                              }),
                            "Refund request cancelled.",
                          )
                        }
                      >
                        Cancel request
                      </Button>
                    </div>
                  )}
                  {order.can.refund && r.status === "pending_provider" && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={() =>
                        run(
                          () => api.orders.refundAction(order.id, r.id, "check", {}),
                          "Refund status checked.",
                        )
                      }
                    >
                      Check status with Paystack
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
        {order.entitlements && (
          <Card title="Download access granted">
            <ul className="space-y-1">
              {order.entitlements.map((e) => (
                <li key={e.id}>
                  {e.product.title} · {e.source} · <StatusBadge status={e.status} /> ·{" "}
                  {e.download_count} download(s)
                </li>
              ))}
            </ul>
          </Card>
        )}
        <Card title="Emails">
          {order.emails.length === 0 ? (
            <p className="text-muted">No emails recorded.</p>
          ) : (
            <ul className="space-y-1">
              {order.emails.map((e, i) => (
                <li key={i}>
                  {e.template.replace(/_/g, " ")} · {EMAIL_STATUS[e.status] ?? e.status} ·{" "}
                  {formatDateTime(e.at)}
                </li>
              ))}
            </ul>
          )}
        </Card>
        {order.events && (
          <Card title="Payment provider events">
            {order.events.length === 0 ? (
              <p className="text-muted">No webhooks received for this order.</p>
            ) : (
              <ul className="space-y-1">
                {order.events.map((e) => (
                  <li key={e.id}>
                    {e.event_type} · {e.status} · received {e.received_count}× ·{" "}
                    {formatDateTime(e.received_at)}
                    {e.result && <span className="block text-xs text-muted">{e.result}</span>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
        <Card title="Notes & history">
          {order.notes && (
            <pre className="mb-3 font-sans text-sm whitespace-pre-wrap text-muted">
              {order.notes}
            </pre>
          )}
          {order.can.manage && (
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                run(() => api.orders.addNote(order.id, note), "Note added.").then(() =>
                  setNote(""),
                );
              }}
            >
              <TextField
                className="flex-1"
                label="Add a support note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <Button type="submit" size="sm" className="self-end" disabled={!note.trim()}>
                Add
              </Button>
            </form>
          )}
          {order.audit && (
            <ul className="mt-3 space-y-1 text-xs text-muted">
              {order.audit.map((a, i) => (
                <li key={i}>
                  {formatDateTime(a.at)} · {a.action} · {a.actor}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      {dialog?.type === "refund" && (
        <RefundDialog
          order={order}
          onClose={() => setDialog(null)}
          onDone={(data) => {
            setDialog(null);
            setData(data.order);
            notify(`Refund ${REFUND_STATUS[data.refund.status] ?? data.refund.status}.`);
          }}
        />
      )}
      {dialog?.type === "complete" && (
        <CompleteRefundDialog
          order={order}
          refund={dialog.refund}
          onClose={() => setDialog(null)}
          onDone={(data) => {
            setDialog(null);
            setData(data.order);
            notify("Refund recorded as completed.");
          }}
        />
      )}
    </>
  );
}

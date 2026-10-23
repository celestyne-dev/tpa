import { CheckCircle2, Circle } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { CheckboxField, SelectField, TextField } from "../components/Fields";
import { useNotify } from "../components/notifyContext";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const MODE_HELP = {
  disabled: "No one can pay. Products can still be browsed; free resources still work.",
  test: "Paystack test mode with a test secret key. Only customers marked as test accounts can check out; no real money moves.",
  live: "Real payments. Available only when every readiness check below passes.",
};

function Events() {
  const api = useAdminApi();
  const { data, error, loading, reload } = useAdminQuery(
    () => api.payments.events({ page_size: 25 }),
    [],
  );
  if (error) return <ErrorState title="We couldn't load payment events" onRetry={reload} />;
  if (loading || !data) return <p className="text-sm text-muted">Loading events…</p>;
  if (!data.length) return <p className="text-sm text-muted">No webhooks received yet.</p>;
  return (
    <ul className="divide-y divide-charcoal/10 text-sm">
      {data.map((e) => (
        <li key={e.id} className="py-2">
          <span className="font-medium">{e.event_type}</span> · {e.status} · {e.mode ?? "—"} ·
          received {e.received_count}× · {formatDateTime(e.received_at)}
          {e.reference && <span className="block font-mono text-xs text-muted">{e.reference}</span>}
          {e.result && <span className="block text-xs text-muted">{e.result}</span>}
        </li>
      ))}
    </ul>
  );
}

function Settings() {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, error, loading, reload } = useAdminQuery(() => api.payments.settings(), []);
  const [form, setForm] = useState(null);
  if (error) return <ErrorState title="We couldn't load payment settings" onRetry={reload} />;
  if (loading || !data)
    return (
      <p role="status" className="text-muted">
        Loading…
      </p>
    );
  const values = form ?? data.settings;
  const set = (patch) => setForm({ ...values, ...patch });
  const provider = data.provider;
  const save = async () => {
    const changes = Object.fromEntries(
      [
        "checkout_mode",
        "currencies",
        "channels",
        "order_expiry_minutes",
        "refunds_via_provider",
        "terms_version",
        "download_limit",
      ]
        .filter((k) => JSON.stringify(values[k]) !== JSON.stringify(data.settings[k]))
        .map((k) => [k, values[k]]),
    );
    if (!Object.keys(changes).length) return;
    try {
      await api.payments.update(changes);
      notify("Payment settings saved.");
      setForm(null);
      reload();
    } catch (err) {
      const details = err.details ? Object.values(err.details).flat().join(" ") : "";
      notify(`${err.message} ${details}`.trim(), "error");
    }
  };
  const attest = async (key, value) => {
    try {
      await api.payments.attest({ [key]: value });
      reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const toggle = (list, item) =>
    list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_24rem]">
      <div className="space-y-6">
        <section className="rounded-xl border border-charcoal/10 bg-white p-5">
          <h2 className="text-lg font-medium">Provider: {provider.label}</h2>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted">Secret key (server environment)</dt>
              <dd>
                {provider.secret_key_configured
                  ? `Configured · ${provider.key_mode} mode`
                  : "Not configured"}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Public key</dt>
              <dd>
                {provider.public_key_configured
                  ? `Configured · ${provider.public_key_mode ?? "unknown"} mode`
                  : "Not configured"}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Live payments allowed by deployment</dt>
              <dd>{provider.live_allowed_by_deployment ? "Yes" : "No (PAYMENTS_LIVE_ALLOWED)"}</dd>
            </div>
            <div>
              <dt className="text-muted">Checkout in force now</dt>
              <dd className="font-semibold">{data.effective_mode}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-muted">Webhook URL (save in the Paystack dashboard)</dt>
              <dd className="font-mono text-xs break-all">{provider.webhook_url}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-muted">Callback URL</dt>
              <dd className="font-mono text-xs break-all">{provider.callback_url}</dd>
            </div>
          </dl>
          <p className="mt-3 text-xs text-muted">
            Keys are never shown or stored here. Set them in the server's environment
            (backend/.env).
          </p>
        </section>
        <section className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5">
          <h2 className="text-lg font-medium">Checkout</h2>
          <SelectField
            label="Checkout mode"
            value={values.checkout_mode}
            hint={MODE_HELP[values.checkout_mode]}
            onChange={(e) => set({ checkout_mode: e.target.value })}
            options={[
              { value: "disabled", label: "Disabled" },
              { value: "test", label: "Test (sandbox)" },
              { value: "live", label: "Live" },
            ]}
          />
          <fieldset>
            <legend className="text-sm font-medium">Currencies customers can pay in</legend>
            <p className="text-xs text-muted">
              Enable only currencies that are activated on your Paystack account (USD requires
              Paystack approval). Nothing is converted.
            </p>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
              {provider.supported_currencies.map((code) => (
                <CheckboxField
                  key={code}
                  label={code}
                  checked={values.currencies.includes(code)}
                  onChange={() => set({ currencies: toggle(values.currencies, code) })}
                />
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="text-sm font-medium">
              Payment methods offered on Paystack's page
            </legend>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
              {provider.supported_channels.map((channel) => (
                <CheckboxField
                  key={channel}
                  label={channel.replace("_", " ")}
                  checked={values.channels.includes(channel)}
                  onChange={() => set({ channels: toggle(values.channels, channel) })}
                />
              ))}
            </div>
          </fieldset>
          <div className="grid gap-4 sm:grid-cols-3">
            <TextField
              label="Unpaid orders expire after (minutes)"
              type="number"
              min={15}
              max={1440}
              value={values.order_expiry_minutes}
              onChange={(e) => set({ order_expiry_minutes: Number(e.target.value) })}
            />
            <TextField
              label="Terms version"
              value={values.terms_version}
              hint="Recorded with each order, e.g. 2026-10."
              onChange={(e) => set({ terms_version: e.target.value })}
            />
            <TextField
              label="Downloads per purchase (optional)"
              type="number"
              min={1}
              value={values.download_limit ?? ""}
              hint="Empty = unlimited."
              onChange={(e) =>
                set({ download_limit: e.target.value ? Number(e.target.value) : null })
              }
            />
          </div>
          <CheckboxField
            label="Issue refunds through the Paystack API"
            hint="Off: staff refund in the Paystack dashboard and record the reference here."
            checked={values.refunds_via_provider}
            onChange={(e) => set({ refunds_via_provider: e.target.checked })}
          />
          <Button onClick={save} disabled={!form}>
            Save payment settings
          </Button>
        </section>
        <section className="rounded-xl border border-charcoal/10 bg-white p-5">
          <h2 className="text-lg font-medium">Recent payment events</h2>
          <div className="mt-3">
            <Events />
          </div>
        </section>
      </div>
      <aside className="space-y-6">
        <section className="rounded-xl border border-charcoal/10 bg-white p-5">
          <h2 className="text-lg font-medium">Readiness</h2>
          <p className="mt-1 text-sm text-muted">
            {data.readiness.live_ready
              ? "Ready for live checkout."
              : data.readiness.test_ready
                ? "Ready for test checkout. Live checkout stays locked."
                : "Not ready for checkout."}
          </p>
          <ul className="mt-3 space-y-2 text-sm">
            {data.readiness.checks
              .filter((c) => !c.key.startsWith("attest_"))
              .map((c) => (
                <li key={c.key} className="flex gap-2">
                  {c.ok ? (
                    <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-sage-700" />
                  ) : (
                    <Circle aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
                  )}
                  <span>
                    <span className="sr-only">{c.ok ? "Done: " : "Not done: "}</span>
                    {c.label} <span className="text-xs text-muted">({c.required_for})</span>
                    {!c.ok && c.detail && (
                      <span className="block text-xs text-muted">{c.detail}</span>
                    )}
                  </span>
                </li>
              ))}
          </ul>
        </section>
        <section className="rounded-xl border border-charcoal/10 bg-white p-5">
          <h2 className="text-lg font-medium">Live activation checklist</h2>
          <p className="mt-1 text-xs text-muted">
            Confirm each item yourself. Withdrawing a confirmation immediately closes live checkout.
          </p>
          <div className="mt-3 space-y-3">
            {Object.entries(data.attestations).map(([key, label]) => (
              <CheckboxField
                key={key}
                label={label}
                hint={
                  data.readiness.attestation[key]
                    ? `Confirmed by ${data.readiness.attestation[key].by} · ${formatDateTime(data.readiness.attestation[key].confirmed_at)}`
                    : undefined
                }
                checked={Boolean(data.readiness.attestation[key])}
                onChange={(e) => attest(key, e.target.checked)}
              />
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

export function PaymentSettingsPage() {
  const { can } = usePermissions();
  return (
    <>
      <AdminPageHeader
        title="Payment Settings"
        description="Checkout stays closed to real customers until it is explicitly configured, verified and switched on here by a Super Admin."
        breadcrumbs={[{ label: "Payment Settings" }]}
      />
      {can("payments.configure") ? (
        <Settings />
      ) : (
        <section className="rounded-xl border border-charcoal/10 bg-white p-5">
          <p className="mb-3 text-sm text-muted">
            Only a Super Admin can change payment settings. You can review payment events.
          </p>
          <Events />
        </section>
      )}
    </>
  );
}

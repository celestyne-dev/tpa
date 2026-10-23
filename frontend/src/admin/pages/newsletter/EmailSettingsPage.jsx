import { CheckCircle2, Circle } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { fieldError } from "../../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../../components/Fields";
import { MODE_LABELS } from "../../components/newsletterLabels";
import { useNotify } from "../../components/notifyContext";
import { useAdminQuery } from "../../hooks/useAdminQuery";

const EDITABLE = [
  "sending_mode",
  "from_name",
  "reply_to",
  "consent_text",
  "consent_version",
  "postal_address",
];

export function EmailSettingsPage() {
  const api = useAdminApi();
  const { data, error, reload, setData } = useAdminQuery(() => api.emailSettings.get(), []);
  if (error) return <ErrorState title="We couldn't load email settings" onRetry={reload} />;
  if (!data) return <p className="text-muted">Loading…</p>;
  return <SettingsEditor key={JSON.stringify(data)} data={data} setData={setData} />;
}

function SettingsEditor({ data, setData }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [form, setForm] = useState(() =>
    Object.fromEntries(EDITABLE.map((k) => [k, data[k] ?? ""])),
  );
  const [saveError, setSaveError] = useState(null);
  const save = async (e) => {
    e.preventDefault();
    setSaveError(null);
    const changes = Object.fromEntries(
      EDITABLE.filter((k) => form[k] !== (data[k] ?? "")).map((k) => [k, form[k]]),
    );
    try {
      setData((await api.emailSettings.update(changes)).data);
      notify("Email settings saved.");
    } catch (err) {
      setSaveError(err);
    }
  };
  const attest = async (key, value) => {
    try {
      setData((await api.emailSettings.attest({ [key]: value })).data);
    } catch (err) {
      notify(err.message, "error");
    }
  };
  return (
    <>
      <AdminPageHeader
        title="Email settings"
        description="Sending mode, sender identity, consent wording and deliverability checks. Credentials stay on the server."
        breadcrumbs={[{ label: "Email settings" }]}
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_24rem]">
        <form onSubmit={save} className="space-y-4 rounded-2xl bg-white p-5 shadow-sm">
          <SelectField
            label="Sending mode"
            value={form.sending_mode}
            error={fieldError(saveError, "sending_mode")}
            onChange={(e) => setForm({ ...form, sending_mode: e.target.value })}
            options={Object.entries(MODE_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Sender name"
              value={form.from_name}
              error={fieldError(saveError, "from_name")}
              onChange={(e) => setForm({ ...form, from_name: e.target.value })}
            />
            <TextField
              label="Sender address"
              value={data.from_email || "Not configured (NEWSLETTER_FROM_EMAIL)"}
              disabled
              hint="Set on the server, on a domain with SPF, DKIM and DMARC."
            />
            <TextField
              label="Default reply-to"
              type="email"
              value={form.reply_to}
              error={fieldError(saveError, "reply_to")}
              onChange={(e) => setForm({ ...form, reply_to: e.target.value })}
            />
            <TextField
              label="Consent version"
              value={form.consent_version}
              error={fieldError(saveError, "consent_version")}
              hint="Change it whenever the consent wording changes."
              onChange={(e) => setForm({ ...form, consent_version: e.target.value })}
            />
          </div>
          <TextAreaField
            label="Consent wording (shown next to every signup form)"
            rows={3}
            value={form.consent_text}
            error={fieldError(saveError, "consent_text")}
            onChange={(e) => setForm({ ...form, consent_text: e.target.value })}
          />
          <TextAreaField
            label="Postal address for the email footer"
            rows={2}
            value={form.postal_address}
            error={fieldError(saveError, "postal_address")}
            onChange={(e) => setForm({ ...form, postal_address: e.target.value })}
          />
          {saveError && !Object.keys(saveError.details ?? {}).length && (
            <p role="alert" className="text-sm text-red-800">
              {saveError.message}
            </p>
          )}
          <Button type="submit">Save settings</Button>
          <p className="text-xs text-muted">
            Changing the sending mode or consent wording queues a site rebuild so signup forms
            appear, update or disappear.
          </p>
        </form>
        <aside className="space-y-4">
          <section className="rounded-2xl bg-white p-5 shadow-sm" aria-labelledby="ready-h">
            <h2 id="ready-h" className="font-medium">
              Readiness
            </h2>
            <ul className="mt-3 space-y-2 text-sm">
              {data.readiness.checks.map((c) => (
                <li key={c.key} className="flex gap-2">
                  {c.ok ? (
                    <CheckCircle2 aria-hidden className="size-4 shrink-0 text-sage-700" />
                  ) : (
                    <Circle aria-hidden className="size-4 shrink-0 text-muted" />
                  )}
                  <span>
                    <span className="sr-only">{c.ok ? "Done: " : "Not done: "}</span>
                    {c.label}
                    {!c.ok && c.hint && <span className="block text-xs text-muted">{c.hint}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <section
            className="space-y-3 rounded-2xl bg-white p-5 shadow-sm"
            aria-labelledby="attest-h"
          >
            <h2 id="attest-h" className="font-medium">
              Your confirmations (needed for live sending)
            </h2>
            {Object.entries(data.attestation_labels).map(([key, label]) => (
              <CheckboxField
                key={key}
                label={label}
                checked={data.attestation[key]}
                onChange={(e) => attest(key, e.target.checked)}
              />
            ))}
          </section>
          <section className="space-y-2 rounded-2xl bg-white p-5 text-sm shadow-sm">
            <h2 className="font-medium">Delivery evidence</h2>
            <p className="text-muted">{data.delivery_evidence}</p>
            <p>
              Backend: <strong>{data.backend}</strong> (
              {data.backend_configured ? "configured" : "not configured"}) · rate limit{" "}
              {data.rate_per_minute}/min · test recipients configured: {data.test_recipients}
            </p>
            <p>
              Bounce/complaint feedback endpoint:{" "}
              <code className="break-all">{data.feedback_url}</code> (
              {data.feedback_configured ? "signing secret set" : "EMAIL_FEEDBACK_SECRET not set"})
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}

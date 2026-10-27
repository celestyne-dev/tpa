import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../../adminApiContext";
import { fieldError } from "../fieldError";
import { CheckboxField, SelectField, TextField } from "../Fields";
import { useNotify } from "../notifyContext";

const toNumber = (value) => (value === "" || value == null ? null : Number(value));

/**
 * Access rules for a resource: how long buyers keep access, how many downloads each buyer
 * gets and whether a future membership may unlock it. Like prices, they are live terms
 * (applied when access is granted) and need the price-management permission.
 */
export function ResourceAccessPanel({ product, canEdit, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const initial = {
    access_days: product.access_days ?? "",
    download_limit: product.download_limit ?? "",
    membership_eligible: Boolean(product.membership_eligible),
  };
  const [form, setForm] = useState(initial);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(form) !== JSON.stringify(initial);

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.products.update(product.id, {
        access_days: toNumber(form.access_days),
        download_limit: toNumber(form.download_limit),
        membership_eligible: form.membership_eligible,
      });
      notify("Access rules saved. They apply to access granted from now on.");
      onChanged?.();
    } catch (err) {
      setError(err);
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={save}
      aria-labelledby="access-rules"
      className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5"
    >
      <div>
        <h2 id="access-rules" className="text-lg font-medium">
          Access rules
        </h2>
        <p className="mt-1 text-sm text-muted">
          Applied when someone buys or claims this resource. Existing buyers keep the terms they
          received.
        </p>
      </div>
      <fieldset disabled={!canEdit || busy} className="grid gap-4 sm:grid-cols-2">
        <legend className="sr-only">Access rules</legend>
        <TextField
          label="Access period (days)"
          type="number"
          min={1}
          max={3650}
          inputMode="numeric"
          value={form.access_days}
          hint="Leave empty for lifetime access."
          error={fieldError(error, "access_days")}
          onChange={(e) => setForm({ ...form, access_days: e.target.value })}
        />
        <TextField
          label="Downloads per buyer"
          type="number"
          min={1}
          max={1000}
          inputMode="numeric"
          value={form.download_limit}
          hint={
            product.effective_download_limit && !product.download_limit
              ? `Leave empty to use the store setting (currently ${product.effective_download_limit}).`
              : "Leave empty to use the store setting (unlimited unless set in Payment settings)."
          }
          error={fieldError(error, "download_limit")}
          onChange={(e) => setForm({ ...form, download_limit: e.target.value })}
        />
        <div className="sm:col-span-2">
          <CheckboxField
            label="Can be included in a future membership"
            checked={form.membership_eligible}
            onChange={(e) => setForm({ ...form, membership_eligible: e.target.checked })}
          />
          <p className="mt-1 pl-7 text-xs text-muted">
            Memberships aren't available yet; this only prepares the resource for them.
          </p>
        </div>
      </fieldset>
      {canEdit ? (
        <Button type="submit" size="sm" disabled={!dirty || busy}>
          Save access rules
        </Button>
      ) : (
        <p className="text-sm text-muted">You can view these rules but not change them.</p>
      )}
    </form>
  );
}

/** Ordered related resources (part of the draft: shown publicly after publishing). */
export function RelatedResourcesEditor({ product, options, value, onChange, disabled }) {
  const [choice, setChoice] = useState("");
  const byId = Object.fromEntries((options.products ?? []).map((p) => [p.id, p]));
  const available = (options.products ?? []).filter(
    (p) => p.id !== product.id && !value.includes(p.id) && p.product_type !== "bundle",
  );
  const move = (index, delta) => {
    const next = [...value];
    [next[index], next[index + delta]] = [next[index + delta], next[index]];
    onChange(next);
  };
  return (
    <section aria-labelledby="related-resources" className="space-y-3">
      <div>
        <h2 id="related-resources" className="text-lg font-medium">
          Related resources
        </h2>
        <p className="mt-1 text-sm text-muted">
          Shown on this resource&apos;s page in this order (only published ones appear). Save the
          draft and publish to update the live page.
        </p>
      </div>
      {value.length === 0 ? (
        <p className="text-sm text-muted">
          None chosen: the page suggests resources from the same collections.
        </p>
      ) : (
        <ol className="space-y-2">
          {value.map((id, index) => (
            <li
              key={id}
              className="flex items-center justify-between gap-2 rounded-lg border border-charcoal/10 bg-white px-3 py-2 text-sm"
            >
              <span>
                {byId[id]?.title ?? `Resource ${id}`}
                {byId[id]?.status && byId[id].status !== "published" && (
                  <span className="ml-2 text-xs text-muted">({byId[id].status})</span>
                )}
              </span>
              <span className="flex gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Move ${byId[id]?.title ?? id} up`}
                  disabled={disabled || index === 0}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp aria-hidden />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Move ${byId[id]?.title ?? id} down`}
                  disabled={disabled || index === value.length - 1}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown aria-hidden />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Remove ${byId[id]?.title ?? id}`}
                  disabled={disabled}
                  onClick={() => onChange(value.filter((v) => v !== id))}
                >
                  <Trash2 aria-hidden />
                </Button>
              </span>
            </li>
          ))}
        </ol>
      )}
      {!disabled && value.length < 12 && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-56 flex-1">
            <SelectField
              label="Add a related resource"
              value={choice}
              options={[
                { value: "", label: "Choose a resource" },
                ...available.map((p) => ({ value: String(p.id), label: p.title })),
              ]}
              onChange={(e) => setChoice(e.target.value)}
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            disabled={!choice}
            onClick={() => {
              onChange([...value, Number(choice)]);
              setChoice("");
            }}
          >
            <Plus aria-hidden />
            Add
          </Button>
        </div>
      )}
    </section>
  );
}

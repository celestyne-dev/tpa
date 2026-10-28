import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { fieldError } from "../../components/fieldError";
import { CheckboxField, TextAreaField, TextField } from "../../components/Fields";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";

const INTERVALS = [
  { value: "month", label: "Monthly" },
  { value: "year", label: "Yearly" },
];

function toForm(plan) {
  return {
    name: plan.name,
    slug: plan.slug,
    tagline: plan.tagline,
    description: plan.description,
    benefits: plan.benefits.join("\n"),
    tier_rank: String(plan.tier_rank),
  };
}

function DetailsForm({ plan, canManage, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [form, setForm] = useState(() => toForm(plan));
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(form) !== JSON.stringify(toForm(plan));
  useUnsavedChanges(dirty);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body = {
        name: form.name,
        tagline: form.tagline,
        description: form.description,
        benefits: form.benefits
          .split("\n")
          .map((b) => b.trim())
          .filter(Boolean),
        tier_rank: Number(form.tier_rank),
        lock_version: plan.lock_version,
      };
      if (!plan.first_published_at) body.slug = form.slug;
      const res = await api.memberships.update(plan.id, body);
      notify("Plan saved.");
      onSaved(res.data);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };
  const err = (name) => fieldError(error, name);
  const editable = canManage && plan.status !== "archived";
  return (
    <form onSubmit={save} className="space-y-4" noValidate>
      <ErrorSummary error={error} />
      {error?.code === "edit_conflict" && (
        <p className="text-sm text-red-800">
          Someone else changed this plan. Reload the page to see their changes.
        </p>
      )}
      <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-lg font-medium sm:col-span-2">Plan content</legend>
        <TextField
          label="Name"
          required
          value={form.name}
          error={err("name")}
          onChange={(e) => set({ name: e.target.value })}
        />
        <TextField
          label="Slug"
          hint={
            plan.first_published_at
              ? "Published plans keep their address."
              : "Lowercase letters, numbers and hyphens."
          }
          value={form.slug}
          disabled={Boolean(plan.first_published_at)}
          error={err("slug")}
          onChange={(e) => set({ slug: e.target.value })}
        />
        <TextField
          className="sm:col-span-2"
          label="Tagline"
          value={form.tagline}
          error={err("tagline")}
          onChange={(e) => set({ tagline: e.target.value })}
        />
        <TextAreaField
          className="sm:col-span-2"
          label="Description"
          hint="Plain text. Leave a blank line between paragraphs."
          rows={6}
          value={form.description}
          error={err("description")}
          onChange={(e) => set({ description: e.target.value })}
        />
        <TextAreaField
          label="Benefits"
          hint="One benefit per line (up to 12)."
          rows={6}
          value={form.benefits}
          error={err("benefits")}
          onChange={(e) => set({ benefits: e.target.value })}
        />
        <TextField
          label="Tier rank"
          hint="1 is the first paid tier; higher numbers are higher tiers."
          type="number"
          min="1"
          max="100"
          value={form.tier_rank}
          error={err("tier_rank")}
          onChange={(e) => set({ tier_rank: e.target.value })}
        />
      </fieldset>
      {editable && (
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={saving || !dirty}>
            {saving ? "Saving…" : "Save content"}
          </Button>
          <span aria-live="polite" className="text-sm text-muted">
            {dirty ? "Unsaved changes" : ""}
          </span>
        </div>
      )}
    </form>
  );
}

function PricesSection({ plan, canManage, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [amounts, setAmounts] = useState({ month: "", year: "" });
  const [error, setError] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const editable = canManage && plan.status !== "archived";
  const run = async (action, message) => {
    setError(null);
    try {
      const res = await action();
      notify(message);
      onSaved(res.data);
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  };
  const addPrice = async (event, interval) => {
    event.preventDefault();
    const ok = await run(
      () =>
        api.memberships.addPrice(plan.id, {
          interval,
          amount: amounts[interval],
          currency: "USD",
          lock_version: plan.lock_version,
        }),
      "Price saved.",
    );
    if (ok) setAmounts((a) => ({ ...a, [interval]: "" }));
  };
  const remove = async () => {
    const price = confirm;
    setConfirm(null);
    await run(
      () => api.memberships.removePrice(plan.id, price.id, { lock_version: plan.lock_version }),
      price.shown_at ? "Price retired." : "Price removed.",
    );
  };
  return (
    <section aria-labelledby="prices-heading" className="space-y-4">
      <h2 id="prices-heading" className="text-lg font-medium">
        Prices (USD)
      </h2>
      <p className="text-sm text-muted">
        Prices are never edited: a new price replaces the current one, and earlier prices are kept
        in the history. The server checks every amount; nothing is converted between currencies.
      </p>
      <ErrorSummary error={error} title="The price wasn't saved" />
      <div className="grid gap-4 md:grid-cols-2">
        {INTERVALS.map(({ value, label }) => {
          const current = plan.prices[value];
          return (
            <form
              key={value}
              onSubmit={(e) => addPrice(e, value)}
              aria-label={`${label} price`}
              className="space-y-3 rounded-xl border border-charcoal/10 bg-white p-4"
              noValidate
            >
              <p className="font-medium">{label}</p>
              <p className="text-2xl font-semibold">
                {current ? current.price.formatted : <span className="text-muted">Not set</span>}
              </p>
              {editable && (
                <>
                  <TextField
                    label={`New ${label.toLowerCase()} price (USD)`}
                    inputMode="decimal"
                    placeholder="9.99"
                    value={amounts[value]}
                    onChange={(e) => setAmounts((a) => ({ ...a, [value]: e.target.value }))}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button type="submit" size="sm" disabled={!amounts[value].trim()}>
                      {current ? "Replace price" : "Set price"}
                    </Button>
                    {current && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setConfirm(current)}
                      >
                        {current.shown_at ? "Retire price" : "Remove price"}
                      </Button>
                    )}
                  </div>
                </>
              )}
            </form>
          );
        })}
      </div>
      {plan.price_history.length > 0 && (
        <details className="rounded-xl border border-charcoal/10 bg-white p-4 text-sm">
          <summary className="cursor-pointer font-medium">Price history</summary>
          <ul className="mt-2 space-y-1">
            {plan.price_history.map((p) => (
              <li key={p.id}>
                {p.interval === "month" ? "Monthly" : "Yearly"} {p.price.formatted} · {p.status}
                {p.shown_at ? " · was public" : ""} · added {formatDateTime(p.created_at)}
                {p.retired_at ? ` · retired ${formatDateTime(p.retired_at)}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm?.shown_at ? "Retire this price?" : "Remove this price?"}
        message={
          confirm?.shown_at
            ? "It has been public, so it is kept in the history as retired."
            : "It has never been public, so it is removed."
        }
        confirmLabel={confirm?.shown_at ? "Retire" : "Remove"}
        onConfirm={remove}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}

const INTERVAL_NAME = { month: "Monthly", year: "Yearly" };

/** Links each active price to a Paystack plan (test mode only) and shows what is linked. */
function PaystackSection({ plan, canManage, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const sync = async () => {
    setError(null);
    setBusy(true);
    try {
      const res = await api.memberships.providerSync(plan.id, { lock_version: plan.lock_version });
      notify("Paystack test plans are in sync.");
      onSaved(res.data);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const linked = plan.provider_plans ?? [];
  return (
    <section aria-labelledby="paystack-heading" className="space-y-4">
      <h2 id="paystack-heading" className="text-lg font-medium">
        Paystack plans (test mode)
      </h2>
      <p className="text-sm text-muted">
        Each active price needs a matching Paystack plan before members can join. Syncing creates
        missing plans in the Paystack test account and checks existing ones still match the amount,
        currency and interval. Live plans are never created here.
      </p>
      <ErrorSummary error={error} title="Paystack plans weren't synced" />
      {linked.length > 0 ? (
        <ul aria-label="Linked Paystack plans" className="space-y-1 text-sm">
          {linked.map((p) => (
            <li key={`${p.price_id}-${p.mode}`}>
              {INTERVAL_NAME[p.interval]} ({p.mode}): <code>{p.plan_code}</code>
              {p.verified_at ? " · checked" : " · not checked"}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm">No Paystack plans are linked yet.</p>
      )}
      {canManage && plan.status !== "archived" && (
        <Button size="sm" variant="outline" onClick={sync} disabled={busy}>
          {busy ? "Syncing…" : "Sync with Paystack (test)"}
        </Button>
      )}
    </section>
  );
}

function AccessSection({ plan, canManage, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const options = useAdminQuery(() => api.memberships.eligibleProducts(), []);
  const initial = useMemo(() => plan.included.map((i) => i.product_id), [plan]);
  const [selected, setSelected] = useState(initial);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const editable = canManage && plan.status !== "archived";
  const dirty = JSON.stringify([...selected].sort()) !== JSON.stringify([...initial].sort());
  // Included items that are no longer eligible stay listed (with the reason) until removed.
  const items = useMemo(() => {
    const list = [...(options.data ?? [])];
    for (const item of plan.included) {
      if (!list.some((o) => o.product_id === item.product_id)) list.push(item);
    }
    const q = filter.trim().toLowerCase();
    return list.filter((i) => !q || i.title.toLowerCase().includes(q));
  }, [options.data, plan.included, filter]);
  const problems = Object.fromEntries(plan.included.map((i) => [i.product_id, i.problem]));
  const toggle = (id, checked) =>
    setSelected((s) => (checked ? [...s, id] : s.filter((x) => x !== id)));
  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await api.memberships.setAccess(plan.id, {
        product_ids: selected,
        lock_version: plan.lock_version,
      });
      notify("Included courses and resources saved.");
      onSaved(res.data);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };
  const group = (kind) => items.filter((i) => i.kind === kind);
  return (
    <section aria-labelledby="access-heading" className="space-y-4">
      <h2 id="access-heading" className="text-lg font-medium">
        Included courses and resources
      </h2>
      <p className="text-sm text-muted">
        Only products marked “Included in memberships” in their resource access settings can be
        chosen. Members get access only after Paystack confirms their payment.
      </p>
      <ErrorSummary error={error} title="The selection wasn't saved" />
      <TextField
        label="Filter by title"
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      {options.loading && !options.data ? (
        <p role="status">Loading eligible products…</p>
      ) : options.error ? (
        <ErrorSummary error={options.error} title="We couldn't load eligible products" />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {[
            ["course", "Courses"],
            ["resource", "Resources"],
          ].map(([kind, label]) => (
            <fieldset
              key={kind}
              disabled={!editable}
              className="space-y-2 rounded-xl border border-charcoal/10 bg-white p-4"
            >
              <legend className="px-1 font-medium">{label}</legend>
              {group(kind).length === 0 && (
                <p className="text-sm text-muted">No eligible {label.toLowerCase()}.</p>
              )}
              {group(kind).map((item) => (
                <div key={item.product_id}>
                  <CheckboxField
                    label={item.course?.title ?? item.title}
                    hint={`${item.type_label}${item.status === "draft" ? " · draft (hidden publicly until published)" : ""}`}
                    checked={selected.includes(item.product_id)}
                    onChange={(e) => toggle(item.product_id, e.target.checked)}
                  />
                  {problems[item.product_id] && (
                    <p className="ml-7 text-xs text-red-800">{problems[item.product_id]}</p>
                  )}
                </div>
              ))}
            </fieldset>
          ))}
        </div>
      )}
      {editable && (
        <Button onClick={save} disabled={saving || !dirty}>
          {saving ? "Saving…" : `Save included items (${selected.length})`}
        </Button>
      )}
    </section>
  );
}

/** One membership plan: content, prices, included products and publication. */
export function MembershipPlanEditorPage() {
  const { planId } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const {
    data: plan,
    error,
    loading,
    reload,
    setData,
  } = useAdminQuery(() => api.memberships.get(planId), [planId]);
  const [statusError, setStatusError] = useState(null);
  const [confirmArchive, setConfirmArchive] = useState(false);
  if (error) return <ErrorState title="We couldn't load this plan" onRetry={reload} />;
  if (loading && !plan) return <p role="status">Loading plan…</p>;
  const canManage = can("memberships.manage");
  const canPublish = can("memberships.publish");
  const setStatus = async (status) => {
    setStatusError(null);
    setConfirmArchive(false);
    try {
      const res = await api.memberships.setStatus(plan.id, {
        status,
        lock_version: plan.lock_version,
      });
      setData(res.data);
      notify(
        status === "published"
          ? "Plan published."
          : status === "archived"
            ? "Plan archived."
            : "Plan moved to draft.",
      );
    } catch (err) {
      setStatusError(err);
    }
  };
  return (
    <>
      <AdminPageHeader
        title={plan.name}
        description={
          plan.status === "published"
            ? `Published · ${formatDateTime(plan.published_at)}`
            : plan.status === "archived"
              ? "Archived — hidden from the membership page"
              : "Draft — not shown publicly"
        }
        breadcrumbs={[
          { label: "Membership plans", to: "/admin/membership-plans" },
          { label: plan.name },
        ]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={plan.status} />
            {canPublish && plan.status !== "published" && (
              <Button size="sm" onClick={() => setStatus("published")}>
                Publish
              </Button>
            )}
            {canPublish && plan.status === "published" && (
              <Button size="sm" variant="outline" onClick={() => setStatus("draft")}>
                Unpublish
              </Button>
            )}
            {canPublish && plan.status === "archived" && (
              <Button size="sm" variant="outline" onClick={() => setStatus("draft")}>
                Restore as draft
              </Button>
            )}
            {canPublish && plan.status !== "archived" && (
              <Button size="sm" variant="outline" onClick={() => setConfirmArchive(true)}>
                Archive
              </Button>
            )}
          </div>
        }
      />
      <div className="mb-6 space-y-3">
        <p role="note" className="rounded-xl bg-cream p-3 text-sm">
          {plan.billing.message} Publishing shows the plan on{" "}
          <Link to="/membership" className="underline underline-offset-4">
            /membership
          </Link>
          {plan.billing.available ? "." : " with a “coming soon” notice."}
        </p>
        {plan.readiness.length > 0 && (
          <div className="rounded-xl border border-gold-300 bg-gold-100/40 p-4 text-sm">
            <p className="font-medium">Before publishing</p>
            <ul className="mt-1 list-disc pl-5">
              {plan.readiness.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
        <ErrorSummary error={statusError} title="The plan's status wasn't changed" />
        {!canManage && (
          <p className="text-sm text-muted">Your role can view this plan but not change it.</p>
        )}
      </div>
      <div className="max-w-4xl space-y-10">
        <DetailsForm key={plan.lock_version} plan={plan} canManage={canManage} onSaved={setData} />
        <PricesSection plan={plan} canManage={canManage} onSaved={setData} />
        <PaystackSection plan={plan} canManage={canManage} onSaved={setData} />
        <AccessSection
          key={`access-${plan.lock_version}`}
          plan={plan}
          canManage={canManage}
          onSaved={setData}
        />
      </div>
      <ConfirmDialog
        open={confirmArchive}
        title="Archive this plan?"
        message="It is hidden from the membership page and can no longer be edited until restored."
        confirmLabel="Archive"
        onConfirm={() => setStatus("archived")}
        onCancel={() => setConfirmArchive(false)}
      />
    </>
  );
}

import { CalendarRange, KanbanSquare, Megaphone, Plus, Receipt } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { useNotify } from "../../components/notifyContext";
import { CURRENCIES, label, money } from "../../components/partnerships/formValues";
import { RecordDialog, Tabs } from "../../components/partnerships/RecordDialog";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { CHANNELS, PLACEMENT_TYPES, PRICING_MODELS, toOptions } from "./options";

function useAction(reload) {
  const notify = useNotify();
  return async (fn, message) => {
    try {
      await fn();
      notify(message);
      reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };
}

function MoveButtons({ allowed, onMove }) {
  return (
    <div className="flex flex-wrap gap-1">
      {allowed.map((s) => (
        <Button key={s} size="sm" variant="outline" onClick={() => onMove(s)}>
          {label(s)}
        </Button>
      ))}
    </div>
  );
}

// ---- opportunities ------------------------------------------------------------------------

function Opportunities({ options }) {
  const api = useAdminApi();
  const { can } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(
    () => api.opportunities.list({ page_size: 100 }),
    [],
  );
  const run = useAction(reload);
  const [editing, setEditing] = useState(null);
  const [note, setNote] = useState(null);
  const manage = can("partnerships.manage");
  const fields = [
    ...(editing?.id
      ? []
      : [
          {
            name: "partner_id",
            label: "Partner",
            type: "id",
            required: true,
            options: toOptions(options?.partners),
          },
        ]),
    { name: "title", label: "Opportunity", required: true },
    { name: "owner_id", label: "Manager", type: "id", options: toOptions(options?.users) },
    { name: "currency", label: "Currency", type: "select", required: true, options: CURRENCIES },
    {
      name: "expected_value_minor",
      label: "Expected value (estimate, not revenue)",
      type: "money",
    },
    { name: "follow_up_on", label: "Follow up on", type: "date" },
    { name: "proposal_reference", label: "Proposal reference or link" },
    { name: "internal_reference", label: "Internal reference" },
    { name: "notes", label: "Negotiation notes (confidential)", type: "textarea" },
  ];
  if (error) return <ErrorState title="We couldn't load opportunities" onRetry={reload} />;
  return (
    <>
      {manage && (
        <Button className="mb-4" onClick={() => setEditing({ currency: "USD" })}>
          <Plus aria-hidden className="size-4" /> New opportunity
        </Button>
      )}
      <DataTable
        caption="Opportunities"
        rows={data}
        loading={loading}
        empty={{ icon: KanbanSquare, title: "No opportunities yet" }}
        columns={[
          {
            key: "title",
            header: "Opportunity",
            render: (o) => (
              <div>
                <button
                  type="button"
                  className="font-medium hover:underline"
                  disabled={!manage}
                  onClick={async () => setEditing((await api.opportunities.get(o.id)).data)}
                >
                  {o.title}
                </button>
                <p className="text-xs text-muted">{o.partner.name}</p>
              </div>
            ),
          },
          { key: "stage", header: "Stage", render: (o) => <StatusBadge status={label(o.stage)} /> },
          {
            key: "value",
            header: "Expected (estimate)",
            render: (o) => money(o.expected_value_minor, o.currency),
          },
          { key: "follow", header: "Follow up", render: (o) => o.follow_up_on ?? "—" },
          {
            key: "move",
            header: "Move to",
            render: (o) =>
              manage && (
                <div className="flex flex-wrap gap-1">
                  <MoveButtons
                    allowed={o.allowed_stages}
                    onMove={(stage) => {
                      const body = { stage };
                      if (stage === "lost") {
                        const reason = window.prompt("Why was it lost?");
                        if (!reason) return;
                        body.reason = reason;
                      }
                      run(() => api.opportunities.move(o.id, body), "Stage updated.");
                    }}
                  />
                  <Button size="sm" variant="outline" onClick={() => setNote(o)}>
                    Log interaction
                  </Button>
                </div>
              ),
          },
        ]}
      />
      {editing && (
        <RecordDialog
          title={editing.id ? `Edit ${editing.title}` : "New opportunity"}
          fields={fields}
          record={editing}
          onClose={() => setEditing(null)}
          onSave={async (body) => {
            if (editing.id) await api.opportunities.update(editing.id, body);
            else await api.opportunities.create(body);
            setEditing(null);
            reload();
          }}
        >
          {() =>
            editing.history?.length > 0 && (
              <div className="sm:col-span-2">
                <p className="text-sm font-medium">History</p>
                <ul className="mt-1 max-h-40 overflow-auto text-xs text-muted">
                  {editing.history.map((h, i) => (
                    <li key={i}>
                      {h.at?.slice(0, 16).replace("T", " ")} · {label(h.kind)}
                      {h.to ? ` → ${label(h.to)}` : ""} {h.summary}
                    </li>
                  ))}
                </ul>
              </div>
            )
          }
        </RecordDialog>
      )}
      {note && (
        <RecordDialog
          title={`Log interaction: ${note.title}`}
          fields={[
            {
              name: "kind",
              label: "Type",
              type: "select",
              required: true,
              default: "call",
              options: ["call", "email", "meeting", "note"].map((v) => ({ value: v, label: v })),
            },
            { name: "occurred_on", label: "Date", type: "date" },
            { name: "summary", label: "Summary", type: "textarea", required: true },
            { name: "follow_up_on", label: "Next follow-up", type: "date" },
          ]}
          onClose={() => setNote(null)}
          onSave={async (body) => {
            await api.opportunities.interact(note.id, body);
            setNote(null);
            reload();
          }}
        />
      )}
    </>
  );
}

// ---- campaigns ----------------------------------------------------------------------------

function Campaigns({ options }) {
  const api = useAdminApi();
  const { can, canAny } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(
    () => api.sponsorshipCampaigns.list({ page_size: 100 }),
    [],
  );
  const run = useAction(reload);
  const [editing, setEditing] = useState(null);
  const fields = [
    ...(editing?.id
      ? []
      : [
          {
            name: "partner_id",
            label: "Partner",
            type: "id",
            required: true,
            options: toOptions(options?.partners),
          },
        ]),
    { name: "name", label: "Campaign", required: true },
    { name: "starts_on", label: "Starts", type: "date" },
    { name: "ends_on", label: "Ends", type: "date" },
    { name: "currency", label: "Currency", type: "select", required: true, options: CURRENCIES },
    {
      name: "contracted_fee_minor",
      label: "Contracted fee",
      type: "money",
      hint: "As agreed in writing.",
    },
    {
      name: "disclosure_text",
      label: "Disclosure shown to readers",
      wide: true,
      required: true,
      hint: "For example: “This campaign is sponsored by Calm Co.”",
    },
    { name: "notes", label: "Internal notes", type: "textarea" },
  ];
  if (error) return <ErrorState title="We couldn't load campaigns" onRetry={reload} />;
  return (
    <>
      {can("sponsorships.manage") && (
        <Button className="mb-4" onClick={() => setEditing({ currency: "USD" })}>
          <Plus aria-hidden className="size-4" /> New campaign
        </Button>
      )}
      <p className="mb-3 text-sm text-muted">
        Editing an approved or scheduled campaign sends it back to draft for re-approval. Approval
        needs the sponsorship approval permission.
      </p>
      <DataTable
        caption="Campaigns"
        rows={data}
        loading={loading}
        empty={{ icon: Megaphone, title: "No campaigns yet" }}
        columns={[
          {
            key: "name",
            header: "Campaign",
            render: (c) => (
              <div>
                <button
                  type="button"
                  className="font-medium hover:underline"
                  onClick={async () => setEditing((await api.sponsorshipCampaigns.get(c.id)).data)}
                >
                  {c.name}
                </button>
                <p className="text-xs text-muted">{c.partner.name}</p>
              </div>
            ),
          },
          {
            key: "status",
            header: "Status",
            render: (c) => <StatusBadge status={label(c.status)} />,
          },
          {
            key: "dates",
            header: "Dates",
            render: (c) => `${c.starts_on ?? "?"} → ${c.ends_on ?? "?"}`,
          },
          {
            key: "fee",
            header: "Contracted",
            render: (c) => money(c.contracted_fee_minor, c.currency),
          },
          {
            key: "move",
            header: "Move to",
            render: (c) =>
              canAny("sponsorships.manage", "sponsorships.approve") && (
                <MoveButtons
                  allowed={c.allowed_statuses}
                  onMove={(status) =>
                    run(() => api.sponsorshipCampaigns.move(c.id, status), "Status updated.")
                  }
                />
              ),
          },
        ]}
      />
      {editing && (
        <RecordDialog
          title={editing.id ? `Edit ${editing.name}` : "New campaign"}
          fields={fields.map((f) => ({ ...f, readOnly: !can("sponsorships.manage") }))}
          record={editing}
          onClose={() => setEditing(null)}
          onSave={async (body) => {
            if (editing.id) await api.sponsorshipCampaigns.update(editing.id, body);
            else await api.sponsorshipCampaigns.create(body);
            setEditing(null);
            reload();
          }}
        />
      )}
    </>
  );
}

// ---- bookings -----------------------------------------------------------------------------

function Bookings({ options }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const [upcoming, setUpcoming] = useState(true);
  const { data, error, loading, reload } = useAdminQuery(
    () => api.adBookings.list(upcoming ? { upcoming: 1 } : {}),
    [upcoming],
  );
  const run = useAction(reload);
  const [editing, setEditing] = useState(null);
  const manage = can("advertising.manage_bookings");
  const fields = [
    {
      name: "placement_id",
      label: "Placement",
      type: "id",
      required: true,
      options: toOptions((options?.placements ?? []).filter((p) => p.is_active)),
    },
    {
      name: "partner_id",
      label: "Partner",
      type: "id",
      required: true,
      options: toOptions(options?.partners),
    },
    { name: "campaign_id", label: "Campaign", type: "id", options: toOptions(options?.campaigns) },
    { name: "starts_at", label: "Starts (your local time)", type: "datetime", required: true },
    { name: "ends_at", label: "Ends (your local time)", type: "datetime", required: true },
    { name: "currency", label: "Currency", type: "select", required: true, options: CURRENCIES },
    { name: "agreed_fee_minor", label: "Agreed fee", type: "money" },
    { name: "headline", label: "Creative headline" },
    { name: "link_label", label: "Link label" },
    { name: "link_url", label: "Link (https:// or a site path)", wide: true },
    { name: "image_media_id", label: "Image (media library ID)", type: "number" },
    { name: "body", label: "Creative text", type: "textarea" },
    { name: "notes", label: "Internal notes", type: "textarea" },
  ];
  const save = async (body) => {
    const res = editing.id
      ? await api.adBookings.update(editing.id, body)
      : await api.adBookings.create(body);
    const warnings = res.meta?.conflicts?.warnings ?? [];
    if (warnings.length)
      notify(`Saved. Overlaps pending booking(s) ${warnings.map((w) => `#${w.id}`).join(", ")}.`);
    setEditing(null);
    reload();
  };
  if (error) return <ErrorState title="We couldn't load bookings" onRetry={reload} />;
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {manage && (
          <Button onClick={() => setEditing({ currency: "USD" })}>
            <Plus aria-hidden className="size-4" /> New booking
          </Button>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={upcoming}
            onChange={(e) => setUpcoming(e.target.checked)}
          />
          Upcoming and live only
        </label>
      </div>
      <p className="mb-3 text-sm text-muted">
        Only approved bookings are shown on the site, and only between their start and end.
        Exclusive placements can't be double-booked.
      </p>
      <DataTable
        caption="Bookings"
        rows={data}
        loading={loading}
        empty={{ icon: CalendarRange, title: "No bookings" }}
        columns={[
          {
            key: "placement",
            header: "Placement",
            render: (b) => (
              <div>
                <button
                  type="button"
                  className="font-medium hover:underline"
                  disabled={!manage}
                  onClick={() => setEditing(b)}
                >
                  {b.placement.name}
                </button>
                <p className="text-xs text-muted">{b.partner.name}</p>
              </div>
            ),
          },
          {
            key: "window",
            header: "When",
            render: (b) =>
              `${new Date(b.starts_at).toLocaleString()} → ${new Date(b.ends_at).toLocaleString()}`,
          },
          {
            key: "status",
            header: "Status",
            render: (b) => (
              <div className="flex flex-col gap-1">
                <StatusBadge status={b.status} />
                <span className="text-xs text-muted">
                  {b.status === "approved" ? b.state : "not shown"}
                </span>
              </div>
            ),
          },
          {
            key: "fee",
            header: "Agreed fee",
            render: (b) => money(b.agreed_fee_minor, b.currency),
          },
          {
            key: "move",
            header: "Actions",
            render: (b) =>
              manage && (
                <MoveButtons
                  allowed={b.allowed_statuses}
                  onMove={(status) =>
                    run(() => api.adBookings.move(b.id, status), "Booking updated.")
                  }
                />
              ),
          },
        ]}
      />
      {editing && (
        <RecordDialog
          title={editing.id ? `Edit booking #${editing.id}` : "New booking"}
          fields={fields}
          record={{
            ...editing,
            placement_id: editing.placement?.id ?? editing.placement_id,
            partner_id: editing.partner?.id ?? editing.partner_id,
          }}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
    </>
  );
}

// ---- inventory and rate cards ------------------------------------------------------------

function Inventory() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const placements = useAdminQuery(() => api.adPlacements.list(), []);
  const rates = useAdminQuery(() => api.rateCards.list(), []);
  const [editing, setEditing] = useState(null);
  const manage = can("advertising.manage_inventory");
  const placementFields = [
    { name: "name", label: "Name", required: true },
    {
      name: "key",
      label: "Key",
      required: true,
      hint: "Used by page sections, e.g. homepage_sponsor.",
    },
    {
      name: "placement_type",
      label: "Type",
      type: "select",
      required: true,
      options: PLACEMENT_TYPES,
    },
    { name: "channel", label: "Channel", type: "select", required: true, options: CHANNELS },
    { name: "dimensions", label: "Dimensions", hint: "e.g. 1200×400" },
    {
      name: "creative_formats",
      label: "Creative formats (one per line)",
      type: "lines",
      hint: "image, text, logo, article, newsletter_block",
    },
    {
      name: "pricing_model",
      label: "Pricing model",
      type: "select",
      required: true,
      options: PRICING_MODELS,
      hint: "CPM needs reliable impression measurement.",
    },
    {
      name: "default_currency",
      label: "Default currency",
      type: "select",
      required: true,
      options: CURRENCIES,
    },
    { name: "capacity", label: "Concurrent bookings allowed", type: "number" },
    { name: "exclusive", label: "Exclusive (one booking at a time)", type: "checkbox" },
    { name: "impressions_measured", label: "Impressions are reliably measured", type: "checkbox" },
    { name: "is_active", label: "Active", type: "checkbox", default: true },
    { name: "restrictions", label: "Restrictions", type: "textarea" },
    { name: "internal_notes", label: "Internal notes", type: "textarea" },
  ];
  const rateFields = [
    { name: "name", label: "Name", required: true },
    { name: "placement_id", label: "Placement", type: "id", options: toOptions(placements.data) },
    {
      name: "pricing_model",
      label: "Pricing model",
      type: "select",
      required: true,
      options: PRICING_MODELS,
    },
    { name: "currency", label: "Currency", type: "select", required: true, options: CURRENCIES },
    { name: "amount_minor", label: "Indicative amount", type: "money", required: true },
    { name: "unit_label", label: "Unit", hint: "e.g. per week" },
    { name: "valid_from", label: "Valid from", type: "date" },
    { name: "valid_until", label: "Valid until", type: "date" },
    { name: "is_public", label: "Show on the public media kit", type: "checkbox" },
    { name: "description", label: "Description", type: "textarea" },
  ];
  const save = async (kind, body) => {
    const target = kind === "placement" ? api.adPlacements : api.rateCards;
    if (editing.record?.id) await target.update(editing.record.id, body);
    else await target.create(body);
    setEditing(null);
    (kind === "placement" ? placements : rates).reload();
  };
  return (
    <>
      {manage && (
        <div className="mb-4 flex gap-2">
          <Button
            onClick={() =>
              setEditing({
                kind: "placement",
                record: {
                  channel: "website",
                  pricing_model: "fixed_fee",
                  default_currency: "USD",
                  capacity: 1,
                },
              })
            }
          >
            <Plus aria-hidden className="size-4" /> New placement
          </Button>
          <Button
            variant="outline"
            onClick={() =>
              setEditing({ kind: "rate", record: { pricing_model: "fixed_fee", currency: "USD" } })
            }
          >
            <Plus aria-hidden className="size-4" /> New rate
          </Button>
        </div>
      )}
      <DataTable
        caption="Placements"
        rows={placements.data}
        loading={placements.loading}
        empty={{ icon: Megaphone, title: "No placements yet" }}
        columns={[
          {
            key: "name",
            header: "Placement",
            render: (p) => (
              <button
                type="button"
                className="font-medium hover:underline"
                disabled={!manage}
                onClick={() => setEditing({ kind: "placement", record: p })}
              >
                {p.name}
              </button>
            ),
          },
          { key: "key", header: "Key", render: (p) => <code>{p.key}</code> },
          { key: "type", header: "Type", render: (p) => label(p.placement_type) },
          {
            key: "excl",
            header: "Availability",
            render: (p) => (p.exclusive ? "Exclusive" : `${p.capacity} at a time`),
          },
          {
            key: "active",
            header: "Status",
            render: (p) => <StatusBadge status={p.is_active ? "active" : "inactive"} />,
          },
        ]}
      />
      <h2 className="mt-8 mb-2 text-lg font-medium">Rate card (indicative)</h2>
      <DataTable
        caption="Rate card"
        rows={rates.data}
        loading={rates.loading}
        empty={{ icon: Receipt, title: "No rates yet" }}
        columns={[
          {
            key: "name",
            header: "Rate",
            render: (r) => (
              <button
                type="button"
                className="font-medium hover:underline"
                disabled={!manage}
                onClick={() => setEditing({ kind: "rate", record: r })}
              >
                {r.name}
              </button>
            ),
          },
          { key: "model", header: "Model", render: (r) => label(r.pricing_model) },
          {
            key: "amount",
            header: "Amount",
            render: (r) => `${money(r.amount_minor, r.currency)} ${r.unit_label ?? ""}`,
          },
          { key: "public", header: "Public", render: (r) => (r.is_public ? "Yes" : "No") },
        ]}
      />
      {editing && (
        <RecordDialog
          title={editing.kind === "placement" ? "Placement" : "Rate"}
          fields={editing.kind === "placement" ? placementFields : rateFields}
          record={editing.record}
          onClose={() => setEditing(null)}
          onSave={(body) => save(editing.kind, body)}
        />
      )}
    </>
  );
}

// ---- finance (manual records) -------------------------------------------------------------

function Finance({ options }) {
  const api = useAdminApi();
  const { can } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(() => api.partnershipFinance.list({}), []);
  const [adding, setAdding] = useState(false);
  if (error) return <ErrorState title="We couldn't load finance records" onRetry={reload} />;
  return (
    <>
      <p className="mb-3 text-sm text-muted">
        Manual records of invoices you issued elsewhere and payments you received. This system never
        issues invoices or takes payments. Only verified receipts count as received.
      </p>
      {can("partnership_finance.manage") && (
        <Button className="mb-4" onClick={() => setAdding(true)}>
          <Plus aria-hidden className="size-4" /> Record invoice or payment
        </Button>
      )}
      <DataTable
        caption="Finance records"
        rows={data}
        loading={loading}
        empty={{ icon: Receipt, title: "No records yet" }}
        columns={[
          { key: "date", header: "Date", render: (e) => e.entry_date },
          { key: "kind", header: "Kind", render: (e) => label(e.kind) },
          { key: "amount", header: "Amount", render: (e) => money(e.amount_minor, e.currency) },
          {
            key: "verified",
            header: "Verified",
            render: (e) => (e.kind === "received" ? (e.verified ? "Yes" : "No") : "—"),
          },
          { key: "ref", header: "Reference", render: (e) => e.reference || "—" },
        ]}
      />
      {adding && (
        <RecordDialog
          title="Record invoice or payment"
          fields={[
            {
              name: "kind",
              label: "Kind",
              type: "select",
              required: true,
              default: "invoiced",
              options: [
                { value: "invoiced", label: "Invoice issued" },
                { value: "received", label: "Payment received" },
              ],
            },
            {
              name: "partner_id",
              label: "Partner",
              type: "id",
              required: true,
              options: toOptions(options?.partners),
            },
            {
              name: "campaign_id",
              label: "Campaign",
              type: "id",
              options: toOptions(options?.campaigns),
            },
            {
              name: "currency",
              label: "Currency",
              type: "select",
              required: true,
              default: "USD",
              options: CURRENCIES,
            },
            { name: "amount_minor", label: "Amount", type: "money", required: true },
            { name: "entry_date", label: "Date", type: "date", required: true },
            { name: "reference", label: "Invoice or payment reference" },
            {
              name: "verified",
              label: "Verified against the bank or payment provider",
              type: "checkbox",
            },
            { name: "notes", label: "Notes", type: "textarea" },
          ]}
          onClose={() => setAdding(false)}
          onSave={async (body) => {
            await api.partnershipFinance.create(body);
            setAdding(false);
            reload();
          }}
        />
      )}
    </>
  );
}

export function SponsorshipsPage() {
  const api = useAdminApi();
  const { can, canAny } = usePermissions();
  const options = useAdminQuery(() => api.partnershipOptions(), []);
  const tabs = [
    can("partnerships.view") && ["opportunities", "Opportunities"],
    can("sponsorships.view") && ["campaigns", "Campaigns"],
    can("advertising.view") && ["bookings", "Bookings"],
    canAny("advertising.view", "advertising.manage_inventory") && [
      "inventory",
      "Inventory & rates",
    ],
    can("partnership_finance.view") && ["finance", "Invoices & payments"],
  ].filter(Boolean);
  const [tab, setTab] = useState(tabs[0]?.[0]);
  const views = {
    opportunities: Opportunities,
    campaigns: Campaigns,
    bookings: Bookings,
    inventory: Inventory,
    finance: Finance,
  };
  const View = views[tab];
  return (
    <>
      <AdminPageHeader
        title="Sponsorships"
        description="Pipeline, campaigns, advertising bookings and inventory. Expected values are estimates; nothing here is realised revenue until recorded as received."
        breadcrumbs={[{ label: "Sponsorships" }]}
      />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {View && <View key={tab} options={options.data} />}
    </>
  );
}

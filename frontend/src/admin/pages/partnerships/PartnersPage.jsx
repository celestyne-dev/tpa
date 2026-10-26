import { Handshake, Inbox, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { useNotify } from "../../components/notifyContext";
import { label } from "../../components/partnerships/formValues";
import { RecordDialog } from "../../components/partnerships/RecordDialog";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { INQUIRY_STATUSES, PARTNER_STATUSES, PARTNERSHIP_TYPES, toOptions } from "./options";

function partnerFields(users) {
  return [
    { name: "name", label: "Organisation", required: true },
    { name: "website", label: "Website", hint: "https:// only." },
    { name: "industry", label: "Industry" },
    { name: "country", label: "Country" },
    {
      name: "partnership_type",
      label: "Partnership type",
      type: "select",
      required: true,
      options: PARTNERSHIP_TYPES,
    },
    { name: "status", label: "Status", type: "select", required: true, options: PARTNER_STATUSES },
    { name: "source", label: "Source", hint: "How they found us, e.g. inquiry form or referral." },
    { name: "owner_id", label: "Relationship owner", type: "id", options: toOptions(users) },
    {
      name: "logo_media_id",
      label: "Logo (media library ID)",
      type: "id-number",
      hint: "Optional: the ID of an image in the media library.",
    },
    { name: "description", label: "Description", type: "textarea" },
    { name: "internal_notes", label: "Internal notes (confidential)", type: "textarea", rows: 4 },
  ].map((f) => (f.type === "id-number" ? { ...f, type: "number" } : f));
}

function ContactsEditor({ contacts, onChange }) {
  const update = (i, patch) => onChange(contacts.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <fieldset className="sm:col-span-2">
      <legend className="text-sm font-medium">Contacts</legend>
      <p className="text-xs text-muted">
        Work contact details only: name, business email and role.
      </p>
      {contacts.map((c, i) => (
        <div key={i} className="mt-2 grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
          <input
            aria-label="Contact name"
            className="rounded-lg border px-3 py-2 text-sm"
            value={c.name}
            onChange={(e) => update(i, { name: e.target.value })}
            placeholder="Name"
          />
          <input
            aria-label="Contact email"
            className="rounded-lg border px-3 py-2 text-sm"
            value={c.email}
            onChange={(e) => update(i, { email: e.target.value })}
            placeholder="Email"
          />
          <input
            aria-label="Contact role"
            className="rounded-lg border px-3 py-2 text-sm"
            value={c.role}
            onChange={(e) => update(i, { role: e.target.value })}
            placeholder="Role"
          />
          <Button
            variant="outline"
            size="sm"
            type="button"
            onClick={() => onChange(contacts.filter((_, j) => j !== i))}
          >
            Remove
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        type="button"
        className="mt-2"
        onClick={() => onChange([...contacts, { name: "", email: "", role: "" }])}
      >
        Add contact
      </Button>
    </fieldset>
  );
}

function PartnerDialog({ partner, users, onClose, onSaved }) {
  const api = useAdminApi();
  const [contacts, setContacts] = useState(partner?.contacts ?? []);
  return (
    <RecordDialog
      title={partner?.id ? `Edit ${partner.name}` : "New partner"}
      fields={partnerFields(users)}
      record={partner ?? { partnership_type: "sponsorship", status: "prospect" }}
      onClose={onClose}
      onSave={async (body) => {
        const payload = { ...body, contacts: contacts.filter((c) => c.name.trim()) };
        if (partner?.id) await api.partners.update(partner.id, payload);
        else await api.partners.create(payload);
        onSaved();
      }}
    >
      {() => <ContactsEditor contacts={contacts} onChange={setContacts} />}
    </RecordDialog>
  );
}

export function PartnersPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useAdminQuery(
    () => api.partners.list({ q, page_size: 100 }),
    [q],
  );
  const options = useAdminQuery(() => api.partnershipOptions(), []);
  const [editing, setEditing] = useState(null);
  const open = async (row) => setEditing((await api.partners.get(row.id)).data);
  return (
    <>
      <AdminPageHeader
        title="Partners"
        description="Organisations you work with or are talking to. Contacts and notes are confidential and visible only to partnership roles."
        breadcrumbs={[{ label: "Partners" }]}
        actions={
          can("partnerships.manage") && (
            <Button onClick={() => setEditing({})}>
              <Plus aria-hidden className="size-4" /> New partner
            </Button>
          )
        }
      />
      <input
        type="search"
        aria-label="Search partners"
        placeholder="Search by name or industry"
        className="mb-4 w-full max-w-sm rounded-full border px-4 py-2 text-sm"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {error ? (
        <ErrorState title="We couldn't load partners" onRetry={reload} />
      ) : (
        <DataTable
          caption="Partners"
          rows={data}
          loading={loading}
          empty={{ icon: Handshake, title: "No partners yet" }}
          columns={[
            {
              key: "name",
              header: "Organisation",
              render: (p) => (
                <button
                  type="button"
                  className="font-medium hover:underline"
                  onClick={() => open(p)}
                >
                  {p.name}
                </button>
              ),
            },
            { key: "type", header: "Type", render: (p) => label(p.partnership_type) },
            { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
            { key: "owner", header: "Owner", render: (p) => p.owner?.name ?? "—" },
            { key: "updated", header: "Updated", render: (p) => p.updated_at?.slice(0, 10) },
          ]}
        />
      )}
      {editing && (
        <PartnerDialog
          partner={editing.id ? editing : null}
          users={options.data?.users}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            notify("Partner saved.");
            reload();
          }}
        />
      )}
    </>
  );
}

export function PartnershipInquiriesPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const [status, setStatus] = useState("new");
  const { data, error, loading, reload } = useAdminQuery(
    () => api.partnershipInquiries.list({ status, page_size: 100 }),
    [status],
  );
  const [selected, setSelected] = useState(null);
  const act = async (id, body, message) => {
    try {
      await api.partnershipInquiries.update(id, body);
      notify(message);
      setSelected(null);
      reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  return (
    <>
      <AdminPageHeader
        title="Partnership inquiries"
        description="Submitted through the Partner With Us form. Nobody is contacted automatically; reply from your own mailbox."
        breadcrumbs={[{ label: "Partnership inquiries" }]}
      />
      <select
        aria-label="Filter by status"
        className="mb-4 rounded-full border px-4 py-2 text-sm"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
      >
        {[
          ...INQUIRY_STATUSES,
          { value: "converted", label: "converted" },
          { value: "", label: "all" },
        ].map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {error ? (
        <ErrorState title="We couldn't load inquiries" onRetry={reload} />
      ) : (
        <DataTable
          caption="Inquiries"
          rows={data}
          loading={loading}
          empty={{ icon: Inbox, title: "No inquiries here" }}
          columns={[
            {
              key: "org",
              header: "Organisation",
              render: (i) => (
                <button
                  type="button"
                  className="font-medium hover:underline"
                  onClick={() => setSelected(i)}
                >
                  {i.organization}
                </button>
              ),
            },
            { key: "type", header: "Type", render: (i) => label(i.collaboration_type) },
            { key: "budget", header: "Budget", render: (i) => label(i.budget_range) || "—" },
            { key: "status", header: "Status", render: (i) => <StatusBadge status={i.status} /> },
            { key: "received", header: "Received", render: (i) => i.created_at?.slice(0, 10) },
          ]}
        />
      )}
      {selected && (
        <div
          role="dialog"
          aria-label="Inquiry"
          className="mt-6 rounded-2xl border border-charcoal/10 bg-white p-6"
        >
          <h2 className="text-lg font-medium">{selected.organization}</h2>
          <p className="text-sm text-muted">
            {selected.contact_name} · {selected.email}
            {selected.website && ` · ${selected.website}`}
          </p>
          {selected.objectives && (
            <p className="mt-3">
              <strong>Objectives:</strong> {selected.objectives}
            </p>
          )}
          <p className="mt-3 whitespace-pre-line">{selected.message}</p>
          <p className="mt-3 text-xs text-muted">
            Team notification: {label(selected.notification_status)} · privacy notice{" "}
            {selected.privacy_notice_version}
          </p>
          {can("partnerships.manage") && selected.status !== "converted" && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                size="sm"
                onClick={() =>
                  act(selected.id, { action: "convert" }, "Converted to a partner and opportunity.")
                }
              >
                Convert to opportunity
              </Button>
              {["reviewed", "declined", "spam"].map((s) => (
                <Button
                  key={s}
                  size="sm"
                  variant="outline"
                  onClick={() => act(selected.id, { status: s }, `Marked ${s}.`)}
                >
                  Mark {s}
                </Button>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}

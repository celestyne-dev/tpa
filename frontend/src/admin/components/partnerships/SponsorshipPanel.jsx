import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../../adminApiContext";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { SelectField, TextAreaField, TextField } from "../Fields";
import { fieldError } from "../fieldError";
import { useNotify } from "../notifyContext";
import { label } from "./formValues";

const REVIEW = ["draft", "internal_review", "sponsor_review"];

function SponsorshipForm({ articleId, record, options, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const manage = can("sponsorships.manage");
  const [form, setForm] = useState({
    sponsor_name: record?.sponsor_name ?? "",
    label: record?.label ?? "Sponsored Content",
    disclosure_text: record?.disclosure_text ?? "",
    partner_id: record?.partner_id ?? "",
    campaign_id: record?.campaign_id ?? "",
    starts_on: record?.starts_on ?? "",
    ends_on: record?.ends_on ?? "",
    sponsored_links: (record?.sponsored_links ?? []).join("\n"),
    sponsor_approval_notes: record?.sponsor_approval_notes ?? "",
    review_status: record?.review_status === "approved" ? "" : (record?.review_status ?? "draft"),
  });
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const run = async (fn, message) => {
    setError(null);
    try {
      await fn();
      notify(message);
      onChanged();
    } catch (err) {
      setError(err);
    }
  };
  const save = () =>
    run(
      () =>
        api.articleSponsorship.save(articleId, {
          sponsor_name: form.sponsor_name,
          label: form.label,
          disclosure_text: form.disclosure_text,
          partner_id: Number(form.partner_id) || null,
          campaign_id: Number(form.campaign_id) || null,
          starts_on: form.starts_on || null,
          ends_on: form.ends_on || null,
          sponsored_links: form.sponsored_links
            .split("\n")
            .map((x) => x.trim())
            .filter(Boolean),
          sponsor_approval_notes: form.sponsor_approval_notes,
          ...(form.review_status ? { review_status: form.review_status } : {}),
        }),
      "Sponsorship saved.",
    );
  const err = (k) => fieldError(error, k);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {record && (
        <p className="text-sm sm:col-span-2">
          Review status: <strong>{label(record.review_status)}</strong>
          {record.approved_at && ` (approved ${record.approved_at.slice(0, 10)})`}. Sponsor review
          is recorded here only; sponsors never get access to the admin.
        </p>
      )}
      <TextField
        label="Sponsor name"
        required
        value={form.sponsor_name}
        error={err("sponsor_name")}
        onChange={set("sponsor_name")}
        disabled={!manage}
      />
      <TextField
        label="Label shown near the title"
        value={form.label}
        error={err("label")}
        hint="Must clearly say the content is sponsored or paid."
        onChange={set("label")}
        disabled={!manage}
      />
      <TextAreaField
        className="sm:col-span-2"
        label="Disclosure shown to readers"
        required
        value={form.disclosure_text}
        error={err("disclosure_text")}
        disabled={!manage}
        hint="For example: “This article was produced in paid partnership with Calm Co.”"
        onChange={set("disclosure_text")}
      />
      <SelectField
        label="Partner"
        value={String(form.partner_id)}
        onChange={set("partner_id")}
        disabled={!manage}
        options={[
          { value: "", label: "—" },
          ...(options?.partners ?? []).map((p) => ({ value: String(p.id), label: p.name })),
        ]}
      />
      <SelectField
        label="Campaign"
        value={String(form.campaign_id)}
        onChange={set("campaign_id")}
        disabled={!manage}
        error={err("campaign_id")}
        options={[
          { value: "", label: "—" },
          ...(options?.campaigns ?? []).map((c) => ({ value: String(c.id), label: c.name })),
        ]}
      />
      <TextField
        type="date"
        label="Sponsorship starts"
        value={form.starts_on}
        onChange={set("starts_on")}
        disabled={!manage}
      />
      <TextField
        type="date"
        label="Sponsorship ends"
        value={form.ends_on}
        error={err("ends_on")}
        onChange={set("ends_on")}
        disabled={!manage}
      />
      <TextAreaField
        className="sm:col-span-2"
        label="Paid outbound links (one https:// address per line)"
        hint='These links get rel="sponsored"; other links in the article stay organic.'
        value={form.sponsored_links}
        error={err("sponsored_links")}
        onChange={set("sponsored_links")}
        disabled={!manage}
      />
      <TextAreaField
        className="sm:col-span-2"
        label="Approval notes (internal)"
        value={form.sponsor_approval_notes}
        onChange={set("sponsor_approval_notes")}
        disabled={!manage}
      />
      <SelectField
        label="Move review to"
        value={form.review_status}
        onChange={set("review_status")}
        disabled={!manage}
        hint="Approval is a separate step for the Editor-in-Chief."
        options={[
          { value: "", label: "Keep current status" },
          ...REVIEW.map((r) => ({ value: r, label: label(r) })),
        ]}
      />
      {error && !Object.keys(error.details ?? {}).length && (
        <p role="alert" className="text-sm text-red-800 sm:col-span-2">
          {error.message}
        </p>
      )}
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        {manage && <Button onClick={save}>Save sponsorship</Button>}
        {record?.can_approve && record.review_status !== "approved" && (
          <Button
            variant="outline"
            onClick={() =>
              run(() => api.articleSponsorship.approve(articleId), "Sponsorship approved.")
            }
          >
            Approve sponsorship
          </Button>
        )}
        {manage && record && (
          <Button
            variant="outline"
            onClick={() => {
              if (window.confirm("Remove the sponsorship from this unpublished article?"))
                run(() => api.articleSponsorship.remove(articleId), "Sponsorship removed.");
            }}
          >
            Remove
          </Button>
        )}
      </div>
      {record?.history?.length > 0 && (
        <ul className="text-xs text-muted sm:col-span-2">
          {record.history.map((h, i) => (
            <li key={i}>
              {h.at?.slice(0, 16).replace("T", " ")} · {label(h.kind)}{" "}
              {h.to ? `→ ${label(h.to)}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Sponsorship details for an article (sponsor, disclosure, paid links, review). Publishing
 * is refused until the disclosure is set and the sponsorship is approved.
 */
export function SponsorshipPanel({ articleId }) {
  const api = useAdminApi();
  const { data, loading, reload } = useAdminQuery(
    () => api.articleSponsorship.get(articleId),
    [articleId],
  );
  const options = useAdminQuery(() => api.partnershipOptions(), []);
  const [adding, setAdding] = useState(false);
  if (loading && data === null) return <p role="status">Loading…</p>;
  if (!data && !adding)
    return (
      <div>
        <p className="text-sm text-muted">
          This is organic editorial content. Mark it as sponsored if it is paid for.
        </p>
        <Button className="mt-3" onClick={() => setAdding(true)}>
          Mark as sponsored content
        </Button>
      </div>
    );
  return (
    <SponsorshipForm
      key={JSON.stringify(data)}
      articleId={articleId}
      record={data}
      options={options.data}
      onChanged={() => {
        setAdding(false);
        reload();
      }}
    />
  );
}

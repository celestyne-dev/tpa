import { History, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { ConfirmDialog } from "../ConfirmDialog";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../Fields";
import { ImageChooser } from "../media/ImageChooser";
import { Modal } from "../Modal";
import { errorText } from "./draft";

const counter = (value, ideal) =>
  `${(value ?? "").length} characters${ideal ? ` (about ${ideal} display best)` : ""}.`;

export function PageSettingsPanel({ detail, meta, onChange, errors, disabled }) {
  const api = useAdminApi();
  const [check, setCheck] = useState(null);
  const [parents, setParents] = useState([]);
  const isHome = detail.is_home;

  useEffect(() => {
    if (isHome) return undefined;
    let cancelled = false;
    api.pages
      .list()
      .then(
        (res) => !cancelled && setParents(res.data.filter((p) => p.id !== detail.id && !p.is_home)),
      )
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [api, detail.id, isHome]);

  const unchanged = meta.slug === detail.slug && meta.parent_id === detail.parent_id;
  useEffect(() => {
    if (isHome || !meta.slug || unchanged) return undefined;
    const timer = setTimeout(() => {
      api.pages
        .slugCheck({ slug: meta.slug, parent_id: meta.parent_id ?? undefined, exclude: detail.id })
        .then((res) => setCheck(res.data))
        .catch(() => setCheck(null));
    }, 400);
    return () => clearTimeout(timer);
  }, [api, meta.slug, meta.parent_id, detail.id, unchanged, isHome]);
  const shownCheck = unchanged ? null : check;

  return (
    <div className="space-y-4">
      <TextField
        label="Page title"
        required
        value={meta.title ?? ""}
        maxLength={200}
        disabled={disabled}
        error={errorText(errors["page.title"])}
        onChange={(e) => onChange({ ...meta, title: e.target.value })}
        hint="Shown in the browser tab and used when no SEO title is set."
      />
      {isHome ? (
        <p className="rounded-lg bg-cream px-4 py-3 text-sm text-ink">
          The homepage always lives at <strong>/</strong>.
        </p>
      ) : (
        <>
          <TextField
            label="Address (slug)"
            value={meta.slug ?? ""}
            maxLength={120}
            disabled={disabled || !detail.capabilities.change_slug}
            error={errorText(errors["page.slug"]) ?? shownCheck?.errors?.slug?.join(" ")}
            onChange={(e) => onChange({ ...meta, slug: e.target.value.toLowerCase() })}
            hint={
              shownCheck?.available
                ? `Available: ${shownCheck.path}${shownCheck.overrides_builtin ? " (replaces the built-in page)" : ""}`
                : "Lowercase letters, numbers and hyphens. Changing it on a live page creates a redirect."
            }
          />
          <SelectField
            label="Parent page"
            value={meta.parent_id ?? ""}
            disabled={disabled || !detail.capabilities.change_slug}
            error={errorText(errors["page.parent_id"]) ?? shownCheck?.errors?.parent_id?.join(" ")}
            options={[
              { value: "", label: "None (top level)" },
              ...parents.map((p) => ({ value: p.id, label: `${p.title} (${p.path})` })),
            ]}
            onChange={(e) =>
              onChange({ ...meta, parent_id: e.target.value ? Number(e.target.value) : null })
            }
          />
        </>
      )}
      <p className="text-sm text-muted">
        Template: <strong>{detail.template_label}</strong>. Templates only provide starter sections;
        everything stays editable.
      </p>
    </div>
  );
}

export function PageSeoPanel({ detail, meta, onChange, errors, disabled, refreshKey }) {
  const api = useAdminApi();
  const [checks, setChecks] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api.pages
      .seoChecks(detail.id)
      .then((res) => !cancelled && setChecks(res.data.checks))
      .catch(() => !cancelled && setChecks(null));
    return () => {
      cancelled = true;
    };
  }, [api, detail.id, refreshKey]);
  const set = (key) => (e) => onChange({ ...meta, [key]: e.target.value });
  return (
    <div className="space-y-4">
      <TextField
        label="SEO title"
        value={meta.seo_title ?? ""}
        maxLength={200}
        disabled={disabled}
        error={errorText(errors["page.seo_title"])}
        hint={`${counter(meta.seo_title, 60)} Leave empty to use the page title.`}
        onChange={set("seo_title")}
      />
      <TextAreaField
        label="Meta description"
        value={meta.meta_description ?? ""}
        maxLength={320}
        disabled={disabled}
        error={errorText(errors["page.meta_description"])}
        hint={counter(meta.meta_description, "70–160")}
        onChange={set("meta_description")}
      />
      <TextField
        label="Canonical URL (optional)"
        value={meta.canonical_url ?? ""}
        disabled={disabled}
        error={errorText(errors["page.canonical_url"])}
        hint="Only for pages that duplicate content published elsewhere. Leave empty normally."
        onChange={set("canonical_url")}
      />
      <CheckboxField
        label="Hide this page from search engines (noindex)"
        hint="It also leaves the sitemap."
        checked={Boolean(meta.noindex)}
        disabled={disabled}
        onChange={(e) => onChange({ ...meta, noindex: e.target.checked })}
      />
      <fieldset className="space-y-3 rounded-lg border border-charcoal/10 p-3">
        <legend className="px-1 text-sm font-semibold">Social sharing</legend>
        <TextField
          label="Social title"
          value={meta.social_title ?? ""}
          maxLength={200}
          disabled={disabled}
          onChange={set("social_title")}
        />
        <TextAreaField
          label="Social description"
          value={meta.social_description ?? ""}
          maxLength={320}
          disabled={disabled}
          onChange={set("social_description")}
        />
        <div className="space-y-1.5">
          <p className="text-sm font-medium text-charcoal">Social image</p>
          <ImageChooser
            mediaId={meta.social_image_id}
            label="social image"
            disabled={disabled}
            onChange={(id) => onChange({ ...meta, social_image_id: id ?? null })}
          />
          {errorText(errors["page.social_image_id"]) && (
            <p role="alert" className="text-sm text-red-800">
              {errorText(errors["page.social_image_id"])}
            </p>
          )}
        </div>
      </fieldset>
      {checks && (
        <section aria-label="SEO checks" className="rounded-lg bg-cream p-3">
          <h3 className="font-sans text-sm font-semibold">Checks for the saved draft</h3>
          {checks.length === 0 ? (
            <p className="mt-1 text-sm text-sage-800">No issues found.</p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm">
              {checks.map((c) => (
                <li
                  key={`${c.code}-${c.message}`}
                  className={c.severity === "warning" ? "text-gold-700" : "text-muted"}
                >
                  {c.severity === "warning" ? "⚠ " : "• "}
                  {c.message}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-muted">
            Guidance only: no tool can promise search rankings.
          </p>
        </section>
      )}
    </div>
  );
}

export function PageHistoryPanel({ detail, onRestored, refreshKey }) {
  const api = useAdminApi();
  const [items, setItems] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api.pages
      .revisions(detail.id)
      .then((res) => !cancelled && setItems(res.data))
      .catch(() => !cancelled && setItems([]));
    return () => {
      cancelled = true;
    };
  }, [api, detail.id, refreshKey]);

  const restore = async () => {
    setBusy(true);
    try {
      const res = await api.pages.restoreRevision(detail.id, confirm.id, detail.lock_version);
      onRestored(res.data, confirm);
      setConfirm(null);
    } catch (err) {
      onRestored(null, confirm, err);
      setConfirm(null);
    } finally {
      setBusy(false);
    }
  };

  if (!items) return <p className="text-sm text-muted">Loading history…</p>;
  if (items.length === 0)
    return (
      <p className="rounded-lg bg-cream p-4 text-sm text-muted">
        Nothing published yet. Every publish is kept here so you can go back to it.
      </p>
    );
  return (
    <>
      <ol aria-label="Revisions" className="space-y-2">
        {items.map((r) => (
          <li
            key={r.id}
            className="flex flex-wrap items-center gap-3 rounded-lg border border-charcoal/10 bg-white p-3"
          >
            <History aria-hidden className="size-4 text-muted" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                #{r.number} · {r.kind_label}
              </p>
              <p className="text-xs text-muted">
                {formatDateTime(r.created_at)}
                {r.created_by ? ` · ${r.created_by.name}` : ""} · {r.section_count} sections
                {r.summary ? ` · ${r.summary}` : ""}
              </p>
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                api.pages.revision(detail.id, r.id).then((res) => setViewing(res.data))
              }
            >
              View
            </Button>
            {detail.capabilities.restore_revisions && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirm(r)}
                aria-label={`Restore revision ${r.number}`}
              >
                <RotateCcw aria-hidden />
                Restore
              </Button>
            )}
          </li>
        ))}
      </ol>
      <Modal
        open={Boolean(viewing)}
        title={viewing ? `Revision #${viewing.number}` : ""}
        onClose={() => setViewing(null)}
      >
        {viewing && (
          <ol className="space-y-1.5 text-sm">
            {viewing.sections.map((s, i) => (
              <li key={`${s.key}-${i}`} className="rounded bg-cream px-3 py-2">
                <span className="font-medium">{s.name || s.type_label}</span>
                {s.heading ? ` — “${s.heading}”` : ""}
                {!s.is_visible && <span className="text-muted"> (hidden)</span>}
              </li>
            ))}
          </ol>
        )}
      </Modal>
      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm ? `Restore revision #${confirm.number}?` : ""}
        message="The draft is replaced with this version (your current draft is kept in history). The website only changes when you publish."
        confirmLabel="Restore into draft"
        busy={busy}
        onConfirm={restore}
        onCancel={() => setConfirm(null)}
      />
    </>
  );
}

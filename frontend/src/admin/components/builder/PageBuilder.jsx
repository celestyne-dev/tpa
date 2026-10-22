import {
  CalendarClock,
  ChevronDown,
  Eye,
  Link2,
  MonitorPlay,
  Rocket,
  Save,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import { AdminPageHeader } from "../AdminPageHeader";
import { ConfirmDialog } from "../ConfirmDialog";
import { TextField } from "../Fields";
import { Modal } from "../Modal";
import { useNotify } from "../notifyContext";
import { StatusBadge } from "../StatusBadge";
import { AddSectionDialog } from "./AddSectionDialog";
import { BuilderLookups } from "./BuilderLookups";
import {
  errorText,
  fromLocalInput,
  linkedSection,
  newSection,
  sameDraft,
  sectionErrors,
  toDraft,
  toLocalInput,
  toPayload,
} from "./draft";
import { useBuilderLookups } from "./lookups";
import { PageHistoryPanel, PageSeoPanel, PageSettingsPanel } from "./PagePanels";
import { PreviewPane } from "./PreviewPane";
import { SectionFields } from "./SectionFields";
import { SectionOutline } from "./SectionOutline";
import { DesignControls, VisibilityControls } from "./StyleControls";

const TABS = [
  ["sections", "Sections"],
  ["settings", "Page settings"],
  ["seo", "SEO"],
  ["history", "History"],
];

function StatusBanner({ detail, dirty }) {
  let tone = "bg-cream text-ink";
  let text;
  if (detail.status === "archived") {
    text = "Archived: not on the website. Restore it to edit or publish again.";
  } else if (detail.status !== "published") {
    text = "Draft: not visible on the website until you publish.";
  } else if (dirty) {
    tone = "bg-gold-100 text-charcoal";
    text = "Live, with unsaved changes. Save the draft to keep them; publish to put them live.";
  } else if (detail.has_unpublished_changes) {
    tone = "bg-gold-100 text-charcoal";
    text = "Live, with a saved draft that is not published yet.";
  } else {
    tone = "bg-sage-50 text-sage-800";
    text = "Live: the website shows this version (after the latest rebuild).";
  }
  return (
    <div role="status" className={cn("rounded-lg px-4 py-3 text-sm", tone)}>
      <p className="flex flex-wrap items-center gap-2">
        <StatusBadge status={detail.status} />
        {text}
        {detail.live_path && detail.status === "published" && (
          <a
            href={detail.live_path}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-4"
          >
            View live page<span className="sr-only"> (opens in a new tab)</span>
          </a>
        )}
      </p>
      {detail.scheduled_at && (
        <p className="mt-1 flex items-center gap-1.5">
          <CalendarClock aria-hidden className="size-4" />
          Scheduled to publish {formatDateTime(detail.scheduled_at)} (the version saved when it was
          scheduled).
        </p>
      )}
      {detail.warnings?.map((w) => (
        <p key={w} className="mt-1 flex items-start gap-1.5">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-gold-700" />
          {w}
        </p>
      ))}
    </div>
  );
}

function MoreActions({ actions }) {
  const [open, setOpen] = useState(false);
  const visible = actions.filter((a) => a.show);
  if (visible.length === 0) return null;
  return (
    <div
      className="relative"
      onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}
    >
      <Button variant="outline" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        More actions
        <ChevronDown aria-hidden />
      </Button>
      {open && (
        <ul className="absolute right-0 z-30 mt-2 w-60 rounded-xl border border-charcoal/10 bg-white p-1 shadow-lift">
          {visible.map((a) => (
            <li key={a.label}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  a.onClick();
                }}
                className={cn(
                  "w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-cream",
                  a.danger && "text-red-800",
                )}
              >
                {a.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SectionEditor({ type, section, onChange, errors, disabled }) {
  const { shared } = useBuilderLookups();
  if (!type) return <p className="text-muted">This section type is no longer available.</p>;
  if (section.reusable_section_id) {
    const source = shared.find((s) => s.id === section.reusable_section_id);
    return (
      <div className="space-y-4">
        <div className="rounded-lg bg-sage-50 p-4 text-sm text-sage-800">
          <p className="flex items-center gap-2 font-medium">
            <Link2 aria-hidden className="size-4" />
            Shared section: {section.reusable_name ?? source?.name}
          </p>
          <p className="mt-1">
            Its content is edited once in Website › Shared sections and updates every page that uses
            it. Detach it (toolbar) to edit a separate copy on this page only.
          </p>
        </div>
        <TextField
          label="Internal name"
          value={section.name ?? ""}
          maxLength={120}
          disabled={disabled}
          onChange={(e) => onChange({ ...section, name: e.target.value })}
        />
        <details className="rounded-lg border border-charcoal/10 p-3">
          <summary className="cursor-pointer text-sm font-semibold">Visibility</summary>
          <div className="mt-3">
            <VisibilityControls
              visibility={section.visibility}
              errors={errors}
              disabled={disabled}
              onChange={(visibility) => onChange({ ...section, visibility })}
            />
          </div>
        </details>
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <TextField
          className="min-w-0 flex-1"
          label="Internal name"
          hint="Only editors see this name."
          value={section.name ?? ""}
          maxLength={120}
          disabled={disabled}
          onChange={(e) => onChange({ ...section, name: e.target.value })}
        />
        <p className="pb-2 text-sm text-muted">{type.label}</p>
      </div>
      <SectionFields
        type={type}
        section={section}
        onChange={onChange}
        errors={errors}
        disabled={disabled}
      />
      {type.design.length > 0 && (
        <details className="rounded-lg border border-charcoal/10 p-3" open>
          <summary className="cursor-pointer text-sm font-semibold">Appearance</summary>
          <div className="mt-3">
            <DesignControls
              type={type}
              design={section.design ?? {}}
              errors={errors}
              disabled={disabled}
              onChange={(design) => onChange({ ...section, design })}
            />
          </div>
        </details>
      )}
      <details className="rounded-lg border border-charcoal/10 p-3">
        <summary className="cursor-pointer text-sm font-semibold">Visibility</summary>
        <div className="mt-3">
          <VisibilityControls
            visibility={section.visibility}
            errors={errors}
            disabled={disabled}
            onChange={(visibility) => onChange({ ...section, visibility })}
          />
        </div>
      </details>
    </div>
  );
}

function Builder({ load, isHome }) {
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const lookups = useBuilderLookups();
  const [detail, setDetail] = useState(null);
  const [types, setTypes] = useState([]);
  const [draft, setDraft] = useState(null);
  const [base, setBase] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [errors, setErrors] = useState({});
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("sections");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleAt, setScheduleAt] = useState("");
  const [shareTarget, setShareTarget] = useState(null);
  const [shareName, setShareName] = useState("");
  const [showPreview, setShowPreview] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  const typeMap = useMemo(() => Object.fromEntries(types.map((t) => [t.type, t])), [types]);
  const withLabels = useCallback(
    (d) => ({
      ...d,
      sections: d.sections.map((s) => ({
        ...s,
        type_label: s.type_label ?? typeMap[s.section_type]?.label,
      })),
    }),
    [typeMap],
  );

  const apply = useCallback((data) => {
    const next = toDraft(data);
    setDetail(data);
    setDraft(next);
    setBase(next);
    setErrors({});
    setSelected((current) =>
      next.sections.some((s) => s.cid === current) ? current : (next.sections[0]?.cid ?? null),
    );
    setRefreshKey((k) => k + 1);
  }, []);

  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    let cancelled = false;
    Promise.all([load(), api.pages.sectionTypes()])
      .then(([page, sectionTypes]) => {
        if (cancelled) return;
        setLoadError(null);
        setTypes(sectionTypes.data);
        apply(page.data);
      })
      .catch((err) => !cancelled && setLoadError(err));
    return () => {
      cancelled = true;
    };
  }, [api, load, apply, version]);

  const dirty = Boolean(draft && base && !sameDraft(draft, base));
  useUnsavedChanges(dirty);

  if (loadError) return <ErrorState title="We couldn't load this page" onRetry={reload} />;
  if (!detail || !draft) return <Skeleton className="h-96 w-full" />;

  const can = detail.capabilities;
  const disabled = !can.edit || busy;
  const sections = withLabels(draft).sections;
  const index = sections.findIndex((s) => s.cid === selected);
  const current = sections[index];
  const errorCounts = Object.fromEntries(
    sections.map((_, i) => [i, Object.keys(sectionErrors(errors, i)).length]),
  );
  const pageErrors = Object.keys(errors).filter((k) => k.startsWith("page.") || k === "sections");

  const fail = (err, fallback) => {
    if (err.status === 409 && err.code === "edit_conflict") {
      setConflict(err.details ?? {});
    } else if (err.status === 400 && err.details) {
      setErrors(err.details);
      const firstSection = Object.keys(err.details)
        .map((k) => /^sections\.(\d+)\./.exec(k)?.[1])
        .find((v) => v !== undefined);
      if (firstSection !== undefined) {
        setSelected(sections[Number(firstSection)]?.cid ?? selected);
        setTab("sections");
      } else if (Object.keys(err.details).some((k) => /^page\.(slug|parent_id|title)/.test(k))) {
        setTab("settings");
      } else if (Object.keys(err.details).some((k) => k.startsWith("page."))) {
        setTab("seo");
      }
      notify(err.message || fallback, "error");
    } else {
      notify(err.message || fallback, "error");
    }
  };

  const saveDraft = async ({ quiet = false } = {}) => {
    setBusy(true);
    try {
      const res = await api.pages.saveDraft(detail.id, {
        lock_version: detail.lock_version,
        ...toPayload(draft),
      });
      apply(res.data);
      if (!quiet) notify("Draft saved. The website has not changed.");
      return res.data;
    } catch (err) {
      fail(err, "The draft could not be saved.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    setConfirm(null);
    let latest = detail;
    if (dirty) {
      latest = await saveDraft({ quiet: true });
      if (!latest) return;
    }
    setBusy(true);
    try {
      const res = await api.pages.publish(detail.id, latest.lock_version);
      apply(res.data);
      notify(
        "Published. The website updates when the queued rebuild finishes (see Publishing jobs).",
      );
    } catch (err) {
      fail(err, "The page could not be published.");
    } finally {
      setBusy(false);
    }
  };

  const openPreview = async () => {
    if (dirty && !(await saveDraft({ quiet: true }))) return;
    window.open(`/admin/pages/${detail.id}/preview`, "_blank", "noopener");
  };

  const runAction = async (fn, message) => {
    setConfirm(null);
    setBusy(true);
    try {
      const res = await fn();
      if (res?.data?.id && res.data.id !== detail.id) {
        notify(message);
        navigate(`/admin/pages/${res.data.id}`);
        return;
      }
      if (res?.data) apply(res.data);
      notify(message);
    } catch (err) {
      fail(err, "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  const schedule = async () => {
    setScheduleOpen(false);
    let latest = detail;
    if (dirty) {
      latest = await saveDraft({ quiet: true });
      if (!latest) return;
    }
    await runAction(
      () => api.pages.schedule(detail.id, fromLocalInput(scheduleAt), latest.lock_version),
      "Scheduled. The saved version will be published automatically.",
    );
  };

  const setSections = (next) => setDraft((d) => ({ ...d, sections: next }));
  const updateSection = (updated) =>
    setSections(draft.sections.map((s) => (s.cid === updated.cid ? updated : s)));

  const detach = (i) => {
    const s = sections[i];
    const copy = {
      ...s,
      reusable_section_id: null,
      reusable_name: null,
      name: `${s.name || s.type_label} (copy)`,
    };
    setSections(draft.sections.map((x, idx) => (idx === i ? copy : x)));
    notify("Detached: this page now has its own copy. Save the draft to keep it.");
  };

  const share = async () => {
    setBusy(true);
    try {
      await api.pages.shareSection(detail.id, shareTarget.id, shareName);
      setShareTarget(null);
      notify("Saved as a shared section. It is now linked on this page.");
      lookups.reload();
      const res = await load();
      apply(res.data);
    } catch (err) {
      fail(err, "The section could not be shared.");
    } finally {
      setBusy(false);
    }
  };

  const title = isHome ? "Homepage" : detail.title;
  return (
    <>
      <AdminPageHeader
        title={title}
        description={
          isHome
            ? "Edit, reorder and preview the homepage sections. Changes stay private until you publish."
            : `${detail.path ?? ""} · ${detail.template_label}`
        }
        breadcrumbs={
          isHome
            ? [{ label: "Homepage" }]
            : [{ label: "Pages", to: "/admin/pages" }, { label: detail.title }]
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {dirty && <span className="text-sm text-gold-700">Unsaved changes</span>}
            {can.edit && (
              <Button variant="outline" onClick={() => saveDraft()} disabled={busy || !dirty}>
                <Save aria-hidden />
                Save draft
              </Button>
            )}
            <Button variant="outline" onClick={openPreview} disabled={busy}>
              <Eye aria-hidden />
              Preview
            </Button>
            {can.publish && (
              <Button onClick={() => setConfirm("publish")} disabled={busy}>
                <Rocket aria-hidden />
                Publish
              </Button>
            )}
            <MoreActions
              actions={[
                {
                  label: "Discard unpublished changes",
                  show:
                    can.edit &&
                    detail.status === "published" &&
                    (detail.has_unpublished_changes || dirty),
                  onClick: () => setConfirm("discard"),
                },
                {
                  label: "Schedule publication…",
                  show: can.publish,
                  onClick: () => setScheduleOpen(true),
                },
                {
                  label: "Cancel scheduled publication",
                  show: can.publish && Boolean(detail.scheduled_at),
                  onClick: () =>
                    runAction(() => api.pages.unschedule(detail.id), "Schedule cancelled."),
                },
                {
                  label: "Duplicate page",
                  show: can.duplicate,
                  onClick: () =>
                    runAction(() => api.pages.duplicate(detail.id), "Copy created as a draft."),
                },
                {
                  label: "Unpublish",
                  show: can.unpublish,
                  danger: true,
                  onClick: () => setConfirm("unpublish"),
                },
                {
                  label: "Archive",
                  show: can.archive,
                  danger: true,
                  onClick: () => setConfirm("archive"),
                },
                {
                  label: "Restore from archive",
                  show: can.restore,
                  onClick: () =>
                    runAction(() => api.pages.restore(detail.id), "Restored as a draft."),
                },
              ]}
            />
          </div>
        }
      />
      <div className="space-y-4">
        <StatusBanner detail={detail} dirty={dirty} />
        {pageErrors.length > 0 && (
          <div role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-900">
            {pageErrors.map((k) => (
              <p key={k}>{errorText(errors[k])}</p>
            ))}
          </div>
        )}
        <div
          role="tablist"
          aria-label="Page editor"
          className="flex flex-wrap gap-1 border-b border-charcoal/10"
        >
          {TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              id={`tab-${key}`}
              aria-selected={tab === key}
              aria-controls={`panel-${key}`}
              onClick={() => setTab(key)}
              className={cn(
                "-mb-px border-b-2 px-4 py-2 text-sm font-medium",
                tab === key
                  ? "border-sage-700 text-sage-800"
                  : "border-transparent text-muted hover:text-charcoal",
              )}
            >
              {label}
              {key === "sections" && ` (${sections.length})`}
            </button>
          ))}
        </div>

        {tab === "sections" && (
          <div
            id="panel-sections"
            role="tabpanel"
            aria-labelledby="tab-sections"
            className="space-y-6"
          >
            <div className="grid gap-6 lg:grid-cols-[19rem_minmax(0,1fr)]">
              <SectionOutline
                sections={sections}
                selected={selected}
                onSelect={setSelected}
                onChange={setSections}
                onAdd={() => setAddOpen(true)}
                onDetach={detach}
                onShare={(s) => {
                  setShareTarget(s);
                  setShareName(s.name || s.type_label);
                }}
                errorCounts={errorCounts}
                disabled={disabled}
                canShare={can.manage_shared && can.edit}
              />
              <section
                aria-label="Section editor"
                className="min-w-0 rounded-xl border border-charcoal/10 bg-white p-5"
              >
                {current ? (
                  <SectionEditor
                    key={current.cid}
                    type={typeMap[current.section_type]}
                    section={current}
                    errors={sectionErrors(errors, index)}
                    disabled={disabled}
                    onChange={updateSection}
                  />
                ) : (
                  <p className="text-muted">Add a section to start building this page.</p>
                )}
              </section>
            </div>
            <div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowPreview((v) => !v)}
                aria-pressed={showPreview}
              >
                <MonitorPlay aria-hidden />
                {showPreview ? "Hide live preview" : "Show live preview"}
              </Button>
              {showPreview && (
                <div className="mt-3">
                  <PreviewPane pageId={detail.id} payload={toPayload(draft)} />
                </div>
              )}
            </div>
          </div>
        )}
        {tab === "settings" && (
          <div
            id="panel-settings"
            role="tabpanel"
            aria-labelledby="tab-settings"
            className="max-w-2xl"
          >
            <PageSettingsPanel
              detail={detail}
              meta={draft.meta}
              errors={errors}
              disabled={disabled}
              onChange={(meta) => setDraft((d) => ({ ...d, meta }))}
            />
          </div>
        )}
        {tab === "seo" && (
          <div id="panel-seo" role="tabpanel" aria-labelledby="tab-seo" className="max-w-2xl">
            <PageSeoPanel
              detail={detail}
              meta={draft.meta}
              errors={errors}
              disabled={disabled}
              refreshKey={refreshKey}
              onChange={(meta) => setDraft((d) => ({ ...d, meta }))}
            />
          </div>
        )}
        {tab === "history" && (
          <div
            id="panel-history"
            role="tabpanel"
            aria-labelledby="tab-history"
            className="max-w-3xl"
          >
            <PageHistoryPanel
              detail={detail}
              refreshKey={refreshKey}
              onRestored={(data, revision, err) => {
                if (err) return fail(err, "The revision could not be restored.");
                apply(data);
                setTab("sections");
                notify(
                  `Revision #${revision.number} restored into the draft. Publish to put it live.`,
                );
              }}
            />
          </div>
        )}
      </div>

      <AddSectionDialog
        open={addOpen}
        types={types}
        existing={sections}
        onClose={() => setAddOpen(false)}
        onAddType={(type) => {
          const section = newSection(type);
          const at = index >= 0 ? index + 1 : draft.sections.length;
          const next = [...draft.sections];
          next.splice(at, 0, section);
          setSections(next);
          setSelected(section.cid);
          setAddOpen(false);
        }}
        onAddShared={(shared) => {
          const section = linkedSection(shared);
          setSections([...draft.sections, section]);
          setSelected(section.cid);
          setAddOpen(false);
        }}
      />
      <ConfirmDialog
        open={confirm === "publish"}
        title={isHome ? "Publish the homepage?" : `Publish “${detail.title}”?`}
        message={`${dirty ? "Your changes are saved first. " : ""}The live website updates after the queued rebuild finishes (usually within a minute or two). Earlier versions stay in History.`}
        confirmLabel="Publish"
        busy={busy}
        onConfirm={publish}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "discard"}
        title="Discard unpublished changes?"
        message="The draft goes back to the live version. Unsaved and saved draft changes are lost."
        confirmLabel="Discard changes"
        tone="danger"
        busy={busy}
        onConfirm={() =>
          runAction(() => api.pages.discard(detail.id), "Draft reset to the live version.")
        }
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "unpublish"}
        title="Unpublish this page?"
        message="It disappears from the website after the next rebuild and returns a 404. Consider adding a redirect."
        confirmLabel="Unpublish"
        tone="danger"
        busy={busy}
        onConfirm={() =>
          runAction(() => api.pages.unpublish(detail.id), "Unpublished. A rebuild has been queued.")
        }
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "archive"}
        title="Archive this page?"
        message="Archived pages are hidden from the page list and from the website. You can restore them later."
        confirmLabel="Archive"
        tone="danger"
        busy={busy}
        onConfirm={() => runAction(() => api.pages.archive(detail.id), "Page archived.")}
        onCancel={() => setConfirm(null)}
      />
      <Modal
        open={scheduleOpen}
        title="Schedule publication"
        onClose={() => setScheduleOpen(false)}
        footer={
          <>
            <Button variant="outline" onClick={() => setScheduleOpen(false)}>
              Cancel
            </Button>
            <Button onClick={schedule} disabled={!scheduleAt}>
              Schedule
            </Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-muted">
          The current draft (saved now) is published automatically at this time. Later edits need
          their own publish.
        </p>
        <TextField
          type="datetime-local"
          label="Publish at (your local time)"
          value={scheduleAt || toLocalInput(detail.scheduled_at)}
          onChange={(e) => setScheduleAt(e.target.value)}
          error={errorText(errors.scheduled_at)}
        />
      </Modal>
      <Modal
        open={Boolean(shareTarget)}
        title="Save as a shared section"
        onClose={() => setShareTarget(null)}
        footer={
          <>
            <Button variant="outline" onClick={() => setShareTarget(null)}>
              Cancel
            </Button>
            <Button onClick={share} disabled={!shareName.trim() || busy}>
              Save shared section
            </Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-muted">
          The saved version of this section becomes reusable on other pages. Editing it later can
          update every page that uses it.
        </p>
        <TextField
          label="Shared section name"
          value={shareName}
          maxLength={120}
          onChange={(e) => setShareName(e.target.value)}
        />
      </Modal>
      <Modal
        open={Boolean(conflict)}
        title="Someone else changed this page"
        onClose={() => setConflict(null)}
        footer={
          <>
            <Button variant="outline" onClick={() => setConflict(null)}>
              Keep my edits for now
            </Button>
            <Button
              onClick={() => {
                setConflict(null);
                reload();
              }}
            >
              Load their version
            </Button>
          </>
        }
      >
        <p className="text-sm">
          {conflict?.updated_by ? `${conflict.updated_by} saved` : "A newer version was saved"}
          {conflict?.updated_at ? ` at ${formatDateTime(conflict.updated_at)}` : ""}. To avoid
          overwriting their work, nothing was saved. Copy anything you need, then load their
          version.
        </p>
      </Modal>
    </>
  );
}

/** Homepage and page builder (drafts, live preview, publishing, history). */
export function PageBuilder(props) {
  return (
    <BuilderLookups>
      <Builder {...props} />
    </BuilderLookups>
  );
}

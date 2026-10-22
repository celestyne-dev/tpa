import {
  Archive,
  BadgeCheck,
  CalendarClock,
  ClipboardCheck,
  ExternalLink,
  Eye,
  RotateCcw,
  Save,
  Send,
  Trash2,
  Undo2,
  UploadCloud,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { BlockEditor } from "../components/BlockEditor";
import { cleanBlocks, countWords, readingMinutes } from "../components/blocks";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { fieldError } from "../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../components/Fields";
import { ImageChooser, MediaThumb } from "../components/media/ImageChooser";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { RevisionsPanel } from "../components/RevisionsPanel";
import { SeoPanel } from "../components/SeoPanel";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { useAutosave } from "../hooks/useAutosave";
import { usePermissions } from "../hooks/usePermissions";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";

const EMPTY = {
  title: "",
  slug: "",
  subtitle: "",
  excerpt: "",
  body: [],
  author_id: "",
  primary_topic_id: "",
  secondary_topic_ids: [],
  tag_ids: [],
  featured: false,
  featured_image_id: "",
  social_image_id: "",
  seo_title: "",
  meta_description: "",
  social_title: "",
  social_description: "",
  canonical_url: "",
  noindex: false,
  original_url: "",
  original_slug: "",
};
const FIELDS = Object.keys(EMPTY);
const TABS = [
  ["content", "Content"],
  ["details", "Details"],
  ["seo", "SEO"],
  ["history", "History"],
];

function toForm(article) {
  const form = {};
  FIELDS.forEach((f) => {
    const v = article[f];
    form[f] = v === null || v === undefined ? EMPTY[f] : v;
  });
  return form;
}

function toPayload(form, { includeSlug, includeIndexing }) {
  const idOrNull = (v) => (v === "" || v === null ? null : Number(v));
  const payload = {
    ...form,
    body: cleanBlocks(form.body),
    author_id: idOrNull(form.author_id),
    primary_topic_id: idOrNull(form.primary_topic_id),
    featured_image_id: idOrNull(form.featured_image_id),
    social_image_id: idOrNull(form.social_image_id),
    secondary_topic_ids: form.secondary_topic_ids.map(Number),
    tag_ids: form.tag_ids.map(Number),
  };
  ["seo_title", "meta_description", "social_title", "social_description", "canonical_url"].forEach(
    (k) => {
      if (payload[k] === "") payload[k] = null;
    },
  );
  if (!includeSlug) delete payload.slug;
  if (!includeIndexing) {
    delete payload.canonical_url;
    delete payload.noindex;
  }
  return payload;
}

function MultiSelect({ legend, options, value, onChange }) {
  return (
    <fieldset>
      <legend className="text-sm font-medium text-charcoal">{legend}</legend>
      <div className="mt-2 flex max-h-40 flex-col gap-1.5 overflow-y-auto rounded-lg border border-charcoal/15 bg-white p-3">
        {options.length === 0 && <span className="text-sm text-muted">None available.</span>}
        {options.map((o) => (
          <label key={o.value} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="accent-sage-700"
              checked={value.includes(o.value)}
              onChange={(e) =>
                onChange(
                  e.target.checked ? [...value, o.value] : value.filter((v) => v !== o.value),
                )
              }
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

const AUTOSAVE_TEXT = {
  idle: "",
  pending: "Unsaved changes…",
  saving: "Saving…",
  saved: "All changes saved",
  error: "Autosave failed — retrying",
  offline: "Offline — will save when reconnected",
  conflict: "Autosave paused (edit conflict)",
};

export function ArticleEditorPage() {
  const { id } = useParams();
  const isNew = !id;
  const api = useAdminApi();
  const navigate = useNavigate();
  const notify = useNotify();
  const { can } = usePermissions();

  const article = useAdminQuery(
    () => (isNew ? Promise.resolve({ data: null }) : api.articles.get(id)),
    [id],
  );
  const refs = useAdminQuery(
    () =>
      Promise.all([api.topics.list(), api.authors.list(), api.tags.list()]).then(
        ([topics, authors, tags]) => ({
          data: { topics: topics.data, authors: authors.data, tags: tags.data },
        }),
      ),
    [],
  );
  const seoChecks = useAdminQuery(
    () => (isNew ? Promise.resolve({ data: null }) : api.articles.seoChecks(id)),
    [id],
  );

  const [form, setForm] = useState(EMPTY);
  const [saved, setSaved] = useState(EMPTY);
  const [lockVersion, setLockVersion] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [scheduleAt, setScheduleAt] = useState("");
  const [tab, setTab] = useState("content");
  const [historyKey, setHistoryKey] = useState(0);

  const record = article.data;
  // The server computes what this user may do with this article (ownership included).
  const allowed = record?.can ?? {};
  const canWrite = isNew ? can("articles.create") : Boolean(allowed.edit);
  const status = record?.status ?? "draft";
  const isLive = status === "published";

  // Load the form once per article. Later server responses are applied explicitly
  // (never by re-syncing), so an in-flight autosave cannot overwrite fresh typing.
  const [loadedFor, setLoadedFor] = useState(null);
  if (record && loadedFor !== record.id) {
    setLoadedFor(record.id);
    setForm(toForm(record));
    setSaved(toForm(record));
    setLockVersion(record.lock_version);
  }

  const dirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(saved), [form, saved]);
  useUnsavedChanges(dirty && canWrite);

  // Reset when switching from an existing article to "new" (render-phase adjustment).
  const routeKey = id ?? "new";
  const [lastRoute, setLastRoute] = useState(routeKey);
  if (routeKey !== lastRoute) {
    setLastRoute(routeKey);
    if (isNew) {
      setForm(EMPTY);
      setSaved(EMPTY);
      setLockVersion(null);
    }
  }

  const payloadOptions = {
    includeSlug: isNew || Boolean(allowed.edit_slug),
    includeIndexing: isNew ? false : Boolean(allowed.edit_indexing),
  };
  const words = countWords(form.body);

  const applyServer = (res, sentForm) => {
    const data = res.data;
    setLockVersion(data.lock_version);
    if (sentForm) setSaved(sentForm);
    article.setData((current) => ({ ...current, ...data, lock_version: data.lock_version }));
    seoChecks.reload();
    setHistoryKey((k) => k + 1);
  };

  const autosave = useAutosave({
    enabled: !isNew && canWrite && !busy,
    dirty,
    payload: form,
    lockVersion,
    save: (body, version) =>
      api.articles.update(id, {
        ...toPayload(body, payloadOptions),
        mode: "autosave",
        lock_version: version,
      }),
    onSaved: (res, sentForm) => {
      setError(null);
      applyServer(res, sentForm);
    },
  });

  const set = (field) => (e) =>
    setForm((f) => ({
      ...f,
      [field]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e,
    }));

  const save = async () => {
    setBusy(true);
    setError(null);
    const sent = form;
    try {
      const payload = toPayload(sent, payloadOptions);
      if (isNew) {
        const res = await api.articles.create(payload);
        setSaved(sent);
        notify("Draft created.");
        navigate(`/admin/articles/${res.data.id}/edit`, { replace: true });
      } else {
        const res = await api.articles.update(id, { ...payload, lock_version: lockVersion });
        applyServer(res, sent);
        notify(
          res.meta?.save_result === "pending"
            ? "Changes saved for review. The live article changes when a publisher publishes them."
            : "Changes saved.",
        );
      }
    } catch (err) {
      setError(err);
      if (err.code === "edit_conflict") setConfirm("conflict");
      notify(err.status === 400 ? "Please fix the highlighted fields." : err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (action, message) => {
    setBusy(true);
    setError(null);
    try {
      const res =
        action === "publish"
          ? await api.articles.publish(id, null)
          : action === "schedule"
            ? await api.articles.publish(id, new Date(scheduleAt).toISOString())
            : action === "publishChanges"
              ? await api.articles.publishChanges(id, lockVersion)
              : await api.articles[action](id);
      if (action === "remove") {
        notify(message);
        navigate("/admin/articles", { replace: true });
        return;
      }
      if (res.data?.lock_version) setLockVersion(res.data.lock_version);
      article.setData(res.data);
      if (["discardChanges", "publishChanges"].includes(action)) {
        setForm(toForm(res.data));
        setSaved(toForm(res.data));
      }
      seoChecks.reload();
      notify(message);
    } catch (err) {
      setError(err);
      notify(
        err.status === 400 ? "The article is not ready to publish yet." : err.message,
        "error",
      );
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const reloadLatest = async () => {
    const res = await api.articles.get(id);
    article.setData(res.data);
    setForm(toForm(res.data));
    setSaved(toForm(res.data));
    setLockVersion(res.data.lock_version);
    autosave.clearConflict();
    setConfirm(null);
    notify("Loaded the latest version.");
  };

  const keepMine = async () => {
    const res = await api.articles.get(id);
    setLockVersion(res.data.lock_version);
    autosave.clearConflict();
    setConfirm(null);
    notify("Your version will be saved over theirs on the next save.");
  };

  if (article.error)
    return (
      <ErrorState
        title="We couldn't load this article"
        message={article.error.message}
        onRetry={article.reload}
      />
    );
  if ((!isNew && !record) || !refs.data)
    return refs.error ? (
      <ErrorState title="We couldn't load the editor" onRetry={refs.reload} />
    ) : (
      <div role="status" aria-label="Loading editor" className="space-y-4">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-64 w-full" />
      </div>
    );

  const { topics, authors, tags } = refs.data;
  const option = (items, labelKey) => [
    { value: "", label: "— Select —" },
    ...items.map((i) => ({
      value: String(i.id),
      label: i[labelKey] + (i.status && i.status !== "active" ? ` (${i.status})` : ""),
    })),
  ];
  const err = (name) => fieldError(error, name);
  const saveLabel = isNew
    ? "Create draft"
    : isLive && !allowed.save_live
      ? "Save for review"
      : "Save changes";
  const conflictOpen = confirm === "conflict" || autosave.status === "conflict";

  return (
    <>
      <AdminPageHeader
        title={isNew ? "New article" : form.title || "Untitled article"}
        breadcrumbs={[
          { label: "Articles", to: "/admin/articles" },
          { label: isNew ? "New" : "Edit" },
        ]}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setPreview(true)}>
              <Eye aria-hidden />
              Preview
            </Button>
            {!isNew && allowed.preview && (
              <ButtonLink
                to={`/admin/articles/${id}/preview`}
                variant="ghost"
                size="sm"
                target="_blank"
                rel="noopener"
                data-allow-unsaved
              >
                <ExternalLink aria-hidden />
                Full preview
              </ButtonLink>
            )}
            {canWrite && (
              <Button
                size="sm"
                onClick={save}
                disabled={busy || (!dirty && !isNew) || !form.title.trim()}
              >
                <Save aria-hidden />
                {saveLabel}
              </Button>
            )}
          </>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
        <span>
          {words} words · {readingMinutes(words)} min read
        </span>
        {!isNew && canWrite && (
          <span aria-live="polite" data-testid="autosave-status">
            {AUTOSAVE_TEXT[autosave.status] || (dirty ? "Unsaved changes" : "")}
            {autosave.lastSavedAt && autosave.status === "saved" && (
              <> · {autosave.lastSavedAt.toLocaleTimeString()}</>
            )}
          </span>
        )}
        {record?.updated_at && <span>Last saved {formatDateTime(record.updated_at)}</span>}
        {!isNew && status === "draft" && (
          <span className="rounded-full bg-beige px-2 py-0.5 text-xs text-ink">
            Draft — not visible on the website
          </span>
        )}
      </div>
      {!canWrite && (
        <p className="mb-4 rounded-lg bg-beige px-4 py-2 text-sm">
          {record && can("articles.edit_own") && !can("articles.edit_any")
            ? "You can only edit your own articles while they are drafts."
            : "You have read-only access to this article."}
        </p>
      )}
      {record?.has_pending_changes && (
        <div
          role="status"
          className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gold-300 bg-gold-100/60 px-4 py-3 text-sm"
        >
          <p>
            <strong>Unpublished changes</strong> to {record.pending_fields.join(", ")}
            {record.pending_by && <> by {record.pending_by.display_name}</>}. The live article is
            unchanged until they are published.
          </p>
          <span className="flex gap-2">
            {allowed.publish_changes && (
              <Button
                size="sm"
                disabled={busy || dirty}
                onClick={() =>
                  runAction("publishChanges", "Changes published. The site rebuild is queued.")
                }
              >
                <UploadCloud aria-hidden />
                Publish changes
              </Button>
            )}
            {allowed.discard_changes && (
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => setConfirm("discard")}
              >
                Discard
              </Button>
            )}
          </span>
        </div>
      )}
      {error?.status === 400 && error.details && (
        <div role="alert" className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-900">
          {error.message || "Please fix the highlighted fields."}
        </div>
      )}

      <div
        role="tablist"
        aria-label="Editor sections"
        className="mb-4 flex gap-1 overflow-x-auto border-b border-charcoal/10"
      >
        {TABS.filter(([key]) => key !== "history" || (!isNew && allowed.view_revisions)).map(
          ([key, label]) => (
            <button
              key={key}
              role="tab"
              type="button"
              id={`tab-${key}`}
              aria-selected={tab === key}
              aria-controls={`panel-${key}`}
              onClick={() => setTab(key)}
              className={cn(
                "-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium",
                tab === key
                  ? "border-sage-700 text-sage-800"
                  : "border-transparent text-muted hover:text-charcoal",
              )}
            >
              {label}
              {key === "seo" &&
                seoChecks.data?.counts?.warning + seoChecks.data?.counts?.error > 0 && (
                  <span className="ml-1 rounded-full bg-gold-100 px-1.5 text-xs text-gold-700">
                    {seoChecks.data.counts.warning + seoChecks.data.counts.error}
                  </span>
                )}
            </button>
          ),
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">
          {tab === "content" && (
            <fieldset
              id="panel-content"
              role="tabpanel"
              aria-labelledby="tab-content"
              disabled={!canWrite}
              className="space-y-5"
            >
              <div className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5">
                <TextField
                  label="Title"
                  required
                  value={form.title}
                  onChange={set("title")}
                  error={err("title")}
                />
                <TextField
                  label="Subtitle"
                  value={form.subtitle}
                  onChange={set("subtitle")}
                  error={err("subtitle")}
                />
                <TextAreaField
                  label="Excerpt"
                  hint="Shown on article cards and as the default description."
                  value={form.excerpt}
                  onChange={set("excerpt")}
                  error={err("excerpt")}
                />
              </div>
              <div className="rounded-xl border border-charcoal/10 bg-cream/40 p-3 sm:p-5">
                <BlockEditor
                  blocks={form.body}
                  onChange={set("body")}
                  errors={error?.details?.body}
                  disabled={!canWrite}
                />
              </div>
            </fieldset>
          )}

          {tab === "details" && (
            <fieldset
              id="panel-details"
              role="tabpanel"
              aria-labelledby="tab-details"
              disabled={!canWrite}
              className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5"
            >
              <legend className="sr-only">Article details</legend>
              <div>
                <p className="mb-1 text-sm font-medium">Featured image</p>
                <ImageChooser
                  label="featured image"
                  mediaId={form.featured_image_id ? Number(form.featured_image_id) : null}
                  onChange={(mediaId) => set("featured_image_id")(mediaId ?? "")}
                  disabled={!canWrite}
                />
                {err("featured_image_id") && (
                  <p role="alert" className="mt-1 text-sm text-red-800">
                    {err("featured_image_id")}
                  </p>
                )}
              </div>
              <SelectField
                label="Author"
                options={option(authors, "display_name")}
                value={String(form.author_id)}
                onChange={set("author_id")}
                error={err("author_id")}
              />
              <SelectField
                label="Primary topic"
                options={option(topics, "name")}
                value={String(form.primary_topic_id)}
                onChange={set("primary_topic_id")}
                error={err("primary_topic_id")}
              />
              <MultiSelect
                legend="Additional topics"
                options={topics
                  .filter((t) => String(t.id) !== String(form.primary_topic_id))
                  .map((t) => ({ value: t.id, label: t.name }))}
                value={form.secondary_topic_ids}
                onChange={set("secondary_topic_ids")}
              />
              <MultiSelect
                legend="Tags"
                options={tags.map((t) => ({ value: t.id, label: t.name }))}
                value={form.tag_ids}
                onChange={set("tag_ids")}
              />
              <CheckboxField
                label="Featured article"
                hint="Shown in featured sections."
                checked={form.featured}
                onChange={set("featured")}
              />
              <details className="rounded-lg border border-charcoal/10 p-4">
                <summary className="cursor-pointer text-sm font-medium">Migration details</summary>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <TextField
                    label="Original URL"
                    value={form.original_url}
                    onChange={set("original_url")}
                    error={err("original_url")}
                  />
                  <TextField
                    label="Original slug"
                    value={form.original_slug}
                    onChange={set("original_slug")}
                    error={err("original_slug")}
                  />
                </div>
              </details>
            </fieldset>
          )}

          {tab === "seo" && (
            <fieldset id="panel-seo" role="tabpanel" aria-labelledby="tab-seo" disabled={!canWrite}>
              <SeoPanel
                articleId={isNew ? undefined : Number(id)}
                form={{ ...form, first_published: Boolean(record?.first_published_at) }}
                set={set}
                can={allowed}
                slugLocked={Boolean(record?.slug_locked)}
                checks={seoChecks.data}
                err={err}
                onRefreshChecks={isNew ? undefined : seoChecks.reload}
              />
            </fieldset>
          )}

          {tab === "history" && !isNew && (
            <div id="panel-history" role="tabpanel" aria-labelledby="tab-history">
              <RevisionsPanel
                articleId={Number(id)}
                canRestore={Boolean(allowed.restore_revision)}
                lockVersion={lockVersion}
                refreshKey={historyKey}
                onRestored={(res) => {
                  setLockVersion(res.data.lock_version);
                  article.setData(res.data);
                  setForm(toForm(res.data));
                  setSaved(toForm(res.data));
                  seoChecks.reload();
                  notify(
                    res.meta?.save_result === "pending"
                      ? "Revision restored as unpublished changes."
                      : "Revision restored.",
                  );
                }}
              />
            </div>
          )}
        </div>

        <aside className="space-y-5">
          <section
            aria-labelledby="publish-heading"
            className="rounded-xl border border-charcoal/10 bg-white p-5"
          >
            <h2
              id="publish-heading"
              className="flex items-center justify-between font-sans text-base font-semibold"
            >
              Publishing <StatusBadge status={status} />
            </h2>
            {record?.review_status && record.review_status !== "none" && (
              <p className="mt-2 flex items-center gap-1.5 text-sm">
                <ClipboardCheck aria-hidden className="size-4 text-sage-700" />
                {record.review_status === "submitted"
                  ? `Submitted for review ${formatDateTime(record.submitted_at)}`
                  : `Approved ${formatDateTime(record.approved_at)}`}
              </p>
            )}
            {record?.published_at && (
              <p className="mt-2 text-sm text-muted">
                {status === "scheduled" ? "Scheduled for" : "Published"}{" "}
                {formatDateTime(record.published_at)}
              </p>
            )}
            {isNew && (
              <p className="mt-2 text-sm text-muted">Create the draft to enable publishing.</p>
            )}
            {!isNew && dirty && (
              <p className="mt-2 text-sm text-gold-700">Save your changes before publishing.</p>
            )}
            {!isNew && (
              <div className="mt-4 space-y-3">
                {allowed.submit && (
                  <Button
                    variant="outline"
                    className="w-full"
                    size="sm"
                    disabled={busy || dirty}
                    onClick={() =>
                      runAction("submit", "Submitted for review. An editor will take a look.")
                    }
                  >
                    <ClipboardCheck aria-hidden />
                    Submit for review
                  </Button>
                )}
                {allowed.approve && (
                  <Button
                    variant="outline"
                    className="w-full"
                    size="sm"
                    disabled={busy || dirty}
                    onClick={() => runAction("approve", "Article approved.")}
                  >
                    <BadgeCheck aria-hidden />
                    Approve
                  </Button>
                )}
                {allowed.publish && (
                  <>
                    <Button
                      className="w-full"
                      size="sm"
                      disabled={busy || dirty}
                      onClick={() =>
                        runAction("publish", "Article published. The site rebuild has been queued.")
                      }
                    >
                      <Send aria-hidden />
                      Publish now
                    </Button>
                    <div className="flex flex-wrap items-end gap-2">
                      <TextField
                        className="min-w-0 flex-1 basis-44"
                        label="Schedule for"
                        type="datetime-local"
                        value={scheduleAt}
                        onChange={(e) => setScheduleAt(e.target.value)}
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy || dirty || !scheduleAt}
                        onClick={() => runAction("schedule", "Article scheduled.")}
                      >
                        <CalendarClock aria-hidden />
                        Schedule
                      </Button>
                    </div>
                    <p className="text-xs text-muted">
                      Times use your browser&apos;s time zone and are stored in UTC. Scheduled
                      articles go live automatically (publishing worker).
                    </p>
                  </>
                )}
                {allowed.unpublish && (
                  <Button
                    variant="outline"
                    className="w-full"
                    size="sm"
                    disabled={busy}
                    onClick={() => setConfirm("unpublish")}
                  >
                    <Undo2 aria-hidden />
                    Unpublish
                  </Button>
                )}
                {allowed.archive && (
                  <Button
                    variant="ghost"
                    className="w-full"
                    size="sm"
                    disabled={busy}
                    onClick={() => setConfirm("archive")}
                  >
                    <Archive aria-hidden />
                    Archive
                  </Button>
                )}
                {allowed.restore && (
                  <Button
                    variant="outline"
                    className="w-full"
                    size="sm"
                    disabled={busy}
                    onClick={() => runAction("restore", "Article restored to draft.")}
                  >
                    <RotateCcw aria-hidden />
                    Restore to draft
                  </Button>
                )}
                {allowed.delete && (
                  <Button
                    variant="ghost"
                    className="w-full text-red-800"
                    size="sm"
                    disabled={busy}
                    onClick={() => setConfirm("delete")}
                  >
                    <Trash2 aria-hidden />
                    Delete permanently
                  </Button>
                )}
              </div>
            )}
            {error?.details &&
              Object.keys(error.details).some((k) =>
                ["author_id", "primary_topic_id", "featured_image_id", "body", "excerpt"].includes(
                  k,
                ),
              ) &&
              error.message?.includes("ready") && (
                <p className="mt-3 text-sm text-red-800">
                  Complete the required fields:{" "}
                  {Object.keys(error.details).join(", ").replaceAll("_id", "").replaceAll("_", " ")}
                  .
                </p>
              )}
          </section>
          {form.featured_image_id && tab !== "details" && (
            <section className="rounded-xl border border-charcoal/10 bg-white p-4">
              <p className="mb-2 text-sm font-medium">Featured image</p>
              <MediaThumb id={Number(form.featured_image_id)} className="aspect-[16/10] w-full" />
            </section>
          )}
          <Link to="/admin/articles" className="inline-block text-sm text-sage-700 hover:underline">
            ← Back to articles
          </Link>
        </aside>
      </div>

      <Modal
        open={preview}
        onClose={() => setPreview(false)}
        title="Preview"
        description="How the article body will read on the website (unsaved changes included). Images show once chosen."
        size="lg"
      >
        <article>
          <h1 className="text-3xl font-medium">{form.title || "Untitled article"}</h1>
          {form.subtitle && (
            <p className="mt-2 font-serif text-lg text-muted italic">{form.subtitle}</p>
          )}
          <div className="mt-6">
            <ArticleBody
              blocks={cleanBlocks(form.body).filter(
                (b) => !["image", "gallery", "related"].includes(b.type),
              )}
            />
          </div>
        </article>
      </Modal>

      <ConfirmDialog
        open={confirm === "unpublish"}
        title="Unpublish this article?"
        message="It will return to draft and disappear from the public site after the next build."
        confirmLabel="Unpublish"
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={() => runAction("unpublish", "Article unpublished.")}
      />
      <ConfirmDialog
        open={confirm === "archive"}
        title="Archive this article?"
        message="Archived articles are hidden from the public site. You can restore them to draft later."
        confirmLabel="Archive"
        tone="danger"
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={() => runAction("archive", "Article archived.")}
      />
      <ConfirmDialog
        open={confirm === "delete"}
        title="Delete this article permanently?"
        message="This draft has never been published. Deleting it cannot be undone."
        confirmLabel="Delete article"
        tone="danger"
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={() => runAction("remove", "Article deleted.")}
      />
      <ConfirmDialog
        open={confirm === "discard"}
        title="Discard unpublished changes?"
        message="The working copy returns to the live article. Earlier versions stay in the history."
        confirmLabel="Discard changes"
        tone="danger"
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={() => runAction("discardChanges", "Unpublished changes discarded.")}
      />
      <Modal
        open={conflictOpen}
        onClose={() => setConfirm(null)}
        title="Someone else changed this article"
        description={
          autosave.conflict?.updated_by || error?.details?.updated_by
            ? `Last saved by ${autosave.conflict?.updated_by ?? error?.details?.updated_by}.`
            : undefined
        }
        footer={
          <>
            <Button variant="outline" onClick={reloadLatest}>
              Load their version
            </Button>
            <Button onClick={keepMine}>Keep my version</Button>
          </>
        }
      >
        <p className="text-ink">
          Your changes were not saved, to avoid overwriting newer work. Load the latest version
          (your unsaved edits are discarded), or keep your version and save it over theirs.
        </p>
      </Modal>
    </>
  );
}

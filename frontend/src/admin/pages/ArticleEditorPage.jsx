import { Archive, CalendarClock, Eye, RotateCcw, Save, Send, Undo2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { fieldError } from "../components/fieldError";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { BlockEditor } from "../components/BlockEditor";
import { cleanBlocks } from "../components/blocks";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
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
  canonical_url: "",
  noindex: false,
  original_url: "",
  original_slug: "",
};
const FIELDS = Object.keys(EMPTY);

function toForm(article) {
  const form = {};
  FIELDS.forEach((f) => {
    const v = article[f];
    form[f] = v === null || v === undefined ? EMPTY[f] : v;
  });
  return form;
}

function toPayload(form, { includeSlug }) {
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
  if (!includeSlug) delete payload.slug;
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

export function ArticleEditorPage() {
  const { id } = useParams();
  const isNew = !id;
  const api = useAdminApi();
  const navigate = useNavigate();
  const notify = useNotify();
  const { can } = usePermissions();
  const canWrite = can("content.write");

  const article = useAdminQuery(
    () => (isNew ? Promise.resolve({ data: null }) : api.articles.get(id)),
    [id],
  );
  const refs = useAdminQuery(
    () =>
      Promise.all([api.topics.list(), api.authors.list(), api.tags.list(), api.media.list()]).then(
        ([topics, authors, tags, media]) => ({
          data: { topics: topics.data, authors: authors.data, tags: tags.data, media: media.data },
        }),
      ),
    [],
  );

  const [form, setForm] = useState(EMPTY);
  const [saved, setSaved] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [scheduleAt, setScheduleAt] = useState("");

  const record = article.data;
  // Sync the form when the article (re)loads.
  const [loadedFor, setLoadedFor] = useState(null);
  if (record && loadedFor !== record.updated_at) {
    setLoadedFor(record.updated_at);
    setForm(toForm(record));
    setSaved(toForm(record));
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
    }
  }

  const set = (field) => (e) =>
    setForm((f) => ({
      ...f,
      [field]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e,
    }));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload = toPayload(form, { includeSlug: isNew || !record?.slug_locked });
      if (isNew) {
        const res = await api.articles.create(payload);
        setSaved(form);
        notify("Draft created.");
        navigate(`/admin/articles/${res.data.id}/edit`, { replace: true });
      } else {
        const res = await api.articles.update(id, payload);
        article.setData(res.data);
        notify("Changes saved.");
      }
    } catch (err) {
      setError(err);
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
            : await api.articles[action](id);
      article.setData(res.data);
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

  const { topics, authors, tags, media } = refs.data;
  const status = record?.status ?? "draft";
  const option = (items, labelKey) => [
    { value: "", label: "— Select —" },
    ...items.map((i) => ({
      value: String(i.id),
      label: i[labelKey] + (i.status && i.status !== "active" ? ` (${i.status})` : ""),
    })),
  ];
  const err = (name) => fieldError(error, name);
  const featuredImage = media.find((m) => String(m.id) === String(form.featured_image_id));

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
            {canWrite && (
              <Button
                size="sm"
                onClick={save}
                disabled={busy || (!dirty && !isNew) || !form.title.trim()}
              >
                <Save aria-hidden />
                {isNew ? "Create draft" : "Save changes"}
              </Button>
            )}
          </>
        }
      />
      {!canWrite && (
        <p className="mb-4 rounded-lg bg-beige px-4 py-2 text-sm">
          You have read-only access to articles.
        </p>
      )}
      {error?.status === 400 && error.details && (
        <div role="alert" className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-900">
          {error.message || "Please fix the highlighted fields."}
        </div>
      )}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <fieldset disabled={!canWrite} className="min-w-0 space-y-5">
          <div className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5">
            <TextField
              label="Title"
              required
              value={form.title}
              onChange={set("title")}
              error={err("title")}
            />
            <TextField
              label="Slug"
              value={form.slug}
              onChange={set("slug")}
              error={err("slug")}
              disabled={record?.slug_locked}
              hint={
                record?.slug_locked
                  ? "Locked after first publication to keep URLs stable."
                  : "Leave empty to generate from the title."
              }
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
          <div className="rounded-xl border border-charcoal/10 bg-cream/40 p-5">
            <BlockEditor
              blocks={form.body}
              onChange={set("body")}
              errors={error?.details?.body}
              disabled={!canWrite}
            />
          </div>
          <details className="rounded-xl border border-charcoal/10 bg-white p-5">
            <summary className="cursor-pointer font-medium">SEO and migration</summary>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <TextField
                label="SEO title"
                value={form.seo_title}
                onChange={set("seo_title")}
                error={err("seo_title")}
              />
              <TextField
                label="Canonical URL"
                placeholder="https://"
                value={form.canonical_url}
                onChange={set("canonical_url")}
                error={err("canonical_url")}
              />
              <TextAreaField
                className="sm:col-span-2"
                label="Meta description"
                value={form.meta_description}
                onChange={set("meta_description")}
                error={err("meta_description")}
              />
              <SelectField
                label="Social sharing image"
                options={option(media, "filename")}
                value={String(form.social_image_id)}
                onChange={set("social_image_id")}
                error={err("social_image_id")}
              />
              <CheckboxField
                label="Hide from search engines (noindex)"
                checked={form.noindex}
                onChange={set("noindex")}
              />
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
                {can("content.publish") && ["draft", "scheduled"].includes(status) && (
                  <>
                    <Button
                      className="w-full"
                      size="sm"
                      disabled={busy || dirty}
                      onClick={() =>
                        runAction(
                          "publish",
                          "Article published. The static site updates after the next build.",
                        )
                      }
                    >
                      <Send aria-hidden />
                      Publish now
                    </Button>
                    <div className="flex items-end gap-2">
                      <TextField
                        className="flex-1"
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
                      Scheduled articles go live when the publish-due task runs and the site is
                      rebuilt.
                    </p>
                  </>
                )}
                {can("content.moderate") && ["published", "scheduled"].includes(status) && (
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
                {can("content.moderate") && status !== "archived" && (
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
                {canWrite && status === "archived" && (
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

          <fieldset
            disabled={!canWrite}
            className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5"
          >
            <legend className="sr-only">Article details</legend>
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
            <SelectField
              label="Featured image"
              options={option(media, "filename")}
              value={String(form.featured_image_id)}
              onChange={set("featured_image_id")}
              error={err("featured_image_id")}
            />
            {featuredImage?.url && (
              <img
                src={featuredImage.url}
                alt={featuredImage.alt_text}
                className="aspect-[16/10] w-full rounded-lg bg-beige object-cover"
              />
            )}
            <CheckboxField
              label="Featured article"
              hint="Shown in featured sections."
              checked={form.featured}
              onChange={set("featured")}
            />
          </fieldset>
          <ButtonLink to="/admin/articles" variant="ghost" size="sm">
            ← Back to articles
          </ButtonLink>
        </aside>
      </div>

      <Modal
        open={preview}
        onClose={() => setPreview(false)}
        title="Preview"
        description="How the article body will read on the website (unsaved changes included)."
        size="lg"
      >
        <article>
          <h1 className="text-3xl font-medium">{form.title || "Untitled article"}</h1>
          {form.subtitle && (
            <p className="mt-2 font-serif text-lg text-muted italic">{form.subtitle}</p>
          )}
          {featuredImage?.url && (
            <img
              src={featuredImage.url}
              alt={featuredImage.alt_text}
              className="mt-4 aspect-[16/10] w-full rounded-xl object-cover"
            />
          )}
          <div className="mt-6">
            <ArticleBody blocks={cleanBlocks(form.body)} />
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
    </>
  );
}

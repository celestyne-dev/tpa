import { Archive, CalendarClock, Copy, Eye, RotateCcw, Send, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router";
import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { cn, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { BlockEditor } from "../../components/BlockEditor";
import { cleanBlocks } from "../../components/blocks";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { fieldError } from "../../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../../components/Fields";
import { ImageChooser } from "../../components/media/ImageChooser";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { CourseAssessmentsPanel } from "./CourseAssessmentsPanel";
import { CourseAssignmentsPanel } from "./CourseAssignmentsPanel";
import { CourseContentPanel } from "./CourseContentPanel";
import { CourseEnrollmentsPanel } from "./CourseEnrollmentsPanel";

const TEXT_BLOCKS = [
  "paragraph",
  "heading",
  "bulleted",
  "numbered",
  "quote",
  "callout",
  "image",
  "divider",
];
const lines = (list) => (list ?? []).join("\n");
const toList = (text) =>
  text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

function formFromCourse(c) {
  return {
    title: c.title,
    slug: c.slug,
    subtitle: c.subtitle,
    summary: c.summary,
    description: c.description,
    outcomes: lines(c.outcomes),
    prerequisites: lines(c.prerequisites),
    audience: lines(c.audience),
    level: c.level,
    estimated_minutes: c.estimated_minutes ?? "",
    category_id: c.category_id ?? "",
    author_id: c.author_id ?? "",
    topic_ids: c.topic_ids,
    cover_media_id: c.cover_media_id,
    social_image_id: c.social_image_id,
    access_type: c.access_type,
    availability: c.availability,
    enrollment_open: c.enrollment_open,
    access_days: c.access_days ?? "",
    product_id: c.product_id ?? "",
    certificate_enabled: c.certificate_enabled,
    is_featured: c.is_featured,
    featured_order: c.featured_order,
    seo_title: c.seo_title ?? "",
    meta_description: c.meta_description ?? "",
    noindex: c.noindex,
  };
}

function payload(form, course) {
  const num = (v) => (v === "" || v == null ? null : Number(v));
  const body = {
    ...form,
    description: cleanBlocks(form.description),
    outcomes: toList(form.outcomes),
    prerequisites: toList(form.prerequisites),
    audience: toList(form.audience),
    estimated_minutes: num(form.estimated_minutes),
    category_id: num(form.category_id),
    author_id: num(form.author_id),
    access_days: num(form.access_days),
    product_id: num(form.product_id),
    featured_order: Number(form.featured_order) || 0,
    seo_title: form.seo_title || null,
    meta_description: form.meta_description || null,
    lock_version: course.lock_version,
  };
  if (course.first_published_at) delete body.slug;
  return body;
}

function DetailsForm({ course, options, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [form, setForm] = useState(() => formFromCourse(course));
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const canEdit = course.can.edit && course.status !== "archived";
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await api.courses.update(course.id, payload(form, course));
      notify("Course saved.");
      onSaved(res.data);
    } catch (err) {
      setError(err);
      notify(err.message, "error");
    } finally {
      setSaving(false);
    }
  };
  const err = (name) => fieldError(error, name);
  const products = options?.products ?? [];
  return (
    <form onSubmit={save} className="max-w-4xl space-y-8">
      <fieldset disabled={!canEdit} className="space-y-4">
        <legend className="text-lg font-medium">About the course</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Title"
            required
            value={form.title}
            error={err("title")}
            onChange={(e) => set({ title: e.target.value })}
          />
          <TextField
            label="Address"
            hint={
              course.first_published_at
                ? "Published courses keep their address."
                : `/courses/${form.slug}`
            }
            value={form.slug}
            disabled={Boolean(course.first_published_at)}
            error={err("slug")}
            onChange={(e) => set({ slug: e.target.value })}
          />
          <TextField
            className="sm:col-span-2"
            label="Subtitle"
            value={form.subtitle}
            error={err("subtitle")}
            onChange={(e) => set({ subtitle: e.target.value })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Short summary"
            hint="Catalogue cards and search results. Required to publish."
            value={form.summary}
            error={err("summary")}
            onChange={(e) => set({ summary: e.target.value })}
          />
          <TextAreaField
            label="What learners will be able to do"
            hint="One outcome per line."
            rows={5}
            value={form.outcomes}
            error={err("outcomes")}
            onChange={(e) => set({ outcomes: e.target.value })}
          />
          <TextAreaField
            label="Who it's for"
            hint="One per line."
            rows={5}
            value={form.audience}
            error={err("audience")}
            onChange={(e) => set({ audience: e.target.value })}
          />
          <TextAreaField
            label="Before you start (prerequisites)"
            hint="One per line; leave empty if none."
            rows={3}
            value={form.prerequisites}
            error={err("prerequisites")}
            onChange={(e) => set({ prerequisites: e.target.value })}
          />
          <div className="grid gap-4">
            <SelectField
              label="Level"
              value={form.level}
              onChange={(e) => set({ level: e.target.value })}
              options={[
                { value: "all_levels", label: "All levels" },
                { value: "beginner", label: "Beginner" },
                { value: "intermediate", label: "Intermediate" },
                { value: "advanced", label: "Advanced" },
              ]}
            />
            <TextField
              label="Estimated reading time (minutes)"
              hint={`Leave empty to add up the lessons (currently ${course.total_minutes} min).`}
              type="number"
              min="1"
              value={form.estimated_minutes}
              error={err("estimated_minutes")}
              onChange={(e) => set({ estimated_minutes: e.target.value })}
            />
          </div>
          <SelectField
            label="Category"
            value={String(form.category_id)}
            error={err("category_id")}
            onChange={(e) => set({ category_id: e.target.value })}
            options={[
              { value: "", label: "No category" },
              ...(options?.categories ?? [])
                .filter((c) => c.is_active || c.id === course.category_id)
                .map((c) => ({ value: String(c.id), label: c.name })),
            ]}
          />
          <SelectField
            label="Author / instructor"
            value={String(form.author_id)}
            error={err("author_id")}
            onChange={(e) => set({ author_id: e.target.value })}
            options={[
              { value: "", label: "Think Positive Always" },
              ...(options?.authors ?? []).map((a) => ({ value: String(a.id), label: a.name })),
            ]}
          />
        </div>
        <fieldset>
          <legend className="text-sm font-medium">Topics</legend>
          <div className="mt-2 flex flex-wrap gap-4">
            {(options?.topics ?? []).map((t) => (
              <CheckboxField
                key={t.id}
                label={t.name}
                checked={form.topic_ids.includes(t.id)}
                onChange={(e) =>
                  set({
                    topic_ids: e.target.checked
                      ? [...form.topic_ids, t.id]
                      : form.topic_ids.filter((id) => id !== t.id),
                  })
                }
              />
            ))}
          </div>
          {err("topic_ids") && <p className="mt-1 text-sm text-red-800">{err("topic_ids")}</p>}
        </fieldset>
        <div>
          <p className="mb-2 text-sm font-medium">Cover image (from the Media Library)</p>
          <ImageChooser
            label="cover image"
            mediaId={form.cover_media_id}
            onChange={(id) => set({ cover_media_id: id })}
            disabled={!canEdit}
          />
          {err("cover_media_id") && (
            <p className="mt-1 text-sm text-red-800">{err("cover_media_id")}</p>
          )}
        </div>
        <BlockEditor
          legend="Course description (shown on the course page)"
          blocks={form.description}
          allowed={TEXT_BLOCKS}
          errors={error?.details?.description}
          onChange={(description) => set({ description })}
          disabled={!canEdit}
        />
      </fieldset>

      <fieldset disabled={!canEdit} className="space-y-4">
        <legend className="text-lg font-medium">Access and enrolment</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            label="Access"
            value={form.access_type}
            error={err("access_type")}
            onChange={(e) => set({ access_type: e.target.value })}
            options={[
              { value: "free", label: "Free (verified account)" },
              { value: "premium", label: "Premium (bought through the course product)" },
            ]}
          />
          <SelectField
            label="Availability"
            value={form.availability}
            onChange={(e) => set({ availability: e.target.value })}
            options={[
              { value: "available", label: "Available" },
              { value: "coming_soon", label: "Coming soon (page visible, no enrolment)" },
            ]}
          />
          <SelectField
            label="Course product (price and checkout)"
            hint="Products of type “Online course”. Premium courses need a paid one; its files are the course worksheets."
            value={String(form.product_id)}
            error={err("product_id")}
            onChange={(e) => set({ product_id: e.target.value })}
            options={[
              { value: "", label: "None" },
              ...products.map((p) => ({
                value: String(p.id),
                label: `${p.title} (${p.pricing_model}, ${p.status})${p.linked && p.id !== course.product_id ? " — used by another course" : ""}`,
              })),
            ]}
          />
          {form.access_type === "free" && (
            <TextField
              label="Access period (days)"
              hint="Leave empty for lifetime access."
              type="number"
              min="1"
              value={form.access_days}
              error={err("access_days")}
              onChange={(e) => set({ access_days: e.target.value })}
            />
          )}
        </div>
        <div className="flex flex-wrap gap-6">
          <CheckboxField
            label="Open for new enrolments"
            checked={form.enrollment_open}
            onChange={(e) => set({ enrollment_open: e.target.checked })}
          />
          <CheckboxField
            label="Issue certificates of completion"
            checked={form.certificate_enabled}
            onChange={(e) => set({ certificate_enabled: e.target.checked })}
          />
          <CheckboxField
            label="Feature in the catalogue"
            checked={form.is_featured}
            onChange={(e) => set({ is_featured: e.target.checked })}
          />
        </div>
        {course.product && (
          <p className="text-sm text-muted">
            Prices, sales status and worksheets are managed on the product:{" "}
            <Link
              to={`/admin/products/${course.product.id}`}
              className="underline underline-offset-4"
            >
              {course.product.title}
            </Link>
            .
          </p>
        )}
      </fieldset>

      <fieldset disabled={!canEdit} className="space-y-4">
        <legend className="text-lg font-medium">Search and sharing</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="SEO title"
            hint="Defaults to the course title."
            value={form.seo_title}
            error={err("seo_title")}
            onChange={(e) => set({ seo_title: e.target.value })}
          />
          <TextAreaField
            label="Meta description"
            hint="Defaults to the summary."
            value={form.meta_description}
            error={err("meta_description")}
            onChange={(e) => set({ meta_description: e.target.value })}
          />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Social sharing image (optional)</p>
          <ImageChooser
            label="social image"
            mediaId={form.social_image_id}
            onChange={(id) => set({ social_image_id: id })}
            disabled={!canEdit}
          />
        </div>
        <CheckboxField
          label="Hide from search engines (noindex)"
          checked={form.noindex}
          onChange={(e) => set({ noindex: e.target.checked })}
        />
      </fieldset>
      {canEdit && (
        <div className="sticky bottom-0 -mx-1 flex items-center gap-3 border-t border-charcoal/10 bg-ivory/95 p-3">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save course"}
          </Button>
          {error?.details?.code === "edit_conflict" && (
            <p role="alert" className="text-sm text-red-800">
              Someone else saved this course. Reload the page to see their changes.
            </p>
          )}
        </div>
      )}
    </form>
  );
}

function PublishDialog({ course, onClose, onDone }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [when, setWhen] = useState("");
  const [error, setError] = useState(null);
  const publish = async () => {
    setError(null);
    try {
      const res = await api.courses.action(
        course.id,
        "publish",
        when ? { publish_at: new Date(when).toISOString() } : {},
      );
      notify(res.data.status === "scheduled" ? "Course scheduled." : "Course published.");
      onDone(res.data);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="Publish course"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={publish}>{when ? "Schedule" : "Publish now"}</Button>
        </>
      }
    >
      <p className="text-sm text-muted">
        Published courses appear in the catalogue, the sitemap and search. Only published lessons
        are shown to learners.
      </p>
      <TextField
        className="mt-4"
        label="Publish later (optional)"
        hint="Your local time. The scheduler publishes it within a few minutes of this time."
        type="datetime-local"
        value={when}
        onChange={(e) => setWhen(e.target.value)}
      />
      {error && (
        <div role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-900">
          <p>{error.message}</p>
          {error.details?.readiness && (
            <ul className="mt-1 list-disc pl-5">
              {error.details.readiness.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  );
}

const SECTIONS = [
  ["", "Details"],
  ["content", "Curriculum"],
  ["assessments", "Assessments"],
  ["assignments", "Assignments"],
  ["enrollments", "Learners"],
];

/** One course: details, curriculum, assessments and learners (route-based tabs). */
export function CourseEditorPage({ section = "" }) {
  const { id } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const {
    data: course,
    error,
    loading,
    reload,
    setData,
  } = useAdminQuery(() => api.courses.get(id), [id]);
  const options = useAdminQuery(() => api.courses.options(), []);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);
  const { can: hasPermission } = usePermissions();

  if (error) return <ErrorState title="We couldn't load this course" onRetry={reload} />;
  if (loading && !course) return <p role="status">Loading course…</p>;

  const run = async (action, message) => {
    setBusy(true);
    try {
      const res = await api.courses.action(course.id, action);
      notify(message);
      if (action === "duplicate") navigate(`/admin/courses/${res.data.id}`);
      else setData(res.data);
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
      setDialog(null);
    }
  };
  const remove = async () => {
    try {
      await api.courses.remove(course.id);
      notify("Course deleted.");
      navigate("/admin/courses");
    } catch (err) {
      notify(err.message, "error");
      setDialog(null);
    }
  };
  const can = course.can;
  const visible = SECTIONS.filter(
    ([key]) =>
      (key !== "enrollments" || can.view_enrollments) &&
      (key !== "assignments" || hasPermission("assignments.view")),
  );

  return (
    <>
      <AdminPageHeader
        title={course.title}
        description={
          course.status === "scheduled"
            ? `Scheduled for ${formatDateTime(course.published_at)}.`
            : course.status === "published"
              ? `Published · /courses/${course.slug}`
              : undefined
        }
        breadcrumbs={[{ label: "Courses", to: "/admin/courses" }, { label: course.title }]}
        actions={
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={course.status} />
            <ButtonLink to={`/admin/courses/${course.id}/preview`} variant="outline" size="sm">
              <Eye aria-hidden /> Preview
            </ButtonLink>
            {can.publish && ["draft", "scheduled"].includes(course.status) && (
              <Button size="sm" onClick={() => setDialog("publish")} disabled={busy}>
                {course.status === "scheduled" ? (
                  <CalendarClock aria-hidden />
                ) : (
                  <Send aria-hidden />
                )}
                {course.status === "scheduled" ? "Reschedule / publish" : "Publish"}
              </Button>
            )}
            {can.publish && ["published", "scheduled"].includes(course.status) && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => run("unpublish", "Course unpublished.")}
                disabled={busy}
              >
                <Undo2 aria-hidden /> Unpublish
              </Button>
            )}
            {can.create && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => run("duplicate", "Copy created as a draft.")}
                disabled={busy}
              >
                <Copy aria-hidden /> Duplicate
              </Button>
            )}
            {can.archive && course.status !== "archived" && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setDialog("archive")}
                disabled={busy}
              >
                <Archive aria-hidden /> Archive
              </Button>
            )}
            {can.archive && course.status === "archived" && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => run("restore", "Course restored as a draft.")}
                disabled={busy}
              >
                <RotateCcw aria-hidden /> Restore
              </Button>
            )}
            {can.archive && !course.first_published_at && course.enrollment_count === 0 && (
              <Button size="sm" variant="outline" onClick={() => setDialog("delete")}>
                <Trash2 aria-hidden /> Delete
              </Button>
            )}
          </div>
        }
      />
      {(course.readiness.issues.length > 0 || course.readiness.warnings.length > 0) && (
        <div className="mb-6 rounded-xl border border-gold-300 bg-gold-100/40 p-4 text-sm">
          {course.readiness.issues.length > 0 && (
            <>
              <p className="font-medium">Before publishing</p>
              <ul className="mt-1 list-disc pl-5">
                {course.readiness.issues.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </>
          )}
          {course.readiness.warnings.length > 0 && (
            <>
              <p className={cn("font-medium", course.readiness.issues.length && "mt-3")}>
                Worth checking
              </p>
              <ul className="mt-1 list-disc pl-5">
                {course.readiness.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      <nav
        aria-label="Course sections"
        className="mb-6 flex flex-wrap gap-1 border-b border-charcoal/10"
      >
        {visible.map(([key, label]) => (
          <NavLink
            key={key || "details"}
            to={`/admin/courses/${course.id}${key ? `/${key}` : ""}`}
            end
            className={({ isActive }) =>
              cn(
                "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
                isActive
                  ? "border-sage-700 text-charcoal"
                  : "border-transparent text-muted hover:text-charcoal",
              )
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
      {section === "" && (
        <DetailsForm
          key={course.lock_version}
          course={course}
          options={options.data}
          onSaved={setData}
        />
      )}
      {section === "content" && <CourseContentPanel course={course} onChanged={reload} />}
      {section === "assessments" && <CourseAssessmentsPanel course={course} onChanged={reload} />}
      {section === "assignments" && <CourseAssignmentsPanel course={course} />}
      {section === "enrollments" && <CourseEnrollmentsPanel course={course} />}
      {dialog === "publish" && (
        <PublishDialog
          course={course}
          onClose={() => setDialog(null)}
          onDone={(data) => {
            setData(data);
            setDialog(null);
          }}
        />
      )}
      <ConfirmDialog
        open={dialog === "archive"}
        title="Archive this course?"
        message="It leaves the catalogue. Enrolled learners keep access; nobody new can enrol."
        confirmLabel="Archive"
        busy={busy}
        onConfirm={() => run("archive", "Course archived.")}
        onCancel={() => setDialog(null)}
      />
      <ConfirmDialog
        open={dialog === "delete"}
        title="Delete this draft?"
        message="The course, its modules, lessons and assessments are removed permanently."
        confirmLabel="Delete"
        tone="danger"
        onConfirm={remove}
        onCancel={() => setDialog(null)}
      />
    </>
  );
}

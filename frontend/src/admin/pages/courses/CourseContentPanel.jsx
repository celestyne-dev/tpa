import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../../adminApiContext";
import { BlockEditor } from "../../components/BlockEditor";
import { LESSON_BLOCKS, cleanBlocks, countWords, readingMinutes } from "../../components/blocks";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { fieldError } from "../../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../../components/Fields";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { UNSAVED_MESSAGE, useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import { DraftPreviewDialog, PublishDialog, RevisionsDialog } from "./LessonRevisions";

function layoutOf(modules) {
  return modules.map((m) => ({ module_id: m.id, lesson_ids: m.lessons.map((l) => l.id) }));
}

function IconAction({ label, icon: Icon, ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="rounded p-1.5 text-muted hover:bg-beige hover:text-charcoal disabled:opacity-40"
      {...props}
    >
      <Icon aria-hidden className="size-4" />
    </button>
  );
}

function ModuleForm({ module, onSave, onCancel }) {
  const [form, setForm] = useState({
    title: module?.title ?? "",
    description: module?.description ?? "",
    objectives: (module?.objectives ?? []).join("\n"),
  });
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      await onSave({
        title: form.title,
        description: form.description,
        objectives: form.objectives
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean),
      });
    } catch (err) {
      setError(err);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl bg-cream/60 p-4">
      <TextField
        label="Module title"
        required
        value={form.title}
        error={fieldError(error, "title")}
        onChange={(e) => setForm({ ...form, title: e.target.value })}
      />
      <TextAreaField
        label="Description (optional)"
        value={form.description}
        error={fieldError(error, "description")}
        onChange={(e) => setForm({ ...form, description: e.target.value })}
      />
      <TextAreaField
        label="Learning objectives (optional, one per line)"
        value={form.objectives}
        error={fieldError(error, "objectives")}
        onChange={(e) => setForm({ ...form, objectives: e.target.value })}
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!form.title.trim()}>
          Save module
        </Button>
        {onCancel && (
          <Button type="button" size="sm" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

const savedAt = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "";

function LessonState({ lesson }) {
  const live = lesson.live;
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      {live?.visible ? (
        <span className="rounded-full bg-sage-100 px-2.5 py-0.5 font-medium text-sage-800">
          Live · revision {live.revision}
        </span>
      ) : live ? (
        <span className="rounded-full bg-beige px-2.5 py-0.5 font-medium">
          Unpublished · revision {live.revision} kept
        </span>
      ) : (
        <span className="rounded-full bg-beige px-2.5 py-0.5 font-medium">Never published</span>
      )}
      {lesson.has_draft_changes && (
        <span className="rounded-full bg-gold-100 px-2.5 py-0.5 font-medium text-gold-700">
          Draft has unpublished changes
        </span>
      )}
      {lesson.draft_saved_at && (
        <span className="text-muted">
          Last saved {savedAt(lesson.draft_saved_at)}
          {lesson.draft_saved_by ? ` by ${lesson.draft_saved_by}` : ""}
        </span>
      )}
    </p>
  );
}

function LessonEditor({ course, lessonId, onClose, onChanged, onDirty }) {
  const api = useAdminApi();
  const notify = useNotify();
  const {
    data: lesson,
    setData,
    reload,
  } = useAdminQuery(() => api.courses.lesson(course.id, lessonId), [lessonId]);
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [conflict, setConflict] = useState(null);
  const [saving, setSaving] = useState(false);
  const [dialog, setDialog] = useState(null); // "preview" | "revisions" | "publish"
  useUnsavedChanges(Boolean(form));
  useEffect(() => {
    onDirty?.(Boolean(form));
  }, [form, onDirty]);
  if (!lesson) return <p role="status">Loading lesson…</p>;
  const current = form ?? {
    title: lesson.title,
    slug: lesson.slug,
    summary: lesson.summary,
    estimated_minutes: lesson.estimated_minutes ?? "",
    is_preview: lesson.is_preview,
    completion_required: lesson.completion_required,
    body: lesson.body,
  };
  const set = (patch) => setForm({ ...current, ...patch });
  const can = course.can;
  const archived = course.status === "archived";
  const canEdit = can.edit_drafts && !archived;
  const canSlug = can.manage_curriculum && !archived && !lesson.live;
  const replace = (data) => {
    setData(data);
    setForm(null);
    setConflict(null);
    onChanged();
  };
  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const { slug, ...fields } = current;
      const res = await api.courses.updateLesson(course.id, lessonId, {
        ...fields,
        ...(canSlug && slug !== lesson.slug && { slug }),
        lock_version: lesson.lock_version,
        estimated_minutes:
          current.estimated_minutes === "" ? null : Number(current.estimated_minutes),
        body: cleanBlocks(current.body),
      });
      replace(res.data);
      notify("Draft saved. Learners still see the live version until you publish.");
    } catch (err) {
      if (err.code === "edit_conflict") setConflict(err.details ?? {});
      else {
        setError(err);
        notify(err.message, "error");
      }
    } finally {
      setSaving(false);
    }
  };
  const publish = async (note) => {
    try {
      const res = await api.courses.publishLesson(course.id, lessonId, note);
      replace(res.data);
      setDialog(null);
      notify("Lesson published.");
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const unpublish = async () => {
    try {
      const res = await api.courses.lessonStatus(course.id, lessonId, "draft");
      replace(res.data);
      notify("Lesson unpublished.");
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const discard = async () => {
    try {
      const res = await api.courses.discardDraft(course.id, lessonId, lesson.lock_version);
      replace(res.data);
      notify("Draft discarded; showing the live version.");
    } catch (err) {
      if (err.code === "edit_conflict") setConflict(err.details ?? {});
      else notify(err.message, "error");
    }
  };
  const loadLatest = () => {
    setForm(null);
    setConflict(null);
    reload();
  };
  const close = () => {
    if (form && !window.confirm(UNSAVED_MESSAGE)) return;
    onClose();
  };
  const words = countWords(current.body.filter((b) => b.type !== "download"));
  const publishable = !form && (lesson.has_draft_changes || lesson.status !== "published");
  return (
    <section
      aria-labelledby="lesson-editor-heading"
      className="rounded-2xl border border-sage-200 bg-white p-5"
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1.5">
          <h2 id="lesson-editor-heading" className="text-xl font-medium">
            Edit lesson: {lesson.title}
          </h2>
          <LessonState lesson={lesson} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={lesson.status} />
          <Button size="sm" variant="outline" onClick={() => setDialog("preview")}>
            Preview draft
          </Button>
          {can.view_revisions && (
            <Button size="sm" variant="outline" onClick={() => setDialog("revisions")}>
              Revisions &amp; compare
            </Button>
          )}
          {can.publish_lessons && !archived && publishable && (
            <Button size="sm" onClick={() => setDialog("publish")}>
              {lesson.live && lesson.has_draft_changes ? "Publish changes" : "Publish lesson"}
            </Button>
          )}
          {canEdit && lesson.has_draft_changes && lesson.live && !form && (
            <Button size="sm" variant="outline" onClick={discard}>
              Discard draft
            </Button>
          )}
          {can.publish_lessons && !archived && lesson.status === "published" && (
            <Button size="sm" variant="outline" onClick={unpublish}>
              Unpublish
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={close}>
            Close
          </Button>
        </div>
      </div>
      {conflict && (
        <div role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm">
          <p className="font-medium">Someone else saved this lesson after you opened it.</p>
          <p className="mt-1">
            {conflict.saved_by ? `${conflict.saved_by} saved it` : "It was saved"}
            {conflict.saved_at ? ` on ${savedAt(conflict.saved_at)}` : ""}. Your changes were not
            saved, so nothing was overwritten. Copy anything you need, then load the latest version.
          </p>
          <Button size="sm" variant="outline" className="mt-3" onClick={loadLatest}>
            Load the latest version
          </Button>
        </div>
      )}
      {!canEdit && (
        <p className="mb-4 rounded-xl bg-cream p-3 text-sm">
          You can read this draft but not change it.
        </p>
      )}
      <fieldset disabled={!canEdit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Lesson title"
            value={current.title}
            error={fieldError(error, "title")}
            onChange={(e) => set({ title: e.target.value })}
          />
          <TextField
            label="Lesson address"
            hint={
              lesson.live
                ? "Fixed after publishing (learners' links and bookmarks use it)."
                : "Part of the learner link."
            }
            value={current.slug}
            disabled={!canSlug}
            error={fieldError(error, "slug")}
            onChange={(e) => set({ slug: e.target.value })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Summary (optional)"
            value={current.summary}
            error={fieldError(error, "summary")}
            onChange={(e) => set({ summary: e.target.value })}
          />
          <TextField
            label="Estimated time (minutes)"
            hint={`Leave empty to estimate from the text (about ${readingMinutes(words)} min).`}
            type="number"
            min="1"
            value={current.estimated_minutes}
            error={fieldError(error, "estimated_minutes")}
            onChange={(e) => set({ estimated_minutes: e.target.value })}
          />
          <div className="space-y-2 pt-6">
            <CheckboxField
              label="Required for course completion"
              checked={current.completion_required}
              onChange={(e) => set({ completion_required: e.target.checked })}
            />
            <CheckboxField
              label="Free preview (anyone can read it from the course page)"
              checked={current.is_preview}
              onChange={(e) => set({ is_preview: e.target.checked })}
            />
          </div>
        </div>
        <BlockEditor
          legend="Lesson content"
          blocks={current.body}
          allowed={LESSON_BLOCKS}
          files={course.product_files}
          errors={error?.details?.body}
          onChange={(body) => set({ body })}
        />
        {lesson.assessments.length > 0 && (
          <p className="text-sm text-muted">
            Shown after this lesson: {lesson.assessments.map((a) => a.title).join(", ")} (edit in
            Assessments).
          </p>
        )}
      </fieldset>
      {canEdit && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={saving || !form || Boolean(conflict)}>
            {saving ? "Saving…" : "Save draft"}
          </Button>
          <span role="status" className="text-sm text-muted">
            {form
              ? "Unsaved changes"
              : lesson.live
                ? "Saving changes the draft only; publish to update what learners read."
                : ""}
          </span>
        </div>
      )}
      <DraftPreviewDialog
        open={dialog === "preview"}
        lesson={lesson}
        onClose={() => setDialog(null)}
      />
      {dialog === "revisions" && (
        <RevisionsDialog
          open
          course={course}
          lesson={lesson}
          onClose={() => setDialog(null)}
          onRestored={replace}
        />
      )}
      {dialog === "publish" && (
        <PublishDialog open lesson={lesson} onClose={() => setDialog(null)} onPublish={publish} />
      )}
    </section>
  );
}

/** Curriculum: modules and lessons in order, with accessible reordering. */
export function CourseContentPanel({ course, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [editing, setEditing] = useState(null); // {type: "module", id} | {type: "lesson", id}
  const [adding, setAdding] = useState(false);
  const [newLesson, setNewLesson] = useState({});
  const [confirm, setConfirm] = useState(null);
  const dirty = useRef(false);
  const onDirty = useCallback((value) => {
    dirty.current = value;
  }, []);
  const edit = (next) => {
    if (dirty.current && editing?.type === "lesson" && !window.confirm(UNSAVED_MESSAGE)) return;
    dirty.current = false;
    setEditing(next);
  };
  const canEdit = course.can.manage_curriculum && course.status !== "archived";
  const modules = course.modules;

  const apply = async (layout, message) => {
    try {
      await api.courses.reorder(course.id, layout);
      notify(message);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const moveModule = (index, delta) => {
    const next = [...modules];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    apply(layoutOf(next), `Moved “${item.title}”.`);
  };
  const moveLesson = (moduleIndex, lessonIndex, delta) => {
    const layout = layoutOf(modules);
    const ids = layout[moduleIndex].lesson_ids;
    const [id] = ids.splice(lessonIndex, 1);
    ids.splice(lessonIndex + delta, 0, id);
    apply(layout, "Lesson moved.");
  };
  const moveToModule = (moduleIndex, lessonIndex, targetId) => {
    const layout = layoutOf(modules);
    const [id] = layout[moduleIndex].lesson_ids.splice(lessonIndex, 1);
    layout.find((m) => m.module_id === Number(targetId)).lesson_ids.push(id);
    apply(layout, "Lesson moved to another module.");
  };
  const saveModule = async (body, moduleId) => {
    if (moduleId) await api.courses.updateModule(course.id, moduleId, body);
    else await api.courses.addModule(course.id, body);
    notify("Module saved.");
    setEditing(null);
    setAdding(false);
    onChanged();
  };
  const addLesson = async (moduleId) => {
    const title = (newLesson[moduleId] ?? "").trim();
    if (!title) return;
    try {
      const res = await api.courses.addLesson(course.id, moduleId, { title });
      setNewLesson({ ...newLesson, [moduleId]: "" });
      notify("Lesson added as a draft.");
      onChanged();
      setEditing({ type: "lesson", id: res.data.id });
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const remove = async () => {
    try {
      if (confirm.type === "module") await api.courses.removeModule(course.id, confirm.id);
      else await api.courses.removeLesson(course.id, confirm.id);
      notify("Deleted.");
      if (editing?.id === confirm.id) setEditing(null);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setConfirm(null);
    }
  };

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm text-muted">
        Course → modules → lessons. Learners see published lessons in this order. Lessons with
        learner progress can't be deleted (unpublish them instead).
      </p>
      {editing?.type === "lesson" && (
        <LessonEditor
          key={editing.id}
          course={course}
          lessonId={editing.id}
          onClose={() => {
            dirty.current = false;
            setEditing(null);
          }}
          onChanged={onChanged}
          onDirty={onDirty}
        />
      )}
      <ol className="space-y-4" aria-label="Modules">
        {modules.map((module, m) => (
          <li key={module.id} className="rounded-2xl border border-charcoal/10 bg-white p-4">
            {editing?.type === "module" && editing.id === module.id ? (
              <ModuleForm
                module={module}
                onSave={(body) => saveModule(body, module.id)}
                onCancel={() => setEditing(null)}
              />
            ) : (
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-medium">
                    <span className="text-sage-700">Module {m + 1}.</span> {module.title}
                  </h3>
                  {module.description && <p className="text-sm text-muted">{module.description}</p>}
                </div>
                {canEdit && (
                  <span className="flex">
                    <IconAction
                      label={`Move module ${module.title} up`}
                      icon={ArrowUp}
                      disabled={m === 0}
                      onClick={() => moveModule(m, -1)}
                    />
                    <IconAction
                      label={`Move module ${module.title} down`}
                      icon={ArrowDown}
                      disabled={m === modules.length - 1}
                      onClick={() => moveModule(m, 1)}
                    />
                    <IconAction
                      label={`Edit module ${module.title}`}
                      icon={Pencil}
                      onClick={() => edit({ type: "module", id: module.id })}
                    />
                    <IconAction
                      label={`Delete module ${module.title}`}
                      icon={Trash2}
                      onClick={() =>
                        setConfirm({ type: "module", id: module.id, title: module.title })
                      }
                    />
                  </span>
                )}
              </div>
            )}
            <ol
              className="mt-3 divide-y divide-charcoal/[0.06]"
              aria-label={`Lessons in ${module.title}`}
            >
              {module.lessons.map((lesson, l) => (
                <li
                  key={lesson.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-2"
                >
                  <button
                    type="button"
                    onClick={() => edit({ type: "lesson", id: lesson.id })}
                    className="text-left hover:underline"
                  >
                    {lesson.title}
                    {lesson.has_draft_changes && (
                      <span className="ml-2 rounded-full bg-gold-100 px-2 py-0.5 text-xs text-gold-700">
                        Unpublished changes
                      </span>
                    )}
                    <span className="ml-2 text-xs text-muted">
                      {lesson.minutes} min{lesson.is_preview ? " · free preview" : ""}
                      {!lesson.completion_required ? " · optional" : ""}
                    </span>
                  </button>
                  <span className="flex items-center gap-1">
                    <StatusBadge status={lesson.status} />
                    {canEdit && (
                      <>
                        <IconAction
                          label={`Move lesson ${lesson.title} up`}
                          icon={ArrowUp}
                          disabled={l === 0}
                          onClick={() => moveLesson(m, l, -1)}
                        />
                        <IconAction
                          label={`Move lesson ${lesson.title} down`}
                          icon={ArrowDown}
                          disabled={l === module.lessons.length - 1}
                          onClick={() => moveLesson(m, l, 1)}
                        />
                        {modules.length > 1 && (
                          <SelectField
                            label={`Move ${lesson.title} to module`}
                            className="[&_label]:sr-only"
                            value=""
                            onChange={(e) => e.target.value && moveToModule(m, l, e.target.value)}
                            options={[
                              { value: "", label: "Move to…" },
                              ...modules
                                .filter((x) => x.id !== module.id)
                                .map((x) => ({ value: String(x.id), label: x.title })),
                            ]}
                          />
                        )}
                        <IconAction
                          label={`Delete lesson ${lesson.title}`}
                          icon={Trash2}
                          onClick={() =>
                            setConfirm({ type: "lesson", id: lesson.id, title: lesson.title })
                          }
                        />
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ol>
            {canEdit && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  addLesson(module.id);
                }}
                className="mt-3 flex flex-wrap items-end gap-2"
              >
                <TextField
                  label={`New lesson in ${module.title}`}
                  value={newLesson[module.id] ?? ""}
                  onChange={(e) => setNewLesson({ ...newLesson, [module.id]: e.target.value })}
                />
                <Button
                  type="submit"
                  size="sm"
                  variant="outline"
                  disabled={!(newLesson[module.id] ?? "").trim()}
                >
                  <Plus aria-hidden /> Add lesson
                </Button>
              </form>
            )}
          </li>
        ))}
      </ol>
      {canEdit &&
        (adding ? (
          <ModuleForm onSave={(body) => saveModule(body)} onCancel={() => setAdding(false)} />
        ) : (
          <Button variant="outline" onClick={() => setAdding(true)}>
            <Plus aria-hidden /> Add module
          </Button>
        ))}
      <ConfirmDialog
        open={Boolean(confirm)}
        title={`Delete “${confirm?.title}”?`}
        message={
          confirm?.type === "module"
            ? "The module and its lessons are deleted."
            : "The lesson is deleted."
        }
        confirmLabel="Delete"
        tone="danger"
        onConfirm={remove}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

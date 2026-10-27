import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
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

function LessonEditor({ course, lessonId, onClose, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { data: lesson, setData } = useAdminQuery(
    () => api.courses.lesson(course.id, lessonId),
    [lessonId],
  );
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
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
  const canEdit = course.can.manage_curriculum && course.status !== "archived";
  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await api.courses.updateLesson(course.id, lessonId, {
        ...current,
        estimated_minutes:
          current.estimated_minutes === "" ? null : Number(current.estimated_minutes),
        body: cleanBlocks(current.body),
      });
      setData(res.data);
      setForm(null);
      notify("Lesson saved.");
      onChanged();
    } catch (err) {
      setError(err);
      notify(err.message, "error");
    } finally {
      setSaving(false);
    }
  };
  const setStatus = async (status) => {
    try {
      const res = await api.courses.lessonStatus(course.id, lessonId, status);
      setData(res.data);
      notify(status === "published" ? "Lesson published." : "Lesson moved back to draft.");
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  const words = countWords(current.body.filter((b) => b.type !== "download"));
  return (
    <section
      aria-labelledby="lesson-editor-heading"
      className="rounded-2xl border border-sage-200 bg-white p-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 id="lesson-editor-heading" className="text-xl font-medium">
          Edit lesson: {lesson.title}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={lesson.status} />
          {course.can.publish && lesson.status === "draft" && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setStatus("published")}
              disabled={Boolean(form)}
            >
              Publish lesson
            </Button>
          )}
          {course.can.publish && lesson.status === "published" && (
            <Button size="sm" variant="outline" onClick={() => setStatus("draft")}>
              Unpublish
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
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
            hint="Part of the learner link."
            value={current.slug}
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
        <div className="mt-4 flex items-center gap-3">
          <Button onClick={save} disabled={saving || !form}>
            {saving ? "Saving…" : "Save lesson"}
          </Button>
          {form && <span className="text-sm text-muted">Unsaved changes</span>}
        </div>
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
          onClose={() => setEditing(null)}
          onChanged={onChanged}
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
                      onClick={() => setEditing({ type: "module", id: module.id })}
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
                    onClick={() => setEditing({ type: "lesson", id: lesson.id })}
                    className="text-left hover:underline"
                  >
                    {lesson.title}
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

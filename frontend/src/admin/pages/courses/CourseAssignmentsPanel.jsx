import { ArrowDown, ArrowUp, Eye, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { AssignmentBrief } from "@/components/courses/AssignmentBrief";
import { ASSIGNMENT_KIND_LABEL } from "@/components/courses/assignmentLabels";
import { Button } from "@/components/ui/Button";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { formatDateTimeLocal } from "@/utils/datetime";
import { useAdminApi } from "../../adminApiContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { fieldError } from "../../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import {
  ASSIGNMENT_KINDS,
  assignmentPayload,
  assignmentToForm,
  nextPromptKey,
} from "./assignmentForm";
import { RubricBuilder } from "./RubricBuilder";

function lessonOptions(course) {
  return [
    { value: "", label: "Course-level (listed with the course)" },
    ...course.modules.flatMap((m) =>
      m.lessons.map((l) => ({ value: String(l.id), label: `${m.title} → ${l.title}` })),
    ),
  ];
}

function AssignmentEditor({ course, assignment, canManage, onChanged, onClose }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const [current, setCurrent] = useState(assignment);
  const [form, setForm] = useState(() => assignmentToForm(assignment));
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(false);
  const [confirm, setConfirm] = useState(null);
  useUnsavedChanges(dirty);
  const editable = canManage && course.status !== "archived";
  const set = (patch) => {
    setForm((f) => ({ ...f, ...patch }));
    setDirty(true);
  };
  const setPrompt = (index, patch) =>
    set({ prompts: form.prompts.map((p, i) => (i === index ? { ...p, ...patch } : p)) });
  const movePrompt = (index, delta) => {
    const next = [...form.prompts];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    set({ prompts: next });
  };
  const replace = (data) => {
    setCurrent(data);
    setForm(assignmentToForm(data));
    setDirty(false);
    onChanged();
  };
  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await api.assignments.update(
        course.id,
        current.id,
        assignmentPayload(form, current.lock_version),
      );
      replace(res.data);
      notify("Assignment saved.");
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };
  const setStatus = async (status) => {
    setError(null);
    try {
      const res = await api.assignments.setStatus(course.id, current.id, status);
      replace(res.data);
      notify(
        status === "published"
          ? "Assignment published."
          : status === "archived"
            ? "Assignment archived."
            : "Assignment moved back to draft.",
      );
    } catch (err) {
      setError(err);
    } finally {
      setConfirm(null);
    }
  };
  const remove = async () => {
    try {
      await api.assignments.remove(course.id, current.id);
      notify("Assignment deleted.");
      setDirty(false);
      onChanged();
      onClose();
    } catch (err) {
      notify(err.message, "error");
      setConfirm(null);
    }
  };
  const err = (name) => fieldError(error, name);
  const previewData = {
    ...current,
    ...assignmentPayload(form, current.lock_version),
    rubric: current.rubric,
  };

  return (
    <section
      aria-labelledby="assignment-editor"
      className="space-y-6 rounded-2xl border border-sage-200 bg-white p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="assignment-editor" className="text-xl font-medium">
          {ASSIGNMENT_KIND_LABEL[current.kind]}: {current.title}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={current.status} />
          <Button size="sm" variant="outline" onClick={() => setPreview(true)}>
            <Eye aria-hidden /> Preview as learner
          </Button>
          {editable && current.status !== "published" && (
            <Button size="sm" onClick={() => setStatus("published")}>
              {current.status === "archived" ? "Restore & publish" : "Publish"}
            </Button>
          )}
          {editable && current.status === "published" && (
            <Button size="sm" variant="outline" onClick={() => setStatus("draft")}>
              Unpublish
            </Button>
          )}
          {editable && current.status !== "archived" && (
            <Button size="sm" variant="outline" onClick={() => setConfirm("archive")}>
              Archive
            </Button>
          )}
          {editable && !current.published_at && (
            <Button size="sm" variant="outline" onClick={() => setConfirm("delete")}>
              <Trash2 aria-hidden /> Delete
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
      <form onSubmit={save} className="space-y-6" noValidate>
        <ErrorSummary error={error} />
        <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-2">
          <legend className="sr-only">Assignment details</legend>
          <TextField
            label="Title"
            required
            value={form.title}
            error={err("title")}
            onChange={(e) => set({ title: e.target.value })}
          />
          <SelectField
            label="Type"
            value={form.kind}
            error={err("kind")}
            onChange={(e) => set({ kind: e.target.value })}
            options={ASSIGNMENT_KINDS}
          />
          <SelectField
            label="Shown with"
            value={form.lesson_id}
            error={err("lesson_id")}
            onChange={(e) => set({ lesson_id: e.target.value })}
            options={lessonOptions(course)}
          />
          <CheckboxField
            className="pt-6"
            label="Required for course completion"
            hint="Needs a released, passing grade."
            checked={form.required}
            onChange={(e) => set({ required: e.target.checked })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Instructions"
            hint="Plain text. Describe the task, the case or the project brief."
            rows={6}
            value={form.instructions}
            error={err("instructions")}
            onChange={(e) => set({ instructions: e.target.value })}
          />
        </fieldset>

        <fieldset disabled={!editable} className="space-y-3">
          <legend className="text-lg font-medium">Prompts the learner answers</legend>
          {err("prompts") && <p className="text-sm text-red-800">{err("prompts")}</p>}
          <ol className="space-y-3">
            {form.prompts.map((p, i) => (
              <li
                key={p.key}
                className="grid gap-2 rounded-xl bg-cream/60 p-3 sm:grid-cols-[1fr_9rem_auto]"
              >
                <TextAreaField
                  label={`Prompt ${i + 1}`}
                  rows={2}
                  value={p.text}
                  onChange={(e) => setPrompt(i, { text: e.target.value })}
                />
                <TextField
                  label={`Prompt ${i + 1} minimum words`}
                  type="number"
                  min="1"
                  value={p.min_words}
                  onChange={(e) => setPrompt(i, { min_words: e.target.value })}
                />
                {editable && (
                  <span className="flex items-end">
                    <button
                      type="button"
                      aria-label={`Move prompt ${i + 1} up`}
                      disabled={i === 0}
                      onClick={() => movePrompt(i, -1)}
                      className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                    >
                      <ArrowUp aria-hidden className="size-4" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Move prompt ${i + 1} down`}
                      disabled={i === form.prompts.length - 1}
                      onClick={() => movePrompt(i, 1)}
                      className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                    >
                      <ArrowDown aria-hidden className="size-4" />
                    </button>
                    {form.prompts.length > 1 && (
                      <button
                        type="button"
                        aria-label={`Remove prompt ${i + 1}`}
                        onClick={() => set({ prompts: form.prompts.filter((_, j) => j !== i) })}
                        className="rounded p-1.5 text-muted hover:text-red-800"
                      >
                        <Trash2 aria-hidden className="size-4" />
                      </button>
                    )}
                  </span>
                )}
              </li>
            ))}
          </ol>
          {editable && form.prompts.length < 10 && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                set({
                  prompts: [...form.prompts, { key: nextPromptKey(), text: "", min_words: "" }],
                })
              }
            >
              <Plus aria-hidden /> Add prompt
            </Button>
          )}
        </fieldset>

        <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-4">
          <legend className="mb-2 text-lg font-medium sm:col-span-4">
            Submission requirements
          </legend>
          {err("requirements") && (
            <p className="text-sm text-red-800 sm:col-span-4">{err("requirements")}</p>
          )}
          <TextField
            label="Minimum words (total)"
            type="number"
            min="1"
            value={form.min_words}
            onChange={(e) => set({ min_words: e.target.value })}
          />
          <TextField
            label="Maximum words (total)"
            type="number"
            min="1"
            value={form.max_words}
            onChange={(e) => set({ max_words: e.target.value })}
          />
          <SelectField
            label="Supporting documents"
            hint="PDF or Word (.docx) only."
            value={form.files}
            onChange={(e) => set({ files: e.target.value })}
            options={[
              { value: "none", label: "Not accepted" },
              { value: "optional", label: "Optional" },
              { value: "required", label: "Required" },
            ]}
          />
          {form.files !== "none" && (
            <TextField
              label="Maximum files"
              type="number"
              min="1"
              value={form.max_files}
              onChange={(e) => set({ max_files: e.target.value })}
            />
          )}
        </fieldset>

        <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-3">
          <legend className="mb-2 text-lg font-medium sm:col-span-3">
            Deadlines, attempts and grading
          </legend>
          <TextField
            label="Opens (optional)"
            hint="Your local time."
            type="datetime-local"
            value={form.available_from}
            error={err("available_from")}
            onChange={(e) => set({ available_from: e.target.value })}
          />
          <TextField
            label="Deadline (optional)"
            hint="Your local time."
            type="datetime-local"
            value={form.due_at}
            error={err("due_at")}
            onChange={(e) => set({ due_at: e.target.value })}
          />
          <SelectField
            label="After the deadline"
            value={form.late_policy}
            onChange={(e) => set({ late_policy: e.target.value })}
            options={[
              { value: "block", label: "Refuse late submissions" },
              { value: "allow", label: "Accept and mark late" },
            ]}
          />
          <TextField
            label="Attempts allowed"
            hint="Empty for unlimited (at most 20)."
            type="number"
            min="1"
            max="20"
            value={form.max_attempts}
            error={err("max_attempts")}
            onChange={(e) => set({ max_attempts: e.target.value })}
          />
          <SelectField
            label="Resubmission"
            value={form.resubmission_policy}
            onChange={(e) => set({ resubmission_policy: e.target.value })}
            options={[
              { value: "none", label: "Not allowed" },
              { value: "on_request", label: "When the reviewer requests changes" },
              { value: "always", label: "Always (until attempts run out)" },
            ]}
          />
          <TextField
            label="Pass/fail passing percentage"
            hint="Used only when there's no rubric."
            type="number"
            min="0"
            max="100"
            value={form.passing_percent}
            error={err("passing_percent")}
            onChange={(e) => set({ passing_percent: e.target.value })}
          />
        </fieldset>
        {editable && (
          <div className="sticky bottom-0 -mx-1 flex items-center gap-3 border-t border-charcoal/10 bg-white/95 p-3">
            <Button type="submit" disabled={saving || !dirty}>
              {saving ? "Saving…" : "Save assignment"}
            </Button>
            <span aria-live="polite" className="text-sm text-muted">
              {dirty ? "Unsaved changes" : "All changes saved"}
            </span>
          </div>
        )}
      </form>
      <RubricBuilder
        courseId={course.id}
        assignment={current}
        canEdit={editable}
        canSeeSubmissions={can("assignments.view_submissions")}
        onSaved={(data) => {
          setCurrent(data);
          onChanged();
        }}
      />
      <Modal
        open={preview}
        onClose={() => setPreview(false)}
        title="Learner preview"
        size="lg"
        footer={
          <Button variant="outline" onClick={() => setPreview(false)}>
            Close preview
          </Button>
        }
      >
        <AssignmentBrief assignment={previewData} headingLevel={3} />
        <ol className="mt-5 space-y-3">
          {previewData.prompts.map((p, i) => (
            <li key={p.id ?? i} className="rounded-xl border border-charcoal/10 p-3">
              <p className="font-medium">
                {i + 1}. {p.text}
              </p>
              {p.min_words && <p className="text-sm text-muted">At least {p.min_words} words.</p>}
            </li>
          ))}
        </ol>
      </Modal>
      <ConfirmDialog
        open={confirm === "archive"}
        title="Archive this assignment?"
        message="Learners no longer see it. Submissions and grades are kept."
        confirmLabel="Archive"
        onConfirm={() => setStatus("archived")}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "delete"}
        title="Delete this draft assignment?"
        message="It has never been published, so nothing learners wrote is lost."
        confirmLabel="Delete"
        tone="danger"
        onConfirm={remove}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}

function AssessorsSection({ course, canManage }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const assessors = useAdminQuery(() => api.assignments.assessors(course.id), [course.id]);
  const users = useAdminQuery(
    () =>
      canManage && can("users.view")
        ? api.users.list({ page_size: 100 })
        : Promise.resolve({ data: [] }),
    [canManage],
  );
  const [adding, setAdding] = useState("");
  const [error, setError] = useState(null);
  const current = assessors.data ?? [];
  const save = async (ids) => {
    setError(null);
    try {
      const res = await api.assignments.setAssessors(course.id, ids);
      assessors.setData(res.data);
      notify("Course assessors updated.");
      setAdding("");
    } catch (err) {
      setError(err);
    }
  };
  const candidates = (users.data ?? []).filter((u) => !current.some((a) => a.user_id === u.id));
  return (
    <section aria-labelledby="assessors-heading" className="rounded-2xl bg-cream/60 p-4">
      <h2 id="assessors-heading" className="font-medium">
        Course assessors
      </h2>
      <p className="mt-1 text-sm text-muted">
        Assessors review and grade this course&apos;s submissions. Staff who manage assignments can
        always review.
      </p>
      {assessors.loading && !assessors.data ? (
        <p role="status" className="mt-2 text-sm">
          Loading assessors…
        </p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-2">
          {current.length === 0 && <li className="text-sm text-muted">None assigned.</li>}
          {current.map((a) => (
            <li
              key={a.user_id}
              className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-1 text-sm"
            >
              {a.name || a.email}
              {canManage && (
                <button
                  type="button"
                  aria-label={`Remove ${a.name || a.email} as assessor`}
                  onClick={() =>
                    save(current.filter((x) => x.user_id !== a.user_id).map((x) => x.user_id))
                  }
                  className="rounded p-0.5 text-muted hover:text-red-800"
                >
                  <Trash2 aria-hidden className="size-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canManage && candidates.length > 0 && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <SelectField
            label="Add an assessor"
            value={adding}
            onChange={(e) => setAdding(e.target.value)}
            options={[
              { value: "", label: "Choose a staff member" },
              ...candidates.map((u) => ({
                value: String(u.id),
                label: `${u.display_name} (${u.email})`,
              })),
            ]}
          />
          <Button
            size="sm"
            disabled={!adding}
            onClick={() => save([...current.map((a) => a.user_id), Number(adding)])}
          >
            Add
          </Button>
        </div>
      )}
      <ErrorSummary error={error} className="mt-3" />
    </section>
  );
}

/** Written assignments, case studies and projects for one course (Batch 09.2). */
export function CourseAssignmentsPanel({ course }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const canManage = can("assignments.manage") && course.status !== "archived";
  const { data, error, loading, reload } = useAdminQuery(
    () => api.assignments.list(course.id),
    [course.id],
  );
  const [open, setOpen] = useState(null);
  const [form, setForm] = useState({ title: "", kind: "written", lesson_id: "" });
  const [createError, setCreateError] = useState(null);
  const lessonTitle = Object.fromEntries(
    course.modules.flatMap((m) => m.lessons.map((l) => [l.id, l.title])),
  );
  const create = async (event) => {
    event.preventDefault();
    setCreateError(null);
    try {
      const res = await api.assignments.create(course.id, {
        title: form.title,
        kind: form.kind,
        lesson_id: form.lesson_id ? Number(form.lesson_id) : null,
      });
      setForm({ title: "", kind: "written", lesson_id: "" });
      notify("Assignment created as a draft. Add prompts and a rubric, then publish it.");
      await reload();
      setOpen(res.data.id);
    } catch (err) {
      setCreateError(err);
    }
  };
  if (error) return <ErrorSummary error={error} title="We couldn't load the assignments" />;
  const items = data ?? [];
  const selected = items.find((a) => a.id === open);
  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm text-muted">
        Written assignments, case studies and practical projects are reviewed by people, using a
        rubric or pass/fail. Learners only see grades and feedback after they are released.
      </p>
      {selected && (
        <AssignmentEditor
          key={selected.id}
          course={course}
          assignment={selected}
          canManage={canManage}
          onChanged={reload}
          onClose={() => setOpen(null)}
        />
      )}
      {loading && !data ? (
        <p role="status">Loading assignments…</p>
      ) : (
        <ol
          aria-label="Assignments"
          className="divide-y divide-charcoal/10 rounded-2xl border border-charcoal/10 bg-white"
        >
          {items.length === 0 && <li className="p-4 text-sm text-muted">No assignments yet.</li>}
          {items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <button
                type="button"
                className="text-left hover:underline"
                onClick={() => setOpen(a.id)}
              >
                <span className="font-medium">{a.title}</span>
                <span className="block text-xs text-muted">
                  {ASSIGNMENT_KIND_LABEL[a.kind]} ·{" "}
                  {a.lesson_id ? `with “${lessonTitle[a.lesson_id] ?? "lesson"}”` : "course-level"}
                  {a.required ? " · required" : " · optional"}
                  {a.due_at ? ` · due ${formatDateTimeLocal(a.due_at)}` : ""}
                  {a.rubric ? ` · rubric v${a.rubric.version}` : " · no rubric"}
                </span>
              </button>
              <StatusBadge status={a.status} />
            </li>
          ))}
        </ol>
      )}
      {canManage && (
        <form
          onSubmit={create}
          className="grid gap-3 rounded-2xl bg-cream/60 p-4 sm:grid-cols-[1fr_12rem_16rem_auto] sm:items-end"
        >
          <TextField
            label="New assignment"
            value={form.title}
            error={fieldError(createError, "title")}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <SelectField
            label="Type"
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
            options={ASSIGNMENT_KINDS}
          />
          <SelectField
            label="Shown with"
            value={form.lesson_id}
            onChange={(e) => setForm({ ...form, lesson_id: e.target.value })}
            options={lessonOptions(course)}
          />
          <Button type="submit" disabled={!form.title.trim()}>
            <Plus aria-hidden /> Create
          </Button>
        </form>
      )}
      <AssessorsSection course={course} canManage={can("assignments.manage")} />
    </div>
  );
}

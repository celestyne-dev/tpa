import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../../adminApiContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { fieldError } from "../../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../../components/Fields";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { ASSESSMENT_KINDS, QUESTION_KINDS, newQuestion } from "./courseAdmin";
import { practicePayload } from "./assignmentForm";

const KIND_LABEL = { quiz: "Quiz", reflection: "Reflection", self_assessment: "Self-assessment" };

function lessonOptions(course) {
  return [
    { value: "", label: "After all modules (course-level)" },
    ...course.modules.flatMap((m) =>
      m.lessons.map((l) => ({ value: String(l.id), label: `${m.title} → ${l.title}` })),
    ),
  ];
}

/**
 * Edits one question (assessment or question-bank question). `kinds` lists the allowed
 * question types; `withTags` adds the bank's tag field. Answer keys are only shown and sent
 * when `keyVisible` (the API hides them from roles that can't manage them).
 */
export function QuestionEditor({ kinds, question, onSave, onCancel, keyVisible, withTags }) {
  const [form, setForm] = useState(() => ({
    ...(question
      ? {
          kind: question.kind,
          prompt: question.prompt,
          help_text: question.help_text,
          options: question.options,
          correct: question.correct ?? [],
          explanation: question.explanation ?? "",
          settings: question.settings,
          points: question.points,
          required: question.required,
        }
      : newQuestion(kinds[0].value)),
    ...(withTags && { tags: (question?.tags ?? []).join(", ") }),
  }));
  const [error, setError] = useState(null);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const choice = form.kind === "single_choice" || form.kind === "multiple_select";
  const graded = choice || form.kind === "true_false";
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      const body = { ...form };
      if (withTags) {
        body.tags = form.tags
          .split(",")
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean);
      }
      if (!keyVisible) {
        delete body.correct;
        delete body.explanation;
      }
      await onSave(body);
    } catch (err) {
      setError(err);
    }
  };
  const toggleCorrect = (id, checked) => {
    if (form.kind === "single_choice") set({ correct: checked ? [id] : [] });
    else set({ correct: checked ? [...form.correct, id] : form.correct.filter((c) => c !== id) });
  };
  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl bg-cream/60 p-4">
      {!question && (
        <SelectField
          label="Question type"
          value={form.kind}
          onChange={(e) =>
            setForm({ ...newQuestion(e.target.value), ...(withTags && { tags: form.tags }) })
          }
          options={kinds}
        />
      )}
      <TextAreaField
        label="Question"
        required
        value={form.prompt}
        error={fieldError(error, "prompt")}
        onChange={(e) => set({ prompt: e.target.value })}
      />
      <TextField
        label="Help text (optional)"
        value={form.help_text ?? ""}
        onChange={(e) => set({ help_text: e.target.value })}
      />
      {choice && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">
            Options {keyVisible && "(tick the correct answer)"}
          </legend>
          {form.options.map((option, i) => (
            <div key={option.id} className="flex items-end gap-2">
              {keyVisible && (
                <CheckboxField
                  label={<span className="sr-only">Option {i + 1} is correct</span>}
                  checked={form.correct.includes(option.id)}
                  onChange={(e) => toggleCorrect(option.id, e.target.checked)}
                />
              )}
              <TextField
                className="flex-1"
                label={`Option ${i + 1}`}
                value={option.text}
                onChange={(e) =>
                  set({
                    options: form.options.map((o) =>
                      o.id === option.id ? { ...o, text: e.target.value } : o,
                    ),
                  })
                }
              />
              {form.options.length > 2 && (
                <button
                  type="button"
                  aria-label={`Remove option ${i + 1}`}
                  className="mb-1 rounded p-2 text-muted hover:text-red-800"
                  onClick={() =>
                    set({
                      options: form.options.filter((o) => o.id !== option.id),
                      correct: form.correct.filter((c) => c !== option.id),
                    })
                  }
                >
                  <Trash2 aria-hidden className="size-4" />
                </button>
              )}
            </div>
          ))}
          {form.options.length < 10 && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                const used = new Set(form.options.map((o) => o.id));
                const id = "abcdefghij".split("").find((c) => !used.has(c));
                set({ options: [...form.options, { id, text: "" }] });
              }}
            >
              <Plus aria-hidden /> Add option
            </Button>
          )}
          {fieldError(error, "options") && (
            <p className="text-sm text-red-800">{fieldError(error, "options")}</p>
          )}
          {fieldError(error, "correct") && (
            <p className="text-sm text-red-800">{fieldError(error, "correct")}</p>
          )}
        </fieldset>
      )}
      {form.kind === "true_false" && keyVisible && (
        <SelectField
          label="The statement is"
          value={form.correct[0] ?? "true"}
          onChange={(e) => set({ correct: [e.target.value] })}
          options={[
            { value: "true", label: "True" },
            { value: "false", label: "False" },
          ]}
        />
      )}
      {form.kind === "rating" && (
        <div className="grid gap-3 sm:grid-cols-3">
          <TextField
            label="Scale (3–10)"
            type="number"
            min="3"
            max="10"
            value={form.settings.scale}
            onChange={(e) => set({ settings: { ...form.settings, scale: Number(e.target.value) } })}
          />
          <TextField
            label="Low end label"
            value={form.settings.min_label}
            onChange={(e) => set({ settings: { ...form.settings, min_label: e.target.value } })}
          />
          <TextField
            label="High end label"
            value={form.settings.max_label}
            onChange={(e) => set({ settings: { ...form.settings, max_label: e.target.value } })}
          />
        </div>
      )}
      {form.kind === "short_text" && (
        <p className="text-sm text-muted">
          Written answers are saved for the learner and never marked right or wrong.
        </p>
      )}
      {graded && keyVisible && (
        <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
          <TextAreaField
            label="Explanation (shown after submitting, per the reveal setting)"
            value={form.explanation}
            onChange={(e) => set({ explanation: e.target.value })}
          />
          <TextField
            label="Points"
            type="number"
            min="0"
            max="100"
            value={form.points}
            onChange={(e) => set({ points: Number(e.target.value) })}
          />
        </div>
      )}
      {withTags && (
        <TextField
          label="Tags"
          hint="Comma-separated, e.g. breathing, beginner. Practice exams can draw by tag."
          value={form.tags}
          error={fieldError(error, "tags")}
          onChange={(e) => set({ tags: e.target.value })}
        />
      )}
      <CheckboxField
        label="Answer required"
        checked={form.required}
        onChange={(e) => set({ required: e.target.checked })}
      />
      {error && !fieldError(error, "prompt") && (
        <p role="alert" className="text-sm text-red-800">
          {error.message}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!form.prompt.trim()}>
          Save question
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function AssessmentEditor({ course, assessmentId, onChanged, onClose }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { data: assessment, setData } = useAdminQuery(
    () => api.courses.assessment(course.id, assessmentId),
    [assessmentId],
  );
  const [settings, setSettings] = useState(null);
  const [editing, setEditing] = useState(null); // question id | "new"
  const [error, setError] = useState(null);
  const [confirm, setConfirm] = useState(null);
  if (!assessment) return <p role="status">Loading assessment…</p>;
  const canEdit = course.can.manage_assessments && course.status !== "archived";
  const form = settings ?? {
    title: assessment.title,
    description: assessment.description,
    lesson_id: assessment.lesson_id ? String(assessment.lesson_id) : "",
    passing_score: assessment.passing_score ?? 70,
    max_attempts: assessment.max_attempts ?? "",
    show_answers: assessment.show_answers,
    required_for_completion: assessment.required_for_completion,
    practice: assessment.practice ?? false,
    time_limit_minutes: assessment.time_limit_minutes ?? "",
    shuffle_questions: assessment.shuffle_questions ?? false,
    shuffle_options: assessment.shuffle_options ?? false,
    selection: (assessment.selection ?? []).map((r) => ({
      bank_id: r.bank_id,
      count: r.count,
      tags: (r.tags ?? []).join(", "),
    })),
  };
  const set = (patch) => setSettings({ ...form, ...patch });
  const saveSettings = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      const body = {
        title: form.title,
        description: form.description,
        lesson_id: form.lesson_id ? Number(form.lesson_id) : null,
        max_attempts: form.max_attempts === "" ? null : Number(form.max_attempts),
        show_answers: form.show_answers,
        required_for_completion: form.practice ? false : form.required_for_completion,
        ...(assessment.kind === "quiz" && {
          passing_score: Number(form.passing_score),
          ...practicePayload(form),
        }),
      };
      const res = await api.courses.updateAssessment(course.id, assessmentId, body);
      setData(res.data);
      setSettings(null);
      notify("Assessment saved.");
      onChanged();
    } catch (err) {
      setError(err);
    }
  };
  const saveQuestion = async (body, questionId) => {
    const res = questionId
      ? await api.courses.updateQuestion(course.id, assessmentId, questionId, body)
      : await api.courses.addQuestion(course.id, assessmentId, body);
    setData(res.data);
    setEditing(null);
    notify("Question saved.");
    onChanged();
  };
  const moveQuestion = async (index, delta) => {
    const ids = assessment.questions.map((q) => q.id);
    const [id] = ids.splice(index, 1);
    ids.splice(index + delta, 0, id);
    const res = await api.courses.reorderQuestions(course.id, assessmentId, ids);
    setData(res.data);
  };
  const removeQuestion = async () => {
    try {
      const res = await api.courses.removeQuestion(course.id, assessmentId, confirm);
      setData(res.data);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setConfirm(null);
    }
  };
  const setStatus = async (status) => {
    try {
      const res = await api.courses.assessmentStatus(course.id, assessmentId, status);
      setData(res.data);
      notify(status === "published" ? "Assessment published." : "Assessment moved back to draft.");
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  return (
    <section
      aria-labelledby="assessment-editor"
      className="rounded-2xl border border-sage-200 bg-white p-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 id="assessment-editor" className="text-xl font-medium">
          {KIND_LABEL[assessment.kind]}: {assessment.title}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={assessment.status} />
          {course.can.publish && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setStatus(assessment.status === "published" ? "draft" : "published")}
            >
              {assessment.status === "published" ? "Unpublish" : "Publish"}
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
      <p className="mb-4 text-sm text-muted">
        {assessment.attempt_count} learner attempt{assessment.attempt_count === 1 ? "" : "s"} so
        far.
        {!assessment.answer_key_visible && " Answer keys are hidden for your role."}
      </p>
      <form onSubmit={saveSettings}>
        <fieldset disabled={!canEdit} className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Title"
            value={form.title}
            error={fieldError(error, "title")}
            onChange={(e) => set({ title: e.target.value })}
          />
          <SelectField
            label="Shown"
            value={form.lesson_id}
            error={fieldError(error, "lesson_id")}
            onChange={(e) => set({ lesson_id: e.target.value })}
            options={lessonOptions(course)}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Instructions (optional)"
            value={form.description}
            onChange={(e) => set({ description: e.target.value })}
          />
          {assessment.kind === "quiz" && (
            <TextField
              label="Passing score (%)"
              type="number"
              min="0"
              max="100"
              value={form.passing_score}
              error={fieldError(error, "passing_score")}
              onChange={(e) => set({ passing_score: e.target.value })}
            />
          )}
          <TextField
            label="Attempts allowed"
            hint="Empty for unlimited."
            type="number"
            min="1"
            value={form.max_attempts}
            error={fieldError(error, "max_attempts")}
            onChange={(e) => set({ max_attempts: e.target.value })}
          />
          {assessment.kind === "quiz" && (
            <SelectField
              label="Reveal correct answers"
              value={form.show_answers}
              onChange={(e) => set({ show_answers: e.target.value })}
              options={[
                { value: "after_submit", label: "After each submission" },
                { value: "after_pass", label: "Only after passing" },
                { value: "never", label: "Never (score only)" },
              ]}
            />
          )}
          <CheckboxField
            className="pt-6"
            label="Required for course completion"
            hint={form.practice ? "Practice exams never count towards completion." : undefined}
            checked={!form.practice && form.required_for_completion}
            disabled={form.practice}
            onChange={(e) => set({ required_for_completion: e.target.checked })}
          />
          {assessment.kind === "quiz" && (
            <PracticeSettings form={form} set={set} error={error} disabled={!canEdit} />
          )}
          {canEdit && settings && (
            <div className="sm:col-span-2">
              <Button type="submit" size="sm">
                Save settings
              </Button>
            </div>
          )}
        </fieldset>
      </form>
      <h3 className="mt-6 font-medium">
        {assessment.selection?.length ? "Fixed questions (always included)" : "Questions"}
      </h3>
      {assessment.selection?.length > 0 && (
        <p className="mt-1 text-sm text-muted">
          Each attempt also draws {assessment.drawn_question_count} question
          {assessment.drawn_question_count === 1 ? "" : "s"} from question banks. Learners see the
          questions only after starting an attempt.
        </p>
      )}
      <ol className="mt-3 space-y-3">
        {assessment.questions.map((q, i) => (
          <li key={q.id} className="rounded-xl border border-charcoal/10 p-3">
            {editing === q.id ? (
              <QuestionEditor
                kinds={QUESTION_KINDS[assessment.kind]}
                question={q}
                keyVisible={assessment.answer_key_visible}
                onSave={(body) => saveQuestion(body, q.id)}
                onCancel={() => setEditing(null)}
              />
            ) : (
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium">
                    {i + 1}. {q.prompt}
                  </p>
                  <p className="text-xs text-muted">
                    {QUESTION_KINDS[assessment.kind].find((k) => k.value === q.kind)?.label ??
                      q.kind}
                    {q.graded
                      ? ` · ${q.points} point${q.points === 1 ? "" : "s"}`
                      : " · not scored"}
                    {!q.required && " · optional"}
                  </p>
                </div>
                {canEdit && (
                  <span className="flex">
                    <button
                      type="button"
                      aria-label={`Move question ${i + 1} up`}
                      disabled={i === 0}
                      onClick={() => moveQuestion(i, -1)}
                      className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                    >
                      <ArrowUp aria-hidden className="size-4" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Move question ${i + 1} down`}
                      disabled={i === assessment.questions.length - 1}
                      onClick={() => moveQuestion(i, 1)}
                      className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                    >
                      <ArrowDown aria-hidden className="size-4" />
                    </button>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(q.id)}>
                      Edit
                    </Button>
                    <button
                      type="button"
                      aria-label={`Delete question ${i + 1}`}
                      onClick={() => setConfirm(q.id)}
                      className="rounded p-1.5 text-muted hover:text-red-800"
                    >
                      <Trash2 aria-hidden className="size-4" />
                    </button>
                  </span>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
      {canEdit &&
        (editing === "new" ? (
          <div className="mt-3">
            <QuestionEditor
              kinds={QUESTION_KINDS[assessment.kind]}
              keyVisible={assessment.answer_key_visible}
              onSave={(body) => saveQuestion(body)}
              onCancel={() => setEditing(null)}
            />
          </div>
        ) : (
          <Button className="mt-3" size="sm" variant="outline" onClick={() => setEditing("new")}>
            <Plus aria-hidden /> Add question
          </Button>
        ))}
      <ConfirmDialog
        open={Boolean(confirm)}
        title="Delete this question?"
        message="Past attempts keep a copy of the question in their history."
        confirmLabel="Delete"
        tone="danger"
        onConfirm={removeQuestion}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}

function PracticeSettings({ form, set, error, disabled }) {
  const api = useAdminApi();
  const { can } = usePermissions();
  const canSeeBanks = can("question_banks.view");
  const banks = useAdminQuery(
    () =>
      canSeeBanks
        ? api.questionBanks.list({ status: "active", page_size: 100 })
        : Promise.resolve({ data: [] }),
    [canSeeBanks],
  );
  const setRule = (index, patch) =>
    set({ selection: form.selection.map((r, i) => (i === index ? { ...r, ...patch } : r)) });
  const bankOptions = (banks.data ?? []).map((b) => ({
    value: b.id,
    label: `${b.title} (${b.question_counts.active} active questions)`,
  }));
  return (
    <fieldset className="space-y-4 rounded-xl border border-charcoal/10 p-4 sm:col-span-2">
      <legend className="px-1 font-medium">Mode, timing and question selection</legend>
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField
          label="Mode"
          value={form.practice ? "practice" : "graded"}
          error={fieldError(error, "practice")}
          onChange={(e) => set({ practice: e.target.value === "practice" })}
          options={[
            { value: "graded", label: "Graded quiz (can count towards completion)" },
            { value: "practice", label: "Practice exam (never counts towards completion)" },
          ]}
        />
        <TextField
          label="Time limit (minutes)"
          hint="Empty for untimed. The server fixes the deadline when a learner starts."
          type="number"
          min="1"
          max="600"
          value={form.time_limit_minutes}
          error={fieldError(error, "time_limit_minutes")}
          onChange={(e) => set({ time_limit_minutes: e.target.value })}
        />
        <CheckboxField
          label="Shuffle question order for each attempt"
          checked={form.shuffle_questions}
          onChange={(e) => set({ shuffle_questions: e.target.checked })}
        />
        <CheckboxField
          label="Shuffle answer options for each attempt"
          checked={form.shuffle_options}
          onChange={(e) => set({ shuffle_options: e.target.checked })}
        />
      </div>
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">Draw questions from question banks</legend>
        {fieldError(error, "selection") && (
          <p className="text-sm text-red-800">{fieldError(error, "selection")}</p>
        )}
        {!canSeeBanks && form.selection.length > 0 && (
          <p className="text-sm text-muted">
            Your role can&apos;t list question banks; the draws are shown by bank id.
          </p>
        )}
        {form.selection.map((rule, i) => (
          <div
            key={i}
            className="grid gap-2 rounded-lg bg-cream/60 p-3 sm:grid-cols-[1fr_7rem_1fr_auto] sm:items-end"
          >
            {canSeeBanks ? (
              <SelectField
                label={`Draw ${i + 1}: question bank`}
                value={rule.bank_id}
                onChange={(e) => setRule(i, { bank_id: e.target.value })}
                options={[
                  { value: "", label: "Choose a bank" },
                  ...bankOptions,
                  ...(rule.bank_id && !bankOptions.some((o) => o.value === rule.bank_id)
                    ? [{ value: rule.bank_id, label: `${rule.bank_id} (archived or unavailable)` }]
                    : []),
                ]}
              />
            ) : (
              <TextField label={`Draw ${i + 1}: bank id`} value={rule.bank_id} readOnly />
            )}
            <TextField
              label={`Draw ${i + 1}: number of questions`}
              type="number"
              min="1"
              max="100"
              value={rule.count}
              onChange={(e) => setRule(i, { count: e.target.value })}
            />
            <TextField
              label={`Draw ${i + 1}: only these tags (optional)`}
              hint="Comma-separated; any tag matches."
              value={rule.tags}
              onChange={(e) => setRule(i, { tags: e.target.value })}
            />
            {!disabled && (
              <button
                type="button"
                aria-label={`Remove draw ${i + 1}`}
                onClick={() => set({ selection: form.selection.filter((_, j) => j !== i) })}
                className="mb-1 rounded p-2 text-muted hover:text-red-800"
              >
                <Trash2 aria-hidden className="size-4" />
              </button>
            )}
          </div>
        ))}
        {!disabled && canSeeBanks && form.selection.length < 10 && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() =>
              set({ selection: [...form.selection, { bank_id: "", count: 5, tags: "" }] })
            }
          >
            <Plus aria-hidden /> Add a draw
          </Button>
        )}
      </fieldset>
    </fieldset>
  );
}

/** Quizzes, written reflections and self-assessments for one course. */
export function CourseAssessmentsPanel({ course, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [open, setOpen] = useState(null);
  const [form, setForm] = useState({ title: "", kind: "quiz", lesson_id: "" });
  const [error, setError] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const canEdit = course.can.manage_assessments && course.status !== "archived";
  const items = course.assessments;
  const create = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      const res = await api.courses.createAssessment(course.id, {
        title: form.title,
        kind: form.kind,
        lesson_id: form.lesson_id ? Number(form.lesson_id) : null,
      });
      setForm({ title: "", kind: "quiz", lesson_id: "" });
      notify("Assessment created as a draft. Add questions, then publish it.");
      onChanged();
      setOpen(res.data.id);
    } catch (err) {
      setError(err);
    }
  };
  const move = async (index, delta) => {
    const ids = items.map((a) => a.id);
    const [id] = ids.splice(index, 1);
    ids.splice(index + delta, 0, id);
    await api.courses.reorderAssessments(course.id, ids);
    onChanged();
  };
  const remove = async () => {
    try {
      await api.courses.removeAssessment(course.id, confirm);
      if (open === confirm) setOpen(null);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setConfirm(null);
    }
  };
  const lessonTitle = Object.fromEntries(
    course.modules.flatMap((m) => m.lessons.map((l) => [l.id, l.title])),
  );
  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm text-muted">
        Quizzes are scored automatically (single choice, multiple select, true/false). Written
        reflections and self-assessments are never marked right or wrong. Correct answers are never
        sent to learners before they submit.
      </p>
      {open && (
        <AssessmentEditor
          key={open}
          course={course}
          assessmentId={open}
          onChanged={onChanged}
          onClose={() => setOpen(null)}
        />
      )}
      <ol
        className="divide-y divide-charcoal/10 rounded-2xl border border-charcoal/10 bg-white"
        aria-label="Assessments"
      >
        {items.length === 0 && <li className="p-4 text-sm text-muted">No assessments yet.</li>}
        {items.map((a, i) => (
          <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
            <button
              type="button"
              className="text-left hover:underline"
              onClick={() => setOpen(a.id)}
            >
              <span className="font-medium">{a.title}</span>
              <span className="block text-xs text-muted">
                {KIND_LABEL[a.kind]} · {a.question_count} question
                {a.question_count === 1 ? "" : "s"} ·{" "}
                {a.lesson_id ? `after “${lessonTitle[a.lesson_id] ?? "lesson"}”` : "course-level"}
                {a.practice ? " · practice exam" : a.required_for_completion ? " · required" : ""}
                {a.time_limit_minutes ? ` · ${a.time_limit_minutes} min` : ""}
                {a.drawn_question_count ? ` · ${a.drawn_question_count} drawn from banks` : ""}
              </span>
            </button>
            <span className="flex items-center gap-1">
              <StatusBadge status={a.status} />
              {canEdit && (
                <>
                  <button
                    type="button"
                    aria-label={`Move ${a.title} up`}
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                    className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                  >
                    <ArrowUp aria-hidden className="size-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={`Move ${a.title} down`}
                    disabled={i === items.length - 1}
                    onClick={() => move(i, 1)}
                    className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                  >
                    <ArrowDown aria-hidden className="size-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${a.title}`}
                    onClick={() => setConfirm(a.id)}
                    className="rounded p-1.5 text-muted hover:text-red-800"
                  >
                    <Trash2 aria-hidden className="size-4" />
                  </button>
                </>
              )}
            </span>
          </li>
        ))}
      </ol>
      {canEdit && (
        <form
          onSubmit={create}
          className="grid gap-3 rounded-2xl bg-cream/60 p-4 sm:grid-cols-[1fr_14rem_16rem_auto] sm:items-end"
        >
          <TextField
            label="New assessment"
            value={form.title}
            error={fieldError(error, "title")}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <SelectField
            label="Type"
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
            options={ASSESSMENT_KINDS}
          />
          <SelectField
            label="Shown"
            value={form.lesson_id}
            onChange={(e) => setForm({ ...form, lesson_id: e.target.value })}
            options={lessonOptions(course)}
          />
          <Button type="submit" disabled={!form.title.trim()}>
            <Plus aria-hidden /> Create
          </Button>
        </form>
      )}
      <ConfirmDialog
        open={Boolean(confirm)}
        title="Delete this assessment?"
        message="Assessments learners have attempted can't be deleted; unpublish them instead."
        confirmLabel="Delete"
        tone="danger"
        onConfirm={remove}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

import { ArrowDown, ArrowUp, History, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { CheckboxField, TextAreaField, TextField } from "../../components/Fields";
import { useNotify } from "../../components/notifyContext";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { rubricProblems } from "./assignmentForm";

// Mirrors backend assignment_admin limits.
const MAX_CRITERIA = 20;
const MAX_DESCRIPTORS = 6;
// Submissions that have been looked at or scored (their grades keep their rubric version).
const REVIEWED = new Set(["under_review", "graded", "completed", "changes_requested"]);

let keySeed = 0;
const key = () => `k${(keySeed += 1)}`;

function toForm(rubric) {
  if (!rubric) {
    return {
      criteria: [{ key: key(), title: "", description: "", max_points: 10, descriptors: [] }],
      passing_percent: 60,
      feedback_required: false,
    };
  }
  return {
    criteria: rubric.criteria.map((c) => ({
      key: key(),
      id: c.id,
      title: c.title,
      description: c.description ?? "",
      max_points: c.max_points,
      descriptors: (c.descriptors ?? []).map((d) => ({ ...d, key: key() })),
    })),
    passing_percent: rubric.passing_percent,
    feedback_required: rubric.feedback_required,
  };
}

function payload(form, lockVersion) {
  return {
    criteria: form.criteria.map((c) => ({
      ...(c.id && { id: c.id }),
      title: c.title.trim(),
      description: c.description.trim(),
      max_points: Number(c.max_points),
      descriptors: c.descriptors.map((d) => ({
        label: d.label.trim(),
        points: Number(d.points),
        description: (d.description ?? "").trim(),
      })),
    })),
    passing_percent: Number(form.passing_percent),
    feedback_required: form.feedback_required,
    lock_version: lockVersion,
  };
}

function RubricHistory({ courseId, assignmentId, current }) {
  const api = useAdminApi();
  const { data, loading, error } = useAdminQuery(
    () => api.assignments.rubrics(courseId, assignmentId),
    [assignmentId, current],
  );
  if (loading && !data) return <p role="status">Loading rubric history…</p>;
  if (error) return <p className="text-sm text-red-800">{error.message}</p>;
  if (!data?.length) return <p className="text-sm text-muted">No rubric versions yet.</p>;
  return (
    <ol className="space-y-2" aria-label="Rubric versions">
      {data.map((r) => (
        <li key={r.id} className="rounded-xl border border-charcoal/10 p-3 text-sm">
          <details>
            <summary className="cursor-pointer font-medium">
              Version {r.version}
              {r.version === current ? " (current)" : ""} · {r.total_points} points · pass at{" "}
              {r.passing_percent}% · {formatDateTime(r.created_at)}
            </summary>
            <ul className="mt-2 list-disc pl-5">
              {r.criteria.map((c) => (
                <li key={c.id}>
                  {c.title} — {c.max_points} points
                  {c.descriptors?.length
                    ? ` (${c.descriptors.map((d) => `${d.label} ${d.points}`).join(", ")})`
                    : ""}
                </li>
              ))}
            </ul>
          </details>
        </li>
      ))}
    </ol>
  );
}

/**
 * Grading criteria for one assignment. Saving always creates a new rubric version; grades
 * already given stay pinned to the version they were scored with.
 */
export function RubricBuilder({ courseId, assignment, canEdit, canSeeSubmissions, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [form, setForm] = useState(() => toForm(assignment.rubric));
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const reviewed = useAdminQuery(
    () =>
      canSeeSubmissions
        ? api.assignments.submissions(courseId, assignment.id)
        : Promise.resolve({ data: [] }),
    [assignment.id, canSeeSubmissions],
  );
  const reviewedCount = (reviewed.data ?? []).filter((s) => REVIEWED.has(s.status)).length;
  const update = (patch) => {
    setForm((f) => ({ ...f, ...patch }));
    setDirty(true);
  };
  const setCriterion = (index, patch) =>
    update({ criteria: form.criteria.map((c, i) => (i === index ? { ...c, ...patch } : c)) });
  const move = (index, delta) => {
    const next = [...form.criteria];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    update({ criteria: next });
  };
  const total = form.criteria.reduce((sum, c) => sum + (Number(c.max_points) || 0), 0);

  const save = async (event) => {
    event.preventDefault();
    const problems = rubricProblems(form);
    if (problems.length) {
      setError({ message: "The rubric needs attention.", details: { criteria: problems } });
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await api.assignments.saveRubric(
        courseId,
        assignment.id,
        payload(form, assignment.lock_version),
      );
      setForm(toForm(res.data.rubric));
      setDirty(false);
      notify(`Rubric version ${res.data.rubric.version} saved.`);
      onSaved(res.data.assignment);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section aria-labelledby="rubric-heading" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="rubric-heading" className="text-lg font-medium">
          Rubric{" "}
          {assignment.rubric ? (
            <span className="text-sm font-normal text-muted">
              (version {assignment.rubric.version})
            </span>
          ) : (
            <span className="text-sm font-normal text-muted">(none yet)</span>
          )}
        </h3>
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-expanded={showHistory}
          onClick={() => setShowHistory((v) => !v)}
        >
          <History aria-hidden /> Version history
        </Button>
      </div>
      {showHistory && (
        <RubricHistory
          courseId={courseId}
          assignmentId={assignment.id}
          current={assignment.rubric?.version}
        />
      )}
      {assignment.rubric && (
        <p role="note" className="rounded-xl bg-cream p-3 text-sm">
          Saving creates version {assignment.rubric.version + 1}. Grades already given keep the
          version they were scored with, so historical scores never change.
        </p>
      )}
      {assignment.rubric && reviewedCount > 0 && (
        <p
          role="alert"
          className="rounded-xl border border-gold-300 bg-gold-100/60 p-3 text-sm font-medium"
        >
          Warning: {reviewedCount} submission{reviewedCount === 1 ? " has" : "s have"} already been
          reviewed or graded with version {assignment.rubric.version}. New grades will use the new
          version; learners graded earlier keep their existing scores.
        </p>
      )}
      <form onSubmit={save} className="space-y-4" noValidate>
        <ErrorSummary error={error} title="The rubric needs attention" />
        <fieldset disabled={!canEdit} className="space-y-4">
          <legend className="sr-only">Grading criteria</legend>
          <ol className="space-y-4">
            {form.criteria.map((c, i) => (
              <li key={c.key} className="rounded-xl border border-charcoal/10 bg-white p-4">
                <fieldset className="space-y-3">
                  <legend className="flex w-full items-center justify-between gap-2 font-medium">
                    <span>Criterion {i + 1}</span>
                    {canEdit && (
                      <span className="flex">
                        <button
                          type="button"
                          aria-label={`Move criterion ${i + 1} up`}
                          disabled={i === 0}
                          onClick={() => move(i, -1)}
                          className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                        >
                          <ArrowUp aria-hidden className="size-4" />
                        </button>
                        <button
                          type="button"
                          aria-label={`Move criterion ${i + 1} down`}
                          disabled={i === form.criteria.length - 1}
                          onClick={() => move(i, 1)}
                          className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                        >
                          <ArrowDown aria-hidden className="size-4" />
                        </button>
                        {form.criteria.length > 1 && (
                          <button
                            type="button"
                            aria-label={`Remove criterion ${i + 1}`}
                            onClick={() =>
                              update({ criteria: form.criteria.filter((_, j) => j !== i) })
                            }
                            className="rounded p-1.5 text-muted hover:text-red-800"
                          >
                            <Trash2 aria-hidden className="size-4" />
                          </button>
                        )}
                      </span>
                    )}
                  </legend>
                  <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
                    <TextField
                      label={`Criterion ${i + 1} name`}
                      value={c.title}
                      maxLength={160}
                      onChange={(e) => setCriterion(i, { title: e.target.value })}
                    />
                    <TextField
                      label={`Criterion ${i + 1} maximum points`}
                      type="number"
                      min="1"
                      max="100"
                      value={c.max_points}
                      onChange={(e) => setCriterion(i, { max_points: e.target.value })}
                    />
                  </div>
                  <TextAreaField
                    label={`Criterion ${i + 1} description`}
                    rows={2}
                    value={c.description}
                    maxLength={1000}
                    onChange={(e) => setCriterion(i, { description: e.target.value })}
                  />
                  <fieldset className="space-y-2">
                    <legend className="text-sm font-medium">Performance descriptors</legend>
                    {c.descriptors.map((d, j) => (
                      <div
                        key={d.key}
                        className="grid gap-2 rounded-lg bg-cream/60 p-2 sm:grid-cols-[10rem_6rem_1fr_auto] sm:items-end"
                      >
                        <TextField
                          label={`Descriptor ${j + 1} label`}
                          value={d.label}
                          maxLength={80}
                          onChange={(e) =>
                            setCriterion(i, {
                              descriptors: c.descriptors.map((x, k) =>
                                k === j ? { ...x, label: e.target.value } : x,
                              ),
                            })
                          }
                        />
                        <TextField
                          label={`Descriptor ${j + 1} points`}
                          type="number"
                          min="0"
                          max={c.max_points}
                          value={d.points}
                          onChange={(e) =>
                            setCriterion(i, {
                              descriptors: c.descriptors.map((x, k) =>
                                k === j ? { ...x, points: e.target.value } : x,
                              ),
                            })
                          }
                        />
                        <TextField
                          label={`Descriptor ${j + 1} description`}
                          value={d.description ?? ""}
                          maxLength={500}
                          onChange={(e) =>
                            setCriterion(i, {
                              descriptors: c.descriptors.map((x, k) =>
                                k === j ? { ...x, description: e.target.value } : x,
                              ),
                            })
                          }
                        />
                        {canEdit && (
                          <button
                            type="button"
                            aria-label={`Remove descriptor ${j + 1} of criterion ${i + 1}`}
                            onClick={() =>
                              setCriterion(i, {
                                descriptors: c.descriptors.filter((_, k) => k !== j),
                              })
                            }
                            className="mb-1 rounded p-2 text-muted hover:text-red-800"
                          >
                            <Trash2 aria-hidden className="size-4" />
                          </button>
                        )}
                      </div>
                    ))}
                    {canEdit && c.descriptors.length < MAX_DESCRIPTORS && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setCriterion(i, {
                            descriptors: [
                              ...c.descriptors,
                              { key: key(), label: "", points: 0, description: "" },
                            ],
                          })
                        }
                      >
                        <Plus aria-hidden /> Add descriptor
                      </Button>
                    )}
                  </fieldset>
                </fieldset>
              </li>
            ))}
          </ol>
          {canEdit && form.criteria.length < MAX_CRITERIA && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                update({
                  criteria: [
                    ...form.criteria,
                    { key: key(), title: "", description: "", max_points: 10, descriptors: [] },
                  ],
                })
              }
            >
              <Plus aria-hidden /> Add criterion
            </Button>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Overall passing requirement (%)"
              hint={`Total available: ${total} points.`}
              type="number"
              min="0"
              max="100"
              value={form.passing_percent}
              onChange={(e) => update({ passing_percent: e.target.value })}
            />
            <CheckboxField
              className="pt-6"
              label="Written feedback required before releasing a grade"
              checked={form.feedback_required}
              onChange={(e) => update({ feedback_required: e.target.checked })}
            />
          </div>
          {canEdit && (
            <Button type="submit" size="sm" disabled={saving || !dirty}>
              {saving ? "Saving…" : assignment.rubric ? "Save as new version" : "Save rubric"}
            </Button>
          )}
        </fieldset>
      </form>
    </section>
  );
}

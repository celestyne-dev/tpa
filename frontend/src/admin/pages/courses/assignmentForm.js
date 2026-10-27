import { ASSIGNMENT_KIND_LABEL } from "@/components/courses/assignmentLabels";
import { fromLocalInput, toLocalInput } from "@/utils/datetime";

/** Form helpers for Batch 09.2 assignments, rubrics and practice exams (admin). */

export const ASSIGNMENT_KINDS = Object.entries(ASSIGNMENT_KIND_LABEL).map(([value, label]) => ({
  value,
  label,
}));

let promptKey = 0;
export const nextPromptKey = () => `p${(promptKey += 1)}`;

export function assignmentToForm(a) {
  const req = a.requirements ?? {};
  return {
    title: a.title,
    kind: a.kind,
    lesson_id: a.lesson_id ? String(a.lesson_id) : "",
    instructions: a.instructions ?? "",
    prompts: (a.prompts ?? []).map((p) => ({
      key: nextPromptKey(),
      id: p.id,
      text: p.text,
      min_words: p.min_words ?? "",
    })),
    min_words: req.min_words ?? "",
    max_words: req.max_words ?? "",
    files: req.files ?? "optional",
    max_files: req.max_files ?? "",
    required: a.required,
    passing_percent: a.passing_percent ?? "",
    max_attempts: a.max_attempts ?? "",
    resubmission_policy: a.resubmission_policy,
    available_from: toLocalInput(a.available_from),
    due_at: toLocalInput(a.due_at),
    late_policy: a.late_policy,
  };
}

/** The request body the API expects (assignment_admin.FIELDS). */
export function assignmentPayload(form, lockVersion) {
  const num = (v) => (v === "" || v == null ? null : Number(v));
  return {
    title: form.title,
    kind: form.kind,
    lesson_id: num(form.lesson_id),
    instructions: form.instructions,
    prompts: form.prompts.map((p) => ({
      ...(p.id && { id: p.id }),
      text: p.text,
      ...(p.min_words !== "" && { min_words: Number(p.min_words) }),
    })),
    requirements: {
      min_words: num(form.min_words),
      max_words: num(form.max_words),
      files: form.files,
      max_files: form.files === "none" ? null : num(form.max_files),
    },
    required: form.required,
    passing_percent: num(form.passing_percent),
    max_attempts: num(form.max_attempts),
    resubmission_policy: form.resubmission_policy,
    available_from: fromLocalInput(form.available_from),
    due_at: fromLocalInput(form.due_at),
    late_policy: form.late_policy,
    lock_version: lockVersion,
  };
}

/** Client-side checks mirroring the API, so problems are listed before saving. */
export function rubricProblems(form) {
  const problems = [];
  if (!form.criteria.length) problems.push("Add at least one criterion.");
  form.criteria.forEach((c, i) => {
    const label = `Criterion ${i + 1}`;
    if (!c.title.trim()) problems.push(`${label}: add a name.`);
    const max = Number(c.max_points);
    if (!Number.isInteger(max) || max < 1 || max > 100)
      problems.push(`${label}: maximum points must be 1 to 100.`);
    c.descriptors.forEach((d, j) => {
      const points = Number(d.points);
      if (!d.label.trim()) problems.push(`${label}, descriptor ${j + 1}: add a label.`);
      if (!Number.isInteger(points) || points < 0 || points > max)
        problems.push(`${label}, descriptor ${j + 1}: points must be 0 to ${max}.`);
    });
  });
  const pass = Number(form.passing_percent);
  if (!Number.isInteger(pass) || pass < 0 || pass > 100)
    problems.push("Passing requirement: use a percentage from 0 to 100.");
  return problems;
}

/** The practice/timed/draw fields the API accepts for quizzes (Batch 09.2). */
export function practicePayload(form) {
  return {
    practice: form.practice,
    time_limit_minutes: form.time_limit_minutes === "" ? null : Number(form.time_limit_minutes),
    shuffle_questions: form.shuffle_questions,
    shuffle_options: form.shuffle_options,
    selection: form.selection.map((r) => ({
      bank_id: r.bank_id,
      count: Number(r.count),
      tags: r.tags
        .split(",")
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean),
    })),
  };
}

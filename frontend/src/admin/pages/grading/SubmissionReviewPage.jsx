import { Download, FileText } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
import {
  ASSIGNMENT_KIND_LABEL,
  SUBMISSION_STATUS_LABEL,
} from "@/components/courses/assignmentLabels";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { formatDateTimeLocal } from "@/utils/datetime";
import { formatBytes } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { SelectField, TextAreaField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";

const GRADE_STATUS = {
  draft: "Draft — not visible to the learner",
  published: "Released to the learner",
  retracted: "Retracted — not visible to the learner",
};

function Responses({ assignment, attempt, fileUrl }) {
  const prompts = assignment.prompts ?? [];
  const extra = Object.keys(attempt.responses ?? {}).filter(
    (id) => !prompts.some((p) => p.id === id),
  );
  return (
    <div className="space-y-4">
      {[...prompts, ...extra.map((id) => ({ id, text: "Earlier prompt" }))].map((p) => (
        <section key={p.id} className="rounded-xl border border-charcoal/10 bg-white p-4">
          <h4 className="font-medium">{p.text}</h4>
          <p className="mt-2 leading-relaxed whitespace-pre-wrap">
            {attempt.responses?.[p.id] || <span className="text-muted">(no answer)</span>}
          </p>
        </section>
      ))}
      <p className="text-sm text-muted">
        {attempt.word_count} words · submitted {formatDateTimeLocal(attempt.submitted_at)}
        {attempt.is_late && " · late"}
      </p>
      {attempt.files?.length > 0 && (
        <ul aria-label="Supporting documents" className="space-y-2">
          {attempt.files.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center gap-2 text-sm">
              <FileText aria-hidden className="size-4 text-sage-700" />
              <a
                href={fileUrl(f.id)}
                className="font-medium text-sage-800 underline underline-offset-4"
              >
                <Download aria-hidden className="mr-1 inline size-4" />
                {f.filename}
              </a>
              <span className="text-muted">
                {f.format.toUpperCase()} · {formatBytes(f.size_bytes)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function gradeForm(grade) {
  return {
    scores: Object.fromEntries(Object.entries(grade?.scores ?? {}).map(([k, v]) => [k, String(v)])),
    passed: grade?.passed == null ? "" : String(grade.passed),
    feedback: grade?.feedback ?? "",
    private_notes: grade?.private_notes ?? "",
  };
}

function GradePanel({ submission, attempt, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const grade = attempt.grade;
  const rubric = grade?.rubric ?? submission.assignment.rubric;
  const [form, setForm] = useState(() => gradeForm(grade));
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [retracting, setRetracting] = useState(false);
  const [reason, setReason] = useState("");
  useUnsavedChanges(dirty);
  const canGrade = can("assignments.grade");
  const canPublish = can("assignments.publish_grades");
  const released = grade?.status === "published";
  const set = (patch) => {
    setForm((f) => ({ ...f, ...patch }));
    setDirty(true);
  };
  const total = rubric
    ? rubric.criteria.reduce((sum, c) => sum + (Number(form.scores[c.id]) || 0), 0)
    : null;

  const run = async (action, message) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      notify(message);
      setDirty(false);
      onChanged();
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const saveDraft = (event) => {
    event.preventDefault();
    const body = {
      feedback: form.feedback,
      private_notes: form.private_notes,
      ...(grade && { lock_version: grade.lock_version }),
    };
    if (rubric) {
      body.scores = Object.fromEntries(
        Object.entries(form.scores)
          .filter(([, v]) => v !== "")
          .map(([k, v]) => [k, Number(v)]),
      );
    } else if (form.passed !== "") {
      body.passed = form.passed === "true";
    }
    run(() => api.assignments.saveGrade(attempt.id, body), "Draft grade saved.");
  };
  const publish = (outcome) =>
    run(
      () => api.assignments.publishGrade(attempt.id, { lock_version: grade.lock_version, outcome }),
      outcome === "graded" ? "Grade released to the learner." : "Changes requested.",
    );
  const retract = async () => {
    setRetracting(false);
    const done = await run(
      () => api.assignments.retractGrade(attempt.id, { lock_version: grade.lock_version, reason }),
      "Grade retracted.",
    );
    if (done) setReason("");
  };

  return (
    <section aria-labelledby="grade-heading" className="space-y-4 rounded-2xl bg-cream p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="grade-heading" className="text-lg font-medium">
          Grade attempt {attempt.number}
        </h3>
        <p className="text-sm text-muted">
          {grade ? GRADE_STATUS[grade.status] : "Not graded yet"}
          {rubric ? ` · rubric version ${rubric.version}` : " · pass/fail"}
        </p>
      </div>
      <ErrorSummary error={error} title="The grade needs attention" />
      <form onSubmit={saveDraft} className="space-y-4" noValidate>
        <fieldset disabled={!canGrade || released || busy} className="space-y-4">
          <legend className="sr-only">Scores and feedback</legend>
          {rubric ? (
            <ol className="space-y-3">
              {rubric.criteria.map((c) => (
                <li key={c.id} className="rounded-xl border border-charcoal/10 bg-white p-4">
                  <fieldset>
                    <legend className="font-medium">
                      {c.title}{" "}
                      <span className="text-sm font-normal text-muted">
                        (0–{c.max_points} points)
                      </span>
                    </legend>
                    {c.description && <p className="text-sm text-muted">{c.description}</p>}
                    {c.descriptors?.length > 0 && (
                      <div
                        className="mt-2 flex flex-wrap gap-2"
                        role="group"
                        aria-label={`${c.title} descriptors`}
                      >
                        {c.descriptors.map((d) => (
                          <button
                            key={d.label}
                            type="button"
                            aria-pressed={form.scores[c.id] === String(d.points)}
                            title={d.description || undefined}
                            onClick={() =>
                              set({ scores: { ...form.scores, [c.id]: String(d.points) } })
                            }
                            className="rounded-full border border-charcoal/20 px-3 py-1 text-sm aria-pressed:border-sage-700 aria-pressed:bg-sage-700 aria-pressed:text-ivory"
                          >
                            {d.label} · {d.points}
                          </button>
                        ))}
                      </div>
                    )}
                    <TextField
                      className="mt-2 max-w-[10rem]"
                      label={`Score for ${c.title}`}
                      type="number"
                      min="0"
                      max={c.max_points}
                      value={form.scores[c.id] ?? ""}
                      onChange={(e) => set({ scores: { ...form.scores, [c.id]: e.target.value } })}
                    />
                  </fieldset>
                </li>
              ))}
            </ol>
          ) : (
            <SelectField
              label="Outcome"
              value={form.passed}
              onChange={(e) => set({ passed: e.target.value })}
              options={[
                { value: "", label: "Not decided" },
                { value: "true", label: "Passed" },
                { value: "false", label: "Not passed" },
              ]}
            />
          )}
          {rubric && (
            <p className="text-sm" aria-live="polite">
              Total: {total} of {rubric.total_points} points
              {rubric.total_points
                ? ` (${Math.round((100 * total) / rubric.total_points)}%, pass at ${rubric.passing_percent}%)`
                : ""}
            </p>
          )}
          <TextAreaField
            label="Feedback for the learner"
            hint={
              rubric?.feedback_required
                ? "Required before the grade is released. Shown to the learner once released."
                : "Shown to the learner once the grade is released."
            }
            rows={6}
            value={form.feedback}
            onChange={(e) => set({ feedback: e.target.value })}
          />
          <TextAreaField
            label="Private staff notes"
            hint="Never shown to the learner."
            rows={3}
            value={form.private_notes}
            onChange={(e) => set({ private_notes: e.target.value })}
          />
          {canGrade && !released && (
            <Button type="submit" variant="outline" disabled={busy || !dirty}>
              {busy ? "Saving…" : "Save draft grade"}
            </Button>
          )}
        </fieldset>
      </form>
      {canPublish && grade && !released && (
        <div className="flex flex-wrap items-center gap-2 border-t border-charcoal/10 pt-4">
          <Button onClick={() => publish("graded")} disabled={busy || dirty}>
            Release grade
          </Button>
          <Button
            variant="outline"
            onClick={() => publish("changes_requested")}
            disabled={busy || dirty}
          >
            Request changes
          </Button>
          {dirty && <p className="text-sm text-muted">Save the draft before releasing.</p>}
        </div>
      )}
      {canPublish && released && (
        <Button variant="outline" onClick={() => setRetracting(true)} disabled={busy}>
          Retract released grade
        </Button>
      )}
      <Modal
        open={retracting}
        onClose={() => setRetracting(false)}
        title="Retract this grade?"
        footer={
          <>
            <Button variant="outline" onClick={() => setRetracting(false)}>
              Cancel
            </Button>
            <Button onClick={retract} disabled={!reason.trim() || busy}>
              Retract
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          The learner no longer sees it. A completion or certificate already issued is kept.
        </p>
        <TextField
          className="mt-3"
          label="Reason"
          value={reason}
          maxLength={300}
          onChange={(e) => setReason(e.target.value)}
        />
      </Modal>
    </section>
  );
}

function GradeSummary({ grade }) {
  if (!grade) return <p className="text-sm text-muted">Not graded.</p>;
  return (
    <div className="space-y-1 text-sm">
      <p>
        {GRADE_STATUS[grade.status]}
        {grade.outcome === "changes_requested" && " · changes requested"}
        {grade.percent != null && ` · ${grade.percent}%`}
        {grade.passed != null && (grade.passed ? " · passed" : " · not passed")}
      </p>
      {grade.published_at && (
        <p className="text-muted">Released {formatDateTimeLocal(grade.published_at)}</p>
      )}
      {grade.retracted_at && (
        <p className="text-muted">
          Retracted {formatDateTimeLocal(grade.retracted_at)}: {grade.retracted_reason}
        </p>
      )}
      {grade.feedback && <p className="whitespace-pre-wrap">{grade.feedback}</p>}
    </div>
  );
}

/** One learner's submission: their work, documents, grading and history. */
export function SubmissionReviewPage() {
  const { submissionId } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(
    () => api.assignments.submission(submissionId),
    [submissionId],
  );
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorState title="We couldn't load this submission" onRetry={reload} />;
  if (loading && !data) return <p role="status">Loading submission…</p>;
  const [latest, ...earlier] = data.attempts;
  const startReview = async () => {
    setBusy(true);
    try {
      await api.assignments.startReview(data.id, data.lock_version);
      notify("Marked as under review.");
      reload();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  };
  const learner = data.learner.name || data.learner.email;
  return (
    <>
      <AdminPageHeader
        title={`${learner}: ${data.assignment.title}`}
        description={`${ASSIGNMENT_KIND_LABEL[data.assignment.kind] ?? "Assignment"} · ${SUBMISSION_STATUS_LABEL[data.status] ?? data.status}`}
        breadcrumbs={[
          { label: "Assignment reviews", to: "/admin/assignment-reviews" },
          { label: learner },
        ]}
        actions={
          can("assignments.grade") &&
          ["pending_review", "resubmitted"].includes(data.status) && (
            <Button size="sm" onClick={startReview} disabled={busy}>
              Start review
            </Button>
          )
        }
      />
      <p className="mb-6 text-sm text-muted">{data.learner.email}</p>
      {latest ? (
        <div className="grid gap-8 xl:grid-cols-[1fr_28rem]">
          <section aria-labelledby="latest-heading" className="min-w-0 space-y-4">
            <h2 id="latest-heading" className="text-xl font-medium">
              Attempt {latest.number} (latest)
            </h2>
            <Responses
              assignment={data.assignment}
              attempt={latest}
              fileUrl={api.assignments.fileUrl}
            />
          </section>
          <GradePanel
            key={`${latest.id}:${latest.grade?.lock_version ?? 0}`}
            submission={data}
            attempt={latest}
            onChanged={reload}
          />
        </div>
      ) : (
        <p>No submitted attempts.</p>
      )}
      {earlier.length > 0 && (
        <section aria-labelledby="history-heading" className="mt-10 space-y-3">
          <h2 id="history-heading" className="text-xl font-medium">
            Submission and grading history
          </h2>
          {earlier.map((a) => (
            <details key={a.id} className="rounded-xl border border-charcoal/10 bg-white p-4">
              <summary className="cursor-pointer font-medium">
                Attempt {a.number} · submitted {formatDateTimeLocal(a.submitted_at)}
                {a.is_late && " · late"}
              </summary>
              <div className="mt-3 grid gap-6 lg:grid-cols-2">
                <Responses
                  assignment={data.assignment}
                  attempt={a}
                  fileUrl={api.assignments.fileUrl}
                />
                <GradeSummary grade={a.grade} />
              </div>
            </details>
          ))}
        </section>
      )}
    </>
  );
}

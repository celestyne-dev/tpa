import { AlertTriangle, CheckCircle2, Circle, Timer } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { formatCountdown, formatDateTimeLocal, spokenDuration } from "@/utils/datetime";
import { Question, Result } from "./AssessmentForm";

// Spoken reminders (seconds left). The visible timer itself is not announced every second.
const ANNOUNCE_AT = [600, 300, 60, 30];
const SAVE_DELAY = 1200;

const answered = (value) =>
  !(value == null || value === "" || (Array.isArray(value) && !value.length));

/**
 * Countdown driven by the server: the end time comes from ``seconds_left`` when the attempt
 * was loaded (so a wrong device clock doesn't matter). The server still decides whether an
 * answer arrived in time.
 */
function useCountdown(attempt, onExpire) {
  const [endAt] = useState(() =>
    attempt.seconds_left == null ? null : Date.now() + attempt.seconds_left * 1000,
  );
  const [left, setLeft] = useState(attempt.seconds_left);
  const [announcement, setAnnouncement] = useState("");
  const expired = useRef(false);
  const announced = useRef(new Set());
  const expireRef = useRef(onExpire);
  useEffect(() => {
    expireRef.current = onExpire;
  });
  useEffect(() => {
    if (endAt == null) return undefined;
    const tick = () => {
      const seconds = Math.max(0, Math.round((endAt - Date.now()) / 1000));
      setLeft(seconds);
      const mark = ANNOUNCE_AT.find((t) => seconds <= t && !announced.current.has(t));
      if (mark != null && seconds > 0) {
        ANNOUNCE_AT.filter((t) => t >= seconds).forEach((t) => announced.current.add(t));
        setAnnouncement(`${spokenDuration(seconds)} left.`);
      }
      if (seconds === 0 && !expired.current) {
        expired.current = true;
        setAnnouncement("Time is up. Submitting your saved answers.");
        expireRef.current();
      }
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [endAt]);
  return { left, announcement, timed: endAt != null };
}

/** Debounced autosave of changed answers; failures keep the answers and retry. */
function useAnswerAutosave(save) {
  const [status, setStatus] = useState("idle"); // idle|pending|saving|saved|error
  const pending = useRef({});
  const timer = useRef(null);
  const attempt = useRef(0);
  const inFlight = useRef(null);
  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  });
  const flushRef = useRef(null);
  const flush = useCallback(async () => {
    clearTimeout(timer.current);
    if (inFlight.current) await inFlight.current.catch(() => {});
    const batch = pending.current;
    if (!Object.keys(batch).length) return true;
    pending.current = {};
    setStatus("saving");
    const request = saveRef.current(batch);
    inFlight.current = request;
    try {
      await request;
      attempt.current = 0;
      setStatus(Object.keys(pending.current).length ? "pending" : "saved");
      return true;
    } catch (error) {
      // Keep the unsaved answers (newer edits win) and retry with backoff.
      pending.current = { ...batch, ...pending.current };
      if (error?.status && error.status < 500 && error.status !== 409) {
        setStatus("error");
        throw error;
      }
      if (error?.status === 409) throw error;
      attempt.current += 1;
      setStatus("error");
      timer.current = setTimeout(
        () => flushRef.current().catch(() => {}),
        Math.min(30000, 1000 * 2 ** attempt.current),
      );
      return false;
    } finally {
      inFlight.current = null;
    }
  }, []);
  useEffect(() => {
    flushRef.current = flush;
  }, [flush]);
  const queue = useCallback(
    (key, value) => {
      pending.current = { ...pending.current, [key]: value };
      setStatus("pending");
      clearTimeout(timer.current);
      timer.current = setTimeout(() => flush().catch(() => {}), SAVE_DELAY);
    },
    [flush],
  );
  useEffect(() => () => clearTimeout(timer.current), []);
  return { status, queue, flush, hasPending: () => Object.keys(pending.current).length > 0 };
}

const SAVE_TEXT = {
  idle: "",
  pending: "Unsaved changes…",
  saving: "Saving…",
  saved: "All answers saved.",
  error: "Couldn't save — your answers are kept here and we'll retry.",
};

function RunningAttempt({ attempt, api, onFinished, onExpiredSave }) {
  const [answers, setAnswers] = useState(attempt.answers ?? {});
  const [index, setIndex] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const headingRef = useRef(null);
  const confirmRef = useRef(null);
  const ids = useId();
  const questions = attempt.questions;
  const question = questions[index];
  const autosave = useAnswerAutosave(async (batch) => {
    try {
      return await api.save(attempt.id, batch);
    } catch (err) {
      // The server says time is up (or the attempt was submitted elsewhere).
      if (["attempt_expired", "attempt_closed"].includes(err.code)) onExpiredSave();
      throw err;
    }
  });

  const submit = useCallback(
    async ({ force = false } = {}) => {
      setSubmitting(true);
      setError(null);
      try {
        await autosave.flush().catch(() => {});
        const res = await api.submit(attempt.id, force ? undefined : answers);
        onFinished(res.data);
      } catch (err) {
        if (["attempt_closed", "attempt_expired"].includes(err.code)) {
          onExpiredSave();
          return;
        }
        setFieldErrors(err.details?.answers ?? {});
        const firstMissing = questions.findIndex((q) => err.details?.answers?.[String(q.id)]);
        if (firstMissing >= 0) setIndex(firstMissing);
        setError(err);
        setConfirming(false);
      } finally {
        setSubmitting(false);
      }
    },
    [answers, api, attempt.id, autosave, onExpiredSave, onFinished, questions],
  );
  const { left, announcement, timed } = useCountdown(attempt, () => submit({ force: true }));

  useEffect(() => {
    if (!timed) return undefined;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [timed]);

  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  const change = (value) => {
    const key = String(question.id);
    setAnswers((a) => ({ ...a, [key]: value }));
    setFieldErrors((e) => ({ ...e, [key]: undefined }));
    autosave.queue(key, answered(value) ? value : null);
  };
  const go = (next) => {
    setIndex(next);
    requestAnimationFrame(() => headingRef.current?.focus());
  };
  const unanswered = questions.filter((q) => !answered(answers[String(q.id)])).length;
  const low = timed && left <= 60;

  return (
    <div className="space-y-5">
      <div className="sticky top-0 z-10 -mx-1 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-charcoal/10 bg-ivory/95 p-3 backdrop-blur">
        <p className="text-sm">
          Question {index + 1} of {questions.length}
          <span className="text-muted"> · {questions.length - unanswered} answered</span>
        </p>
        {timed && (
          <p
            role="timer"
            aria-live="off"
            aria-label={`Time remaining: ${spokenDuration(left)}`}
            className={`flex items-center gap-1.5 font-mono text-lg font-semibold ${low ? "text-red-800" : ""}`}
          >
            <Timer aria-hidden className="size-5" /> {formatCountdown(left)}
          </p>
        )}
        <p aria-live="polite" className="w-full text-xs text-muted sm:w-auto">
          {SAVE_TEXT[autosave.status]}
        </p>
      </div>
      <p aria-live="assertive" className="sr-only">
        {announcement}
      </p>
      {timed && (
        <p role="note" className="flex gap-2 rounded-xl bg-gold-100/60 p-3 text-sm">
          <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-gold-700" />
          The timer runs on our server: it keeps counting down if you leave or close this page.
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">
          {error.message}
        </p>
      )}
      <div>
        <h3 ref={headingRef} tabIndex={-1} className="sr-only outline-none">
          Question {index + 1} of {questions.length}
        </h3>
        <Question
          key={question.id}
          index={index}
          question={question}
          value={answers[String(question.id)]}
          error={fieldErrors[String(question.id)]?.join(" ")}
          onChange={change}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="outline" onClick={() => go(index - 1)} disabled={index === 0}>
          Previous
        </Button>
        {index < questions.length - 1 ? (
          <Button variant="outline" onClick={() => go(index + 1)}>
            Next
          </Button>
        ) : (
          <Button onClick={() => setConfirming(true)} disabled={submitting}>
            Review and submit
          </Button>
        )}
      </div>
      <nav aria-label="Questions" className="rounded-2xl border border-charcoal/10 bg-white p-4">
        <ol className="flex flex-wrap gap-2">
          {questions.map((q, i) => {
            const done = answered(answers[String(q.id)]);
            return (
              <li key={q.id}>
                <button
                  type="button"
                  onClick={() => go(i)}
                  aria-current={i === index ? "step" : undefined}
                  aria-label={`Question ${i + 1}${done ? ", answered" : ", not answered"}`}
                  className={`flex size-10 items-center justify-center rounded-full border text-sm ${
                    i === index
                      ? "border-sage-700 bg-sage-700 text-ivory"
                      : done
                        ? "border-sage-600 bg-sage-50"
                        : "border-charcoal/20"
                  }`}
                >
                  {i + 1}
                </button>
              </li>
            );
          })}
        </ol>
        {questions.length > 1 && (
          <Button
            className="mt-3"
            size="sm"
            onClick={() => setConfirming(true)}
            disabled={submitting}
          >
            Submit exam
          </Button>
        )}
      </nav>
      {confirming && (
        <section
          ref={confirmRef}
          tabIndex={-1}
          role="alertdialog"
          aria-labelledby={`${ids}-confirm`}
          aria-describedby={`${ids}-confirm-desc`}
          className="rounded-2xl border-2 border-sage-600 bg-white p-5 outline-none"
        >
          <h3 id={`${ids}-confirm`} className="text-lg font-medium">
            Submit your answers?
          </h3>
          <p id={`${ids}-confirm-desc`} className="mt-1 text-sm">
            {unanswered
              ? `${unanswered} question${unanswered === 1 ? " is" : "s are"} still unanswered. `
              : "Every question has an answer. "}
            You can't change your answers after submitting.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button onClick={() => submit()} disabled={submitting}>
              {submitting ? "Submitting…" : "Yes, submit"}
            </Button>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={submitting}>
              Keep working
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}

function History({ assessment }) {
  if (!assessment.attempts?.length) return null;
  return (
    <section aria-label="Your previous attempts" className="space-y-2">
      <h3 className="font-medium">Your attempts</h3>
      <ol className="space-y-2">
        {assessment.attempts.map((a) => (
          <li key={a.id} className="rounded-xl border border-charcoal/10 bg-white p-3">
            <details>
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
                {a.passed ? (
                  <CheckCircle2 aria-hidden className="size-4 text-sage-700" />
                ) : (
                  <Circle aria-hidden className="size-4 text-charcoal/40" />
                )}
                <span className="font-medium">Attempt {a.attempt_number}</span>
                <span className="text-muted">
                  {formatDateTimeLocal(a.submitted_at)}
                  {a.percent != null && ` · ${a.percent}%`}
                  {a.status === "expired" && " · time ran out"}
                  {a.passed != null && (a.passed ? " · passed" : " · not passed")}
                </span>
              </summary>
              <div className="mt-3">
                <Result assessment={assessment} attempt={a} />
              </div>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * Drawn, shuffled or timed assessment: start (or resume) an attempt, answer with autosave,
 * then submit. Scoring, timing and eligibility are decided by the server.
 */
export function PracticeExam({ assessment, api, onAssessment }) {
  const [attempt, setAttempt] = useState(assessment.in_progress);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const resultRef = useRef(null);
  const headingId = useId();
  const exhausted = assessment.attempts_left === 0;

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.start();
      setResult(null);
      setAttempt(res.data.attempt);
      onAssessment(res.data.assessment);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const finished = (data) => {
    setAttempt(null);
    setResult(data.attempt);
    onAssessment(data.assessment, data.progress);
    requestAnimationFrame(() => resultRef.current?.focus());
  };
  // The server closed the attempt (deadline passed or already submitted): show the outcome.
  const closed = async () => {
    const res = await api.reload();
    const latest = res.data.assessment.attempts?.[0] ?? null;
    setAttempt(null);
    setResult(latest);
    onAssessment(res.data.assessment, res.data.progress);
    requestAnimationFrame(() => resultRef.current?.focus());
  };

  return (
    <section aria-labelledby={headingId} className="space-y-6 rounded-3xl bg-cream p-5 sm:p-7">
      <div>
        <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
          {assessment.practice ? "Practice exam" : "Graded quiz"}
          {assessment.required_for_completion && " · Required for completion"}
        </p>
        <h2 id={headingId} className="mt-1 text-2xl font-medium">
          {assessment.title}
        </h2>
        {assessment.description && <p className="mt-2 text-muted">{assessment.description}</p>}
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
          <li>{assessment.question_count} questions</li>
          <li>
            {assessment.time_limit_minutes ? `${assessment.time_limit_minutes} minutes` : "Untimed"}
          </li>
          {assessment.passing_score != null && <li>Pass mark {assessment.passing_score}%</li>}
          <li>
            {assessment.max_attempts
              ? `${assessment.attempts_used} of ${assessment.max_attempts} attempts used`
              : "Unlimited attempts"}
          </li>
          {assessment.best_percent != null && <li>Best score {assessment.best_percent}%</li>}
        </ul>
        {assessment.practice && (
          <p className="mt-2 text-sm">
            Practice exams help you prepare. They never count towards course completion or your
            certificate.
          </p>
        )}
      </div>
      {attempt ? (
        <RunningAttempt
          key={attempt.id}
          attempt={attempt}
          api={api}
          onFinished={finished}
          onExpiredSave={closed}
        />
      ) : (
        <>
          <div ref={resultRef} tabIndex={-1} aria-live="polite" className="outline-none">
            {result && <Result assessment={assessment} attempt={result} />}
          </div>
          {error && (
            <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">
              {error.message}
            </p>
          )}
          {exhausted ? (
            <p className="text-sm font-medium">You have used all attempts for this exam.</p>
          ) : (
            <div className="space-y-3">
              {assessment.time_limit_minutes && (
                <p role="note" className="flex gap-2 rounded-xl bg-gold-100/60 p-3 text-sm">
                  <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-gold-700" />
                  Once you start, you have {assessment.time_limit_minutes} minutes. The timer keeps
                  counting down even if you leave this page.
                </p>
              )}
              <Button onClick={start} disabled={busy}>
                {busy
                  ? "Starting…"
                  : assessment.attempts?.length
                    ? "Start a new attempt"
                    : "Start exam"}
              </Button>
            </div>
          )}
          <History assessment={assessment} />
        </>
      )}
    </section>
  );
}

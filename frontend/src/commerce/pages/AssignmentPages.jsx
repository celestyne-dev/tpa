import { ArrowLeft, Download, FileText, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { useUnsavedChanges } from "@/admin/hooks/useUnsavedChanges";
import { AssignmentBrief } from "@/components/courses/AssignmentBrief";
import { SUBMISSION_STATUS_LABEL } from "@/components/courses/assignmentLabels";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { routes } from "@/config/navigation";
import { formatDateTimeLocal } from "@/utils/datetime";
import { formatBytes } from "@/utils/format";
import { RequireCustomer } from "../RequireCustomer";

const SAVE_DELAY = 2000;
const countWords = (text) => (text.trim() ? text.trim().split(/\s+/).length : 0);
const backupKey = (slug, id) => `tpa-assignment-draft:${slug}:${id}`;

function readBackup(key) {
  try {
    return JSON.parse(window.localStorage.getItem(key) ?? "null");
  } catch {
    return null;
  }
}
function writeBackup(key, value) {
  try {
    if (value) window.localStorage.setItem(key, JSON.stringify(value));
    else window.localStorage.removeItem(key);
  } catch {
    // Storage full or disabled: the server copy and on-screen text remain.
  }
}

const BLOCKED = {
  not_open: "This assignment isn't open for submissions yet.",
  attempts_exhausted: "You have used every attempt for this assignment.",
  completed: "You have completed this assignment.",
  awaiting_review: "Your submission is waiting for review. You'll be able to read feedback here.",
  resubmission_not_allowed: "This assignment can't be resubmitted right now.",
  deadline_passed: "The deadline has passed, so new submissions aren't accepted.",
};

const SAVE_TEXT = {
  idle: "",
  pending: "Unsaved changes…",
  saving: "Saving draft…",
  saved: "Draft saved.",
  offline:
    "You're offline — your text is kept on this device and will be saved when you reconnect.",
  error: "Couldn't save your draft. Your text is kept on this device; we'll keep trying.",
  conflict:
    "This draft was changed in another window. Your text here is kept — reload to see the other version.",
};

function Grade({ grade, rubric }) {
  if (!grade) return null;
  const criteria = grade.rubric?.criteria ?? rubric?.criteria ?? [];
  return (
    <section className="space-y-3 rounded-2xl bg-sage-50 p-4" aria-label="Instructor feedback">
      <p className="font-medium">
        {grade.outcome === "changes_requested"
          ? "Your reviewer asked for changes"
          : grade.passed
            ? `Passed${grade.percent != null ? ` — ${grade.percent}%` : ""}`
            : `Not passed yet${grade.percent != null ? ` — ${grade.percent}%` : ""}`}
      </p>
      {grade.total_points != null && (
        <p className="text-sm">
          {grade.total_points} of {grade.max_points} points
        </p>
      )}
      {criteria.length > 0 && Object.keys(grade.scores ?? {}).length > 0 && (
        <ul className="space-y-1 text-sm">
          {criteria.map((c) => (
            <li key={c.id}>
              {c.title}: {grade.scores[c.id] ?? "—"} / {c.max_points}
            </li>
          ))}
        </ul>
      )}
      {grade.feedback && (
        <div>
          <p className="text-sm font-medium">Feedback</p>
          <p className="mt-1 text-sm leading-relaxed whitespace-pre-wrap">{grade.feedback}</p>
        </div>
      )}
      <p className="text-xs text-muted">Released {formatDateTimeLocal(grade.released_at)}</p>
    </section>
  );
}

function FileList({ files, fileUrl, onRemove, busy }) {
  if (!files?.length) return null;
  return (
    <ul className="space-y-2" aria-label="Supporting documents">
      {files.map((f) => (
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
          {onRemove && (
            <button
              type="button"
              disabled={busy}
              onClick={() => onRemove(f)}
              aria-label={`Remove ${f.filename}`}
              className="rounded p-1 text-muted hover:text-red-800"
            >
              <Trash2 aria-hidden className="size-4" />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

function AttemptHistory({ view, fileUrl }) {
  if (!view.history.length) return null;
  const prompts = view.assignment.prompts;
  return (
    <section aria-labelledby="history-heading" className="space-y-3">
      <h2 id="history-heading" className="text-xl font-medium">
        Your submissions
      </h2>
      <ol className="space-y-3">
        {view.history.map((a) => (
          <li key={a.id} className="rounded-2xl border border-charcoal/10 bg-white p-4">
            <p className="font-medium">
              Attempt {a.number}
              {a.latest && " (latest)"}
              <span className="ml-2 text-sm font-normal text-muted">
                Submitted {formatDateTimeLocal(a.submitted_at)}
                {a.is_late && " · late"}
              </span>
            </p>
            <Grade grade={a.grade} rubric={view.assignment.rubric} />
            {!a.grade && a.latest && (
              <p className="mt-2 text-sm text-muted">No feedback has been released yet.</p>
            )}
            <details className="mt-3">
              <summary className="cursor-pointer text-sm font-medium">What you submitted</summary>
              <div className="mt-2 space-y-3">
                {prompts.map((p) => (
                  <div key={p.id}>
                    <p className="text-sm font-medium">{p.text}</p>
                    <p className="text-sm whitespace-pre-wrap">{a.responses[p.id] || "—"}</p>
                  </div>
                ))}
                <FileList files={a.files} fileUrl={fileUrl} />
              </div>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * Draft editor with conflict-aware autosave. Text is never thrown away: it stays on screen
 * and in a local backup until the server confirms it, and network failures retry.
 */
function DraftEditor({ view, slug, onView }) {
  const shopApi = useShopApi();
  const ids = useId();
  const assignment = view.assignment;
  const storageKey = backupKey(slug, assignment.id);
  const [responses, setResponses] = useState(() => view.draft?.responses ?? {});
  const [saved, setSaved] = useState(() => view.draft?.responses ?? {});
  const [status, setStatus] = useState("idle");
  const [backup, setBackup] = useState(() => {
    const local = readBackup(storageKey);
    if (!local) return null;
    const server = view.draft?.responses ?? {};
    return JSON.stringify(local.responses) !== JSON.stringify(server) ? local : null;
  });
  const [submitError, setSubmitError] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(view.draft?.lock_version ?? null);
  const inFlight = useRef(null);
  const timer = useRef(null);
  const retries = useRef(0);
  const latest = useRef(responses);
  const submitKey = useRef(null);
  const resultRef = useRef(null);
  const dirty = JSON.stringify(responses) !== JSON.stringify(saved);
  useUnsavedChanges(dirty);

  useEffect(() => {
    latest.current = responses;
  }, [responses]);

  const saveRef = useRef(null);
  const save = useCallback(async () => {
    clearTimeout(timer.current);
    if (inFlight.current) return inFlight.current;
    const body = { responses: latest.current };
    if (lock.current) body.lock_version = lock.current;
    const sent = latest.current;
    setStatus("saving");
    const request = shopApi
      .saveAssignmentDraft(slug, assignment.id, body)
      .then((res) => {
        retries.current = 0;
        lock.current = res.data.draft?.lock_version ?? lock.current;
        setSaved(sent);
        onView(res.data);
        if (JSON.stringify(sent) === JSON.stringify(latest.current)) {
          writeBackup(storageKey, null);
          setStatus("saved");
        } else {
          setStatus("pending");
          timer.current = setTimeout(() => saveRef.current(), SAVE_DELAY);
        }
        return true;
      })
      .catch((err) => {
        if (err.code === "edit_conflict") {
          setStatus("conflict");
        } else if (!err.status || err.status >= 500) {
          retries.current += 1;
          setStatus(typeof navigator !== "undefined" && !navigator.onLine ? "offline" : "error");
          timer.current = setTimeout(
            () => saveRef.current(),
            Math.min(60000, 1000 * 2 ** retries.current),
          );
        } else {
          setStatus("error");
          setSubmitError(err);
        }
        return false;
      })
      .finally(() => {
        inFlight.current = null;
      });
    inFlight.current = request;
    return request;
  }, [assignment.id, onView, shopApi, slug, storageKey]);
  useEffect(() => {
    saveRef.current = save;
  }, [save]);

  useEffect(() => {
    const retry = () => retries.current > 0 && save();
    window.addEventListener("online", retry);
    return () => {
      window.removeEventListener("online", retry);
      clearTimeout(timer.current);
    };
  }, [save]);

  const change = (promptId, text) => {
    const next = { ...latest.current, [promptId]: text };
    latest.current = next;
    setResponses(next);
    writeBackup(storageKey, { responses: next, at: new Date().toISOString() });
    if (status === "conflict") return;
    setStatus("pending");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => saveRef.current(), SAVE_DELAY);
  };

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setFileError(null);
    setBusy(true);
    try {
      if (dirty) await save();
      const res = await shopApi.uploadAssignmentFile(slug, assignment.id, file);
      lock.current = res.data.draft?.lock_version ?? lock.current;
      onView(res.data);
    } catch (err) {
      setFileError(err);
    } finally {
      setBusy(false);
    }
  };
  const removeFile = async (file) => {
    setFileError(null);
    setBusy(true);
    try {
      await shopApi.removeAssignmentFile(file.id);
      const res = await shopApi.assignment(slug, assignment.id);
      lock.current = res.data.draft?.lock_version ?? lock.current;
      onView(res.data);
    } catch (err) {
      setFileError(err);
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    setSubmitError(null);
    setBusy(true);
    try {
      if (dirty || !lock.current) {
        const ok = await save();
        if (!ok) throw new Error("Your draft couldn't be saved, so it wasn't submitted.");
      }
      // The same key is reused if this request is retried, so it is never submitted twice.
      submitKey.current ??=
        globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const res = await shopApi.submitAssignment(slug, assignment.id, {
        idempotency_key: submitKey.current.replace(/[^A-Za-z0-9-]/g, "").slice(0, 64),
        lock_version: lock.current,
      });
      submitKey.current = null;
      writeBackup(storageKey, null);
      setConfirming(false);
      onView(res.data, { submitted: true });
    } catch (err) {
      setSubmitError(err);
      setConfirming(false);
      requestAnimationFrame(() => resultRef.current?.focus());
    } finally {
      setBusy(false);
    }
  };

  const req = assignment.requirements;
  const total = Object.values(responses).reduce((sum, t) => sum + countWords(t ?? ""), 0);
  const files = view.draft?.files ?? [];
  const previous = view.history[0];

  return (
    <section aria-labelledby={`${ids}-draft`} className="space-y-5 rounded-3xl bg-cream p-5 sm:p-7">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={`${ids}-draft`} className="text-xl font-medium">
          {view.history.length ? `Attempt ${view.history.length + 1}` : "Your response"}
        </h2>
        <p aria-live="polite" className="text-sm text-muted">
          {SAVE_TEXT[status]}
        </p>
      </div>
      {backup && (
        <div role="alert" className="rounded-xl border border-gold-300 bg-gold-100/60 p-3 text-sm">
          <p>
            We found text from {formatDateTimeLocal(backup.at)} on this device that wasn&apos;t
            saved yet.
          </p>
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              onClick={() => {
                Object.entries(backup.responses).forEach(([k, v]) => change(k, v));
                setBackup(null);
              }}
            >
              Restore it
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                writeBackup(storageKey, null);
                setBackup(null);
              }}
            >
              Discard
            </Button>
          </div>
        </div>
      )}
      {previous && !view.draft && Object.keys(responses).length === 0 && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => Object.entries(previous.responses).forEach(([k, v]) => change(k, v ?? ""))}
        >
          Start from my previous submission
        </Button>
      )}
      <div ref={resultRef} tabIndex={-1} className="outline-none">
        <ErrorSummary error={submitError} title="Your submission isn't ready yet" />
      </div>
      {assignment.prompts.map((p, i) => {
        const words = countWords(responses[p.id] ?? "");
        return (
          <div key={p.id} className="rounded-2xl border border-charcoal/10 bg-white p-4">
            <label htmlFor={`${ids}-${p.id}`} className="font-medium">
              <span className="text-sage-700">{i + 1}.</span> {p.text}
            </label>
            <textarea
              id={`${ids}-${p.id}`}
              rows={10}
              maxLength={50000}
              value={responses[p.id] ?? ""}
              aria-describedby={`${ids}-${p.id}-count`}
              onChange={(e) => change(p.id, e.target.value)}
              className="mt-3 w-full rounded-xl border border-charcoal/15 p-3 leading-relaxed"
            />
            <p id={`${ids}-${p.id}-count`} className="mt-1 text-xs text-muted">
              {words} word{words === 1 ? "" : "s"}
              {p.min_words ? ` · at least ${p.min_words}` : ""}
            </p>
          </div>
        );
      })}
      <p className="text-sm text-muted">
        {total} words in total
        {req.min_words ? ` · minimum ${req.min_words}` : ""}
        {req.max_words ? ` · maximum ${req.max_words}` : ""}
      </p>
      {req.files !== "none" && (
        <div className="space-y-2">
          <p className="font-medium">
            Supporting documents{" "}
            <span className="text-sm font-normal text-muted">
              ({req.files === "required" ? "required" : "optional"}; PDF or Word .docx)
            </span>
          </p>
          <FileList
            files={files}
            fileUrl={shopApi.assignmentFileUrl}
            onRemove={removeFile}
            busy={busy}
          />
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-charcoal/20 bg-white px-4 py-2 text-sm font-medium focus-within:ring-2 focus-within:ring-sage-600">
            <Upload aria-hidden className="size-4" />
            {busy ? "Working…" : "Attach a document"}
            <input
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="sr-only"
              disabled={busy}
              onChange={upload}
            />
          </label>
          <ErrorSummary error={fileError} title="The document wasn't added" />
        </div>
      )}
      <div className="border-t border-charcoal/10 pt-4">
        {confirming ? (
          <div role="alertdialog" aria-labelledby={`${ids}-confirm`} className="space-y-3">
            <p id={`${ids}-confirm`} className="font-medium">
              Submit this attempt for review? You can&apos;t edit it afterwards.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={submit} disabled={busy}>
                {busy ? "Submitting…" : "Yes, submit"}
              </Button>
              <Button variant="outline" onClick={() => setConfirming(false)} disabled={busy}>
                Keep editing
              </Button>
            </div>
          </div>
        ) : (
          <Button onClick={() => setConfirming(true)} disabled={busy || status === "conflict"}>
            Submit for review
          </Button>
        )}
      </div>
    </section>
  );
}

function AssignmentView({ slug, id }) {
  const shopApi = useShopApi();
  const [state, setState] = useState({ status: "loading", view: null, error: null, notice: "" });
  const noticeRef = useRef(null);
  const [version, setVersion] = useState(0);
  const load = () => setVersion((v) => v + 1);
  useEffect(() => {
    let live = true;
    shopApi.assignment(slug, id).then(
      (res) => live && setState({ status: "ready", view: res.data, error: null, notice: "" }),
      (error) => live && setState({ status: "error", view: null, error, notice: "" }),
    );
    return () => {
      live = false;
    };
  }, [id, shopApi, slug, version]);
  const onView = useCallback((view, { submitted } = {}) => {
    setState((s) => ({
      ...s,
      view,
      notice: submitted ? "Submitted. Your reviewer will be notified." : s.notice,
    }));
    if (submitted) requestAnimationFrame(() => noticeRef.current?.focus());
  }, []);

  if (state.status === "loading" && !state.view)
    return (
      <p role="status" className="py-16 text-center text-muted">
        Loading assignment…
      </p>
    );
  if (state.status === "error") {
    if (state.error?.status === 404 || state.error?.status === 403)
      return (
        <EmptyState
          icon={FileText}
          title="This assignment isn't available"
          description={state.error.message}
          action={
            <Link to={routes.learn(slug)} className="underline underline-offset-4">
              Back to the course
            </Link>
          }
        />
      );
    return <ErrorState title="We couldn't load this assignment" onRetry={load} />;
  }
  const view = state.view;
  const status = view.submission?.status ?? "not_started";
  const canWrite = view.can_submit;
  return (
    <div className="space-y-8">
      <AssignmentBrief
        assignment={view.assignment}
        attemptsAllowed={view.attempts_allowed}
        attemptsUsed={view.submission?.attempts_used ?? 0}
        headingLevel={1}
      />
      <div
        ref={noticeRef}
        tabIndex={-1}
        aria-live="polite"
        className="rounded-2xl border border-charcoal/10 bg-white p-4 outline-none"
      >
        <p className="font-medium">Status: {SUBMISSION_STATUS_LABEL[status] ?? status}</p>
        {state.notice && <p className="mt-1 text-sm text-sage-800">{state.notice}</p>}
        {!canWrite && view.blocked_reason && (
          <p className="mt-1 text-sm text-muted">{BLOCKED[view.blocked_reason]}</p>
        )}
      </div>
      {canWrite && (
        <DraftEditor key={view.history.length} view={view} slug={slug} onView={onView} />
      )}
      <AttemptHistory view={view} fileUrl={shopApi.assignmentFileUrl} />
    </div>
  );
}

export function LearnAssignmentPage() {
  const { courseSlug, assignmentId } = useParams();
  return (
    <RequireCustomer>
      <Seo title="Assignment" path={routes.accountLearning} noIndex />
      <div className="border-b border-charcoal/[0.06] bg-cream">
        <Container size="wide" className="py-4">
          <Link
            to={routes.learn(courseSlug)}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-sage-800 underline-offset-4 hover:underline"
          >
            <ArrowLeft aria-hidden className="size-4" /> Course outline
          </Link>
        </Container>
      </div>
      <Container className="py-10">
        <div className="mx-auto max-w-[72ch]">
          <AssignmentView slug={courseSlug} id={assignmentId} />
        </div>
      </Container>
    </RequireCustomer>
  );
}

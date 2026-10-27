import { CheckCircle2, CircleX } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";

const KIND_LABEL = {
  quiz: "Quiz",
  reflection: "Written reflection",
  self_assessment: "Self-assessment",
};

function Question({ question, value, onChange, error, index }) {
  const id = useId();
  const describedBy = [question.help_text && `${id}-help`, error && `${id}-error`]
    .filter(Boolean)
    .join(" ");
  const legend = (
    <legend className="font-medium">
      <span className="text-sage-700">{index + 1}.</span> {question.prompt}
      {!question.required && <span className="ml-1 text-sm text-muted">(optional)</span>}
    </legend>
  );
  const help = question.help_text && (
    <p id={`${id}-help`} className="mt-1 text-sm text-muted">
      {question.help_text}
    </p>
  );
  const errorText = error && (
    <p id={`${id}-error`} role="alert" className="mt-2 text-sm text-red-800">
      {error}
    </p>
  );
  if (question.kind === "short_text") {
    return (
      <div className="rounded-2xl border border-charcoal/10 bg-white p-5">
        <label htmlFor={`${id}-text`} className="font-medium">
          <span className="text-sage-700">{index + 1}.</span> {question.prompt}
          {!question.required && <span className="ml-1 text-sm text-muted">(optional)</span>}
        </label>
        {help}
        <textarea
          id={`${id}-text`}
          rows={4}
          maxLength={question.max_length}
          value={value ?? ""}
          aria-describedby={describedBy || undefined}
          aria-invalid={error ? true : undefined}
          onChange={(e) => onChange(e.target.value)}
          className="mt-3 w-full rounded-xl border border-charcoal/15 p-3"
        />
        {errorText}
      </div>
    );
  }
  if (question.kind === "rating") {
    const scale = Array.from({ length: question.scale }, (_, i) => i + 1);
    return (
      <fieldset
        className="rounded-2xl border border-charcoal/10 bg-white p-5"
        aria-describedby={describedBy || undefined}
      >
        {legend}
        {help}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {question.min_label && <span className="text-sm text-muted">{question.min_label}</span>}
          {scale.map((n) => (
            <label
              key={n}
              className="grid size-11 cursor-pointer place-items-center rounded-full border border-charcoal/20 has-[:checked]:border-sage-700 has-[:checked]:bg-sage-700 has-[:checked]:text-ivory has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-sage-600"
            >
              <input
                type="radio"
                name={`${id}-rating`}
                value={n}
                checked={value === n}
                onChange={() => onChange(n)}
                className="sr-only"
              />
              {n}
            </label>
          ))}
          {question.max_label && <span className="text-sm text-muted">{question.max_label}</span>}
        </div>
        {errorText}
      </fieldset>
    );
  }
  const multiple = question.kind === "multiple_select";
  const selected = multiple ? (value ?? []) : value;
  return (
    <fieldset
      className="rounded-2xl border border-charcoal/10 bg-white p-5"
      aria-describedby={describedBy || undefined}
    >
      {legend}
      {help}
      {multiple && <p className="mt-1 text-sm text-muted">Choose all that apply.</p>}
      <div className="mt-3 space-y-2">
        {question.options.map((option) => (
          <label
            key={option.id}
            className="flex cursor-pointer items-start gap-3 rounded-xl border border-charcoal/10 p-3 has-[:checked]:border-sage-600 has-[:checked]:bg-sage-50"
          >
            <input
              type={multiple ? "checkbox" : "radio"}
              name={`${id}-choice`}
              value={option.id}
              checked={multiple ? selected.includes(option.id) : selected === option.id}
              onChange={(e) =>
                onChange(
                  multiple
                    ? e.target.checked
                      ? [...selected, option.id]
                      : selected.filter((v) => v !== option.id)
                    : option.id,
                )
              }
              className="mt-1 size-4 accent-sage-700"
            />
            <span>{option.text}</span>
          </label>
        ))}
      </div>
      {errorText}
    </fieldset>
  );
}

function optionText(options, ids) {
  const map = Object.fromEntries((options ?? []).map((o) => [o.id, o.text]));
  return (ids ?? []).map((v) => map[v] ?? v).join(", ");
}

function Result({ assessment, attempt }) {
  return (
    <div className="space-y-4">
      <div
        className={`rounded-2xl p-5 ${
          attempt.graded ? (attempt.passed ? "bg-sage-50" : "bg-gold-100/50") : "bg-sage-50"
        }`}
      >
        {attempt.graded ? (
          <p className="flex items-center gap-2 text-lg font-medium">
            {attempt.passed ? (
              <CheckCircle2 aria-hidden className="size-6 text-sage-700" />
            ) : (
              <CircleX aria-hidden className="size-6 text-gold-700" />
            )}
            {attempt.passed ? "Passed" : "Not passed yet"}: {attempt.percent}% ({attempt.score} of{" "}
            {attempt.max_score} points)
          </p>
        ) : (
          <p className="text-lg font-medium">Thank you — your answers are saved.</p>
        )}
        {attempt.graded && !attempt.passed && assessment.passing_score != null && (
          <p className="mt-1 text-sm">
            You need {assessment.passing_score}% to pass.
            {assessment.attempts_left === 0
              ? " You have no attempts left."
              : assessment.attempts_left != null
                ? ` Attempts left: ${assessment.attempts_left}.`
                : " You can try again."}
          </p>
        )}
      </div>
      {attempt.results.some((r) => r.graded && "correct" in r) && (
        <ol className="space-y-3">
          {attempt.results
            .filter((r) => r.graded)
            .map((r) => (
              <li key={r.question_id} className="rounded-xl border border-charcoal/10 bg-white p-4">
                <p className="font-medium">{r.prompt}</p>
                <p className={`mt-1 text-sm ${r.correct ? "text-sage-800" : "text-red-800"}`}>
                  {r.correct ? "Correct" : "Not quite"}
                </p>
                {r.correct_answer && (
                  <p className="mt-1 text-sm">
                    Correct answer: {optionText(r.options, r.correct_answer)}
                  </p>
                )}
                {r.explanation && <p className="mt-1 text-sm text-muted">{r.explanation}</p>}
              </li>
            ))}
        </ol>
      )}
    </div>
  );
}

/** A quiz, reflection or self-assessment. Scoring always happens on the server. */
export function AssessmentForm({ assessment, onSubmit }) {
  const [answers, setAnswers] = useState({});
  const [state, setState] = useState({ busy: false, error: "", fieldErrors: {}, attempt: null });
  const resultRef = useRef(null);
  const headingId = useId();
  const latest = state.attempt ?? assessment.attempts?.[0] ?? null;
  const exhausted = assessment.attempts_left === 0;
  const canRetry = !exhausted && !(assessment.graded === false && latest);
  const [retrying, setRetrying] = useState(false);
  const showForm = !latest || retrying;

  const submit = async (event) => {
    event.preventDefault();
    setState((s) => ({ ...s, busy: true, error: "", fieldErrors: {} }));
    try {
      const attempt = await onSubmit(answers);
      setState({ busy: false, error: "", fieldErrors: {}, attempt });
      setRetrying(false);
      setAnswers({});
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (error) {
      setState({
        busy: false,
        error: error.message,
        fieldErrors: error.details?.answers ?? {},
        attempt: null,
      });
    }
  };

  return (
    <section aria-labelledby={headingId} className="rounded-3xl bg-cream p-5 sm:p-7">
      <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
        {KIND_LABEL[assessment.kind]}
        {assessment.required_for_completion && " · Required"}
      </p>
      <h2 id={headingId} className="mt-1 text-2xl font-medium">
        {assessment.title}
      </h2>
      {assessment.description && <p className="mt-2 text-muted">{assessment.description}</p>}
      {assessment.graded && (
        <p className="mt-2 text-sm text-muted">
          Pass mark {assessment.passing_score}%.
          {assessment.max_attempts
            ? ` ${assessment.attempts_used} of ${assessment.max_attempts} attempts used.`
            : " Unlimited attempts."}
        </p>
      )}
      {!assessment.graded && (
        <p className="mt-2 text-sm text-muted">
          Nothing here is marked right or wrong; your answers are saved for you.
        </p>
      )}
      <div ref={resultRef} tabIndex={-1} aria-live="polite" className="mt-5 outline-none">
        {latest && !retrying && <Result assessment={assessment} attempt={latest} />}
      </div>
      {latest && !retrying && canRetry && assessment.graded && (
        <Button className="mt-4" variant="outline" onClick={() => setRetrying(true)}>
          Try again
        </Button>
      )}
      {showForm && !exhausted && (
        <form onSubmit={submit} className="mt-5 space-y-4" noValidate>
          {assessment.questions.map((question, index) => (
            <Question
              key={question.id}
              index={index}
              question={question}
              value={answers[question.id]}
              error={state.fieldErrors[String(question.id)]?.join(" ")}
              onChange={(v) => setAnswers((a) => ({ ...a, [question.id]: v }))}
            />
          ))}
          {state.error && (
            <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">
              {state.error}
            </p>
          )}
          <Button type="submit" disabled={state.busy}>
            {state.busy ? "Submitting…" : "Submit answers"}
          </Button>
        </form>
      )}
    </section>
  );
}

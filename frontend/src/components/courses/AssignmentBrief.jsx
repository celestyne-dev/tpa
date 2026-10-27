import { CalendarClock, FileText, RotateCcw } from "lucide-react";
import { formatDateTimeLocal } from "@/utils/datetime";
import { ASSIGNMENT_KIND_LABEL } from "./assignmentLabels";

const FILE_RULE = {
  none: "No supporting documents.",
  optional: "Supporting documents (PDF or Word) are optional.",
  required: "Attach at least one supporting document (PDF or Word).",
};

/** What a learner reads before writing: instructions, prompts, requirements and deadline. */
export function AssignmentBrief({ assignment, attemptsAllowed, attemptsUsed, headingLevel = 2 }) {
  const Heading = `h${headingLevel}`;
  const req = assignment.requirements ?? {};
  const words = [
    req.min_words ? `at least ${req.min_words} words` : null,
    req.max_words ? `at most ${req.max_words} words` : null,
  ].filter(Boolean);
  const limit = attemptsAllowed ?? assignment.max_attempts;
  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
          {ASSIGNMENT_KIND_LABEL[assignment.kind] ?? "Assignment"}
          {assignment.required ? " · Required for completion" : " · Optional"}
        </p>
        <Heading className="mt-1 text-2xl font-medium sm:text-3xl">{assignment.title}</Heading>
      </div>
      {assignment.instructions && (
        <div className="leading-relaxed whitespace-pre-line text-ink">
          {assignment.instructions}
        </div>
      )}
      <ul className="space-y-2 rounded-2xl bg-cream p-4 text-sm">
        <li className="flex gap-2">
          <CalendarClock aria-hidden className="mt-0.5 size-4 shrink-0 text-sage-700" />
          <span>
            {assignment.due_at
              ? `Due ${formatDateTimeLocal(assignment.due_at)}${
                  assignment.late_policy === "block"
                    ? " — late submissions aren't accepted."
                    : " — late submissions are accepted and marked late."
                }`
              : "No deadline."}
            {assignment.available_from &&
              new Date(assignment.available_from) > new Date() &&
              ` Opens ${formatDateTimeLocal(assignment.available_from)}.`}
          </span>
        </li>
        <li className="flex gap-2">
          <RotateCcw aria-hidden className="mt-0.5 size-4 shrink-0 text-sage-700" />
          <span>
            {limit
              ? `${attemptsUsed != null ? `${attemptsUsed} of ${limit}` : `Up to ${limit}`} attempt${limit === 1 ? "" : "s"}${attemptsUsed != null ? " used" : ""}.`
              : "No attempt limit."}{" "}
            {assignment.resubmission_policy === "always"
              ? "You can resubmit after each grade."
              : assignment.resubmission_policy === "on_request"
                ? "You can resubmit when your reviewer asks for changes."
                : "One submission only."}
          </span>
        </li>
        <li className="flex gap-2">
          <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-sage-700" />
          <span>
            {words.length ? `Write ${words.join(" and ")} in total. ` : ""}
            {FILE_RULE[req.files ?? "optional"]}
            {req.files !== "none" && req.max_files ? ` Up to ${req.max_files} files.` : ""}
          </span>
        </li>
      </ul>
      {assignment.rubric && (
        <details className="rounded-2xl border border-charcoal/10 bg-white p-4">
          <summary className="cursor-pointer font-medium">
            How this is assessed ({assignment.rubric.total_points} points, pass at{" "}
            {assignment.rubric.passing_percent}%)
          </summary>
          <ul className="mt-3 space-y-2 text-sm">
            {assignment.rubric.criteria.map((c) => (
              <li key={c.id}>
                <span className="font-medium">{c.title}</span> — {c.max_points} points
                {c.description && <span className="block text-muted">{c.description}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

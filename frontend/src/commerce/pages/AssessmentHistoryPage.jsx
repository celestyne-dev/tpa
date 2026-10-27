import { ClipboardList } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { SUBMISSION_STATUS_LABEL } from "@/components/courses/assignmentLabels";
import { useShopApi } from "@/components/products/shopApiContext";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { routes } from "@/config/navigation";
import { formatDateTimeLocal } from "@/utils/datetime";
import { AccountShell } from "../AccountShell";
import { RequireCustomer } from "../RequireCustomer";

const STATE_LABEL = {
  not_started: "Not started",
  submitted: "Done",
  passed: "Passed",
  failed: "Not passed yet",
};
const FEEDBACK = new Set(["graded", "completed", "changes_requested"]);

/** Loads every active course's assessment history and assignments in parallel. */
function useHistory() {
  const shopApi = useShopApi();
  const [state, setState] = useState({ status: "loading", courses: [], error: null });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const learning = await shopApi.learning();
        const enrolled = learning.data.enrollments.filter((e) => e.access === "active");
        const courses = await Promise.all(
          enrolled.map(async (e) => {
            const [history, assignments] = await Promise.allSettled([
              shopApi.assessmentHistory(e.course.slug),
              shopApi.assignments(e.course.slug),
            ]);
            return {
              enrollment: e,
              assessments: history.status === "fulfilled" ? history.value.data.assessments : [],
              assignments: assignments.status === "fulfilled" ? assignments.value.data : [],
              failed: history.status === "rejected",
            };
          }),
        );
        if (live) setState({ status: "ready", courses, error: null });
      } catch (error) {
        if (live) setState({ status: "error", courses: [], error });
      }
    })();
    return () => {
      live = false;
    };
  }, [shopApi, version]);
  return [state, () => setVersion((v) => v + 1)];
}

function CourseHistory({ item }) {
  const { enrollment, assessments, assignments } = item;
  const slug = enrollment.course.slug;
  const headingId = `history-${slug}`;
  return (
    <section
      aria-labelledby={headingId}
      className="rounded-2xl border border-charcoal/10 bg-white p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={headingId} className="text-xl font-medium">
          <Link to={routes.learn(slug)} className="underline-offset-4 hover:underline">
            {enrollment.course.title}
          </Link>
        </h2>
        <p className="text-sm text-muted">
          {enrollment.completed_at
            ? `Course completed ${formatDateTimeLocal(enrollment.completed_at)}`
            : `Course progress ${enrollment.progress.percent}%`}
        </p>
      </div>
      {item.failed && (
        <p className="mt-2 text-sm text-red-800">
          We couldn&apos;t load this course&apos;s results.
        </p>
      )}
      {assessments.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-0 text-left text-sm">
            <caption className="sr-only">Assessments in {enrollment.course.title}</caption>
            <thead className="text-xs tracking-wide text-muted uppercase">
              <tr>
                <th scope="col" className="py-2 pr-3">
                  Assessment
                </th>
                <th scope="col" className="py-2 pr-3">
                  Result
                </th>
                <th scope="col" className="py-2">
                  Attempts
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-charcoal/[0.06] align-top">
              {assessments.map((a) => (
                <tr key={a.assessment_id}>
                  <th scope="row" className="py-3 pr-3 font-medium">
                    <Link
                      to={`/learn/${slug}/assessments/${a.assessment_id}`}
                      className="underline-offset-4 hover:underline"
                    >
                      {a.title}
                    </Link>
                    <span className="mt-1 block text-xs font-normal text-muted">
                      {a.practice
                        ? "Practice — doesn't count towards completion"
                        : a.kind === "quiz"
                          ? "Graded quiz"
                          : "Ungraded"}
                    </span>
                  </th>
                  <td className="py-3 pr-3">
                    {STATE_LABEL[a.status] ?? a.status}
                    {a.best_percent != null && (
                      <span className="block text-xs text-muted">Best {a.best_percent}%</span>
                    )}
                    {a.in_progress && (
                      <span className="block text-xs font-medium text-gold-700">
                        Attempt in progress
                      </span>
                    )}
                  </td>
                  <td className="py-3">
                    {a.attempts.length === 0 ? (
                      <span className="text-muted">None yet</span>
                    ) : (
                      <ul className="space-y-1">
                        {a.attempts.map((t) => (
                          <li key={t.id}>
                            {formatDateTimeLocal(t.submitted_at)}
                            {t.percent != null && ` · ${t.percent}%`}
                            {t.status === "expired" && " · time ran out"}
                          </li>
                        ))}
                      </ul>
                    )}
                    {a.attempts.length > 0 && (
                      <Link
                        to={`/learn/${slug}/assessments/${a.assessment_id}`}
                        className="mt-1 inline-block text-xs underline underline-offset-4"
                      >
                        View results and feedback
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {assignments.length > 0 && (
        <div className="mt-5">
          <h3 className="font-medium">Assignments</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {assignments.map((a) => (
              <li key={a.id} className="flex flex-wrap items-baseline gap-x-2">
                <Link
                  to={routes.learnAssignment(slug, a.id)}
                  className="font-medium underline underline-offset-4"
                >
                  {a.title}
                </Link>
                <span className="text-muted">
                  {SUBMISSION_STATUS_LABEL[a.status] ?? a.status}
                  {a.required ? "" : " · optional"}
                  {FEEDBACK.has(a.status) ? " · feedback available" : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {assessments.length === 0 && assignments.length === 0 && !item.failed && (
        <p className="mt-2 text-sm text-muted">This course has no assessments.</p>
      )}
    </section>
  );
}

function HistoryList() {
  const [state, reload] = useHistory();
  if (state.status === "loading") return <p role="status">Loading your results…</p>;
  if (state.status === "error")
    return <ErrorState title="We couldn't load your results" onRetry={reload} />;
  if (!state.courses.length)
    return (
      <EmptyState
        icon={ClipboardList}
        title="No results yet"
        description="Quizzes, practice exams and assignments from your courses appear here."
        action={
          <Link to={routes.accountLearning} className="underline underline-offset-4">
            My learning
          </Link>
        }
      />
    );
  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-sm text-muted">
        Practice exams are for preparation only: they never count towards course completion or
        certificates.
      </p>
      {state.courses.map((item) => (
        <CourseHistory key={item.enrollment.course.slug} item={item} />
      ))}
    </div>
  );
}

export function AssessmentHistoryPage() {
  return (
    <RequireCustomer>
      <AccountShell title="Assessment results" path={routes.assessmentHistory}>
        <HistoryList />
      </AccountShell>
    </RequireCustomer>
  );
}

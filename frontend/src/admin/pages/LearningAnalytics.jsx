import { GraduationCap } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../adminApiContext";
import { SelectField, TextField } from "../components/Fields";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { RankTable, Stat } from "./analyticsParts";

const PRESETS = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "365d", label: "Last 12 months" },
  { value: "custom", label: "Custom range" },
];
const ACCESS_LABEL = {
  free: "Free",
  purchase: "Purchased",
  membership: "Membership",
  manual: "Granted by staff",
};
const TYPE_LABEL = {
  quiz: "Graded quizzes",
  timed: "Timed assessments",
  practice: "Practice",
  ungraded: "Reflections / self-assessments",
};
const pct = (v) => (v == null ? "—" : `${v}%`);

/** Enrollment / start / completion counts per period, drawn from the reported numbers. */
function LearningTrend({ trend }) {
  const max = Math.max(1, ...trend.map((t) => t.enrollments));
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Enrollments, starts and completions per period</caption>
      <thead className="text-muted">
        <tr>
          <th scope="col" className="w-28">
            Period
          </th>
          <th scope="col">Enrollments</th>
          <th scope="col" className="text-right">
            Starts
          </th>
          <th scope="col" className="text-right">
            Completions
          </th>
        </tr>
      </thead>
      <tbody>
        {trend.map((t) => (
          <tr key={t.period}>
            <td className="py-0.5 pr-2 whitespace-nowrap">{t.period}</td>
            <td className="py-0.5">
              <div className="flex items-center gap-2">
                <div
                  aria-hidden
                  className="h-3 rounded bg-sage-600"
                  style={{
                    width: `${(t.enrollments / max) * 100}%`,
                    minWidth: t.enrollments ? 2 : 0,
                  }}
                />
                <span>{t.enrollments}</span>
              </div>
            </td>
            <td className="py-0.5 text-right">{t.starts}</td>
            <td className="py-0.5 text-right">{t.completions}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Course and assessment performance from existing LMS records (courses.view_reports). */
export function LearningAnalytics() {
  const api = useAdminApi();
  const [preset, setPreset] = useState("30d");
  const [custom, setCustom] = useState({ date_from: "", date_to: "" });
  const [course, setCourse] = useState("");
  const [granularity, setGranularity] = useState("");
  const params = {
    ...(preset === "custom"
      ? Object.fromEntries(Object.entries(custom).filter(([, v]) => v))
      : { range: preset }),
    ...(course ? { course } : {}),
    ...(granularity ? { granularity } : {}),
  };
  const { data, error, loading, reload } = useAdminQuery(
    () => api.learningAnalytics(params),
    [JSON.stringify(params)],
  );
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField
          label="Time period"
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
          options={PRESETS}
        />
        {preset === "custom" && (
          <>
            <TextField
              label="First day"
              type="date"
              value={custom.date_from}
              onChange={(e) => setCustom((c) => ({ ...c, date_from: e.target.value }))}
            />
            <TextField
              label="Last day"
              type="date"
              value={custom.date_to}
              onChange={(e) => setCustom((c) => ({ ...c, date_to: e.target.value }))}
            />
          </>
        )}
        <SelectField
          label="Course"
          value={course}
          onChange={(e) => setCourse(e.target.value)}
          options={[
            { value: "", label: "All courses" },
            ...(data?.course_options ?? []).map((c) => ({ value: String(c.id), label: c.title })),
          ]}
        />
        <SelectField
          label="Group trend by"
          value={granularity}
          onChange={(e) => setGranularity(e.target.value)}
          options={[
            { value: "", label: "Automatic" },
            { value: "day", label: "Day" },
            { value: "week", label: "Week" },
            { value: "month", label: "Month" },
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load learning analytics" onRetry={reload} />
      ) : loading || !data ? (
        <p role="status" className="text-muted">
          Loading…
        </p>
      ) : !data.has_data ? (
        <EmptyState
          icon={GraduationCap}
          title="No enrollments yet"
          description="Learning figures appear once learners enrol in a course."
        />
      ) : (
        <>
          <section
            aria-label="Learning overview"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <Stat
              label="Current enrollments"
              value={data.current.enrollments}
              hint={Object.entries(data.current.by_access)
                .filter(([, n]) => n)
                .map(([k, n]) => `${ACCESS_LABEL[k]} ${n}`)
                .join(" · ")}
            />
            <Stat
              label="Started / completed"
              value={`${data.current.started} / ${data.current.completed}`}
              hint={`${data.current.unfinished} unfinished · ${data.current.not_started} not started`}
            />
            <Stat
              label="Completion rate"
              value={pct(data.current.completion_rate)}
              hint={`${pct(data.current.completion_rate_of_started)} of learners who started`}
            />
            <Stat
              label="Active learners (period)"
              value={data.period.active_learners}
              hint="At least this many: see definitions below"
            />
          </section>
          <section aria-label="This period" className="grid gap-3 sm:grid-cols-3">
            <Stat label="New enrollments" value={data.period.new_enrollments} />
            <Stat label="Courses started" value={data.period.starts} />
            <Stat label="Courses completed" value={data.period.completions} />
          </section>
          <section
            aria-labelledby="learning-trend"
            className="rounded-xl border border-charcoal/10 bg-white p-4"
          >
            <h2 id="learning-trend" className="mb-2 text-base font-semibold">
              Enrollment and completion trend ({data.range.from} to {data.range.to})
            </h2>
            <LearningTrend trend={data.trend} />
          </section>
          <RankTable
            caption="Course performance"
            rows={data.courses}
            columns={[
              { header: "Course", render: (r) => r.title },
              { header: "Enrolled", numeric: true, render: (r) => r.enrollments },
              { header: "Started", numeric: true, render: (r) => r.started },
              {
                header: "Completed",
                numeric: true,
                render: (r) => `${r.completed} (${pct(r.completion_rate)})`,
              },
              { header: "Avg progress", numeric: true, render: (r) => pct(r.average_progress) },
              { header: "Assignments", numeric: true, render: (r) => r.assignment_submissions },
              { header: "Avg best score", numeric: true, render: (r) => pct(r.average_best_score) },
            ]}
          />
          {data.lessons ? (
            <RankTable
              caption="Lesson progress"
              rows={data.lessons.items}
              empty="This course has no published lessons."
              columns={[
                { header: "Lesson", render: (r) => r.title },
                { header: "Viewed", numeric: true, render: (r) => r.viewed },
                {
                  header: "Completed",
                  numeric: true,
                  render: (r) => `${r.completed} (${pct(r.completion_rate_of_started)})`,
                },
                {
                  header: "Unfinished learners stopped here",
                  numeric: true,
                  render: (r) => r.unfinished_stopped_here,
                },
              ]}
            />
          ) : (
            <p className="text-sm text-muted">
              Choose a course to see lesson progress and dropout points.
            </p>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <RankTable
              caption="Assessment performance"
              rows={Object.entries(data.assessments.by_type).map(([type, v]) => ({ type, ...v }))}
              columns={[
                { header: "Type", render: (r) => TYPE_LABEL[r.type] ?? r.type },
                { header: "Attempts", numeric: true, render: (r) => r.attempts },
                { header: "Learners", numeric: true, render: (r) => r.participants },
                { header: "Pass rate", numeric: true, render: (r) => pct(r.pass_rate) },
                { header: "Avg score", numeric: true, render: (r) => pct(r.average_percent) },
              ]}
            />
            <section
              aria-label="Assignments and grading"
              className="rounded-xl border border-charcoal/10 bg-white p-4 text-sm"
            >
              <h2 className="text-base font-semibold">Assignments and grading</h2>
              {data.assignments.available ? (
                <dl className="mt-2 grid grid-cols-2 gap-2">
                  <dt>Submitted (period)</dt>
                  <dd>
                    {data.assignments.submitted} ({data.assignments.submitted_late} late)
                  </dd>
                  <dt>Graded (period)</dt>
                  <dd>{data.assignments.graded}</dd>
                  <dt>Passed / failed</dt>
                  <dd>
                    {data.assignments.passed} / {data.assignments.failed} (
                    {pct(data.assignments.pass_rate)})
                  </dd>
                  <dt>Average grade</dt>
                  <dd>{pct(data.assignments.average_percent)}</dd>
                  <dt>Waiting for grading now</dt>
                  <dd>{data.assignments.pending_grading}</dd>
                  <dt>Waiting for resubmission</dt>
                  <dd>{data.assignments.awaiting_resubmission}</dd>
                </dl>
              ) : (
                <p className="mt-2 text-muted">{data.assignments.reason}</p>
              )}
            </section>
          </div>
        </>
      )}
      {data && (
        <section aria-label="Learning definitions" className="rounded-xl bg-cream p-4 text-sm">
          <h2 className="font-semibold">How these are defined</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {Object.values(data.definitions).map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

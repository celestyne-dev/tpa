import { ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { SUBMISSION_STATUS_LABEL } from "@/components/courses/assignmentLabels";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTimeLocal } from "@/utils/datetime";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { SelectField } from "../../components/Fields";
import { useAdminQuery } from "../../hooks/useAdminQuery";

const FILTERS = [
  { value: "awaiting", label: "Awaiting review (pending, resubmitted, in review)" },
  { value: "pending_review", label: "Pending — not opened yet" },
  { value: "resubmitted", label: "Resubmitted" },
  { value: "under_review", label: "Under review" },
  { value: "changes_requested", label: "Changes requested" },
  { value: "graded", label: "Graded (not passed)" },
  { value: "completed", label: "Completed (passed)" },
  { value: "", label: "All submissions" },
];

const GRADE_LABEL = { draft: "Draft grade", published: "Released", retracted: "Retracted" };

/** Instructor dashboard: submissions across the courses this user may review. */
export function GradingDashboardPage() {
  const api = useAdminApi();
  const [status, setStatus] = useState("awaiting");
  const [courseId, setCourseId] = useState("");
  const { data, error, loading, reload } = useAdminQuery(
    () =>
      api.assignments.queue({
        ...(status && { status }),
        ...(courseId && { course_id: courseId }),
      }),
    [status, courseId],
  );
  const columns = [
    {
      key: "learner",
      header: "Learner",
      render: (r) => (
        <Link
          to={`/admin/assignment-reviews/${r.id}`}
          className="font-medium underline-offset-4 hover:underline"
        >
          {r.learner.name || r.learner.email || "Learner"}
          <span className="block text-xs font-normal text-muted">{r.learner.email}</span>
        </Link>
      ),
    },
    {
      key: "assignment",
      header: "Assignment",
      render: (r) => (
        <>
          {r.assignment.title}
          <span className="block text-xs text-muted">{r.course.title}</span>
        </>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <>
          {SUBMISSION_STATUS_LABEL[r.status] ?? r.status}
          {r.grade_status && (
            <span className="block text-xs text-muted">{GRADE_LABEL[r.grade_status]}</span>
          )}
        </>
      ),
    },
    {
      key: "submitted",
      header: "Submitted",
      render: (r) => (
        <>
          {formatDateTimeLocal(r.submitted_at)}
          {r.late && <span className="ml-1 text-xs font-semibold text-gold-700">Late</span>}
          <span className="block text-xs text-muted">Attempt {r.attempts}</span>
        </>
      ),
    },
  ];
  return (
    <>
      <AdminPageHeader
        title="Assignment reviews"
        description="Submissions from the courses you manage or are an assessor for."
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:max-w-3xl">
        <SelectField
          label="Show"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          options={FILTERS}
        />
        <SelectField
          label="Course"
          value={courseId}
          onChange={(e) => setCourseId(e.target.value)}
          options={[
            { value: "", label: "All my courses" },
            ...(data?.courses ?? []).map((c) => ({ value: String(c.id), label: c.title })),
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load submissions" onRetry={reload} />
      ) : (
        <>
          <p aria-live="polite" className="mb-2 text-sm text-muted">
            {loading ? "Loading submissions…" : `${data?.items.length ?? 0} submissions`}
            {data?.truncated && " (showing the oldest 200; filter by course to see more)"}
          </p>
          <DataTable
            caption="Submissions"
            columns={columns}
            rows={data?.items}
            loading={loading}
            empty={{
              icon: ClipboardCheck,
              title: "Nothing waiting for you",
              description: "New submissions from your courses appear here.",
            }}
          />
        </>
      )}
    </>
  );
}

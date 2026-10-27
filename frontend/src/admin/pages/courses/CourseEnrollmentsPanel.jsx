import { Users } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { DataTable } from "../../components/DataTable";
import { fieldError } from "../../components/fieldError";
import { SelectField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { toPagination } from "./courseAdmin";

const ACCESS_LABEL = {
  active: "Active",
  revoked: "Ended by staff",
  expired: "Access period over",
  ended: "Purchase refunded/revoked",
};

function ReasonForm({ label, onSubmit, children }) {
  const [reason, setReason] = useState("");
  const [extra, setExtra] = useState("");
  const [error, setError] = useState(null);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await onSubmit(reason, extra);
          setReason("");
          setExtra("");
        } catch (err) {
          setError(err);
        }
      }}
      className="flex flex-wrap items-end gap-2"
    >
      {children?.(extra, setExtra, error)}
      <TextField
        label={children ? "Note (why)" : "Reason"}
        value={reason}
        error={
          fieldError(error, "reason") ??
          fieldError(error, "note") ??
          (error && !error.details ? error.message : undefined)
        }
        onChange={(e) => setReason(e.target.value)}
      />
      <Button type="submit" size="sm" variant="outline" disabled={!reason.trim()}>
        {label}
      </Button>
    </form>
  );
}

function EnrollmentDetail({ course, enrollmentId, onClose, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, setData, reload } = useAdminQuery(
    () => api.courses.enrollment(course.id, enrollmentId),
    [enrollmentId],
  );
  const canManage = course.can.manage_enrollments;
  const act = async (action, reason) => {
    const res = await api.courses.enrollmentAction(course.id, enrollmentId, action, { reason });
    setData(res.data);
    notify(action === "revoke" ? "Enrolment ended." : "Enrolment restored.");
    onChanged();
  };
  const certificate = async (action, body) => {
    await api.courses.certificateAction(data.certificate.code, action, body);
    notify("Certificate updated.");
    reload();
  };
  return (
    <Modal open onClose={onClose} title={data ? data.learner.email : "Learner"} size="lg">
      {!data ? (
        <p role="status">Loading…</p>
      ) : (
        <div className="space-y-5 text-sm">
          <p>
            {data.learner.name || "No name"} · enrolled {formatDateTime(data.enrolled_at)} via{" "}
            {data.source} · {ACCESS_LABEL[data.access]}
            {data.revoked_reason ? ` (${data.revoked_reason})` : ""}
          </p>
          <p>
            Progress {data.progress.percent}% · {data.progress.completed_lessons}/
            {data.progress.required_lessons} lessons · {data.progress.completed_assessments}/
            {data.progress.required_assessments} assessments
            {data.completed_at ? ` · completed ${formatDateTime(data.completed_at)}` : ""}
          </p>
          <div className="overflow-x-auto rounded-xl border border-charcoal/10">
            <table className="w-full">
              <caption className="p-2 text-left font-medium">Lessons</caption>
              <thead className="text-left text-muted">
                <tr>
                  <th className="px-3 py-1.5">Lesson</th>
                  <th className="px-3 py-1.5">Last opened</th>
                  <th className="px-3 py-1.5">Completed</th>
                </tr>
              </thead>
              <tbody>
                {data.lessons.map((l) => (
                  <tr key={l.id} className="border-t border-charcoal/5">
                    <td className="px-3 py-1.5">{l.title}</td>
                    <td className="px-3 py-1.5">
                      {l.viewed_at ? formatDateTime(l.viewed_at) : "—"}
                    </td>
                    <td className="px-3 py-1.5">
                      {l.completed_at ? formatDateTime(l.completed_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.assessments.length > 0 && (
            <ul className="space-y-1">
              {data.assessments.map((a) => (
                <li key={a.id}>
                  <span className="font-medium">{a.title}</span> — {a.status.replace("_", " ")}
                  {a.attempts.length > 0 &&
                    ` · ${a.attempts.length} attempt(s)${a.attempts.some((t) => t.percent != null) ? `, best ${Math.max(...a.attempts.map((t) => t.percent ?? 0))}%` : ""}`}
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted">
            Learners' private exercise notes and written reflection answers are not shown here.
          </p>
          {data.certificate && (
            <div className="space-y-3 rounded-xl bg-sage-50 p-4">
              <p>
                Certificate {data.certificate.code} · issued to {data.certificate.recipient_name} ·{" "}
                <StatusBadge status={data.certificate.status} />
              </p>
              {canManage && (
                <>
                  <ReasonForm
                    label="Correct name"
                    onSubmit={(note, name) =>
                      certificate("correct", { recipient_name: name, note })
                    }
                  >
                    {(name, setName, error) => (
                      <TextField
                        label="Correct name"
                        value={name}
                        error={fieldError(error, "name")}
                        onChange={(e) => setName(e.target.value)}
                      />
                    )}
                  </ReasonForm>
                  {data.certificate.status === "valid" ? (
                    <ReasonForm
                      label="Revoke certificate"
                      onSubmit={(reason) => certificate("revoke", { reason })}
                    />
                  ) : (
                    <ReasonForm
                      label="Reinstate certificate"
                      onSubmit={(reason) => certificate("reinstate", { reason })}
                    />
                  )}
                </>
              )}
            </div>
          )}
          {canManage &&
            (data.status === "active" ? (
              <ReasonForm label="End enrolment" onSubmit={(reason) => act("revoke", reason)} />
            ) : (
              <ReasonForm label="Restore enrolment" onSubmit={(reason) => act("restore", reason)} />
            ))}
        </div>
      )}
    </Modal>
  );
}

/** Learners of one course: progress, completion, certificates and manual enrolment. */
export function CourseEnrollmentsPanel({ course }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [filters, setFilters] = useState({ q: "", status: "", page: 1 });
  const [open, setOpen] = useState(null);
  const [form, setForm] = useState({ email: "", reason: "" });
  const [error, setError] = useState(null);
  const {
    data,
    meta,
    error: loadError,
    loading,
    reload,
  } = useAdminQuery(
    () =>
      api.courses.enrollments(
        course.id,
        Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")),
      ),
    [filters.q, filters.status, filters.page],
  );
  const report = useAdminQuery(
    () =>
      course.can.view_reports
        ? api.courses.courseReports(course.id)
        : Promise.resolve({ data: null }),
    [],
  );
  const enroll = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      await api.courses.enroll(course.id, form);
      setForm({ email: "", reason: "" });
      notify("Learner enrolled.");
      reload();
    } catch (err) {
      setError(err);
    }
  };
  const stats = report.data?.per_course?.[0];
  return (
    <div className="space-y-5">
      {stats && (
        <div className="grid gap-3 sm:grid-cols-4">
          {[
            ["Active learners", stats.learners],
            ["Completions", stats.completions],
            [
              "Average progress",
              stats.average_progress == null ? "—" : `${stats.average_progress}%`,
            ],
            ["Certificates", report.data.enrollments.certificates_issued],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-charcoal/10 bg-white p-4">
              <p className="text-sm text-muted">{label}</p>
              <p className="mt-1 text-2xl font-semibold">{value}</p>
            </div>
          ))}
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          label="Search learners"
          type="search"
          value={filters.q}
          onChange={(e) => setFilters({ ...filters, q: e.target.value, page: 1 })}
        />
        <SelectField
          label="Show"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value, page: 1 })}
          options={[
            { value: "", label: "Everyone" },
            { value: "in_progress", label: "In progress" },
            { value: "completed", label: "Completed" },
            { value: "active", label: "Active enrolments" },
            { value: "revoked", label: "Ended by staff" },
          ]}
        />
      </div>
      {loadError ? (
        <ErrorState title="We couldn't load learners" onRetry={reload} />
      ) : (
        <>
          <DataTable
            caption="Learners"
            loading={loading}
            rows={data}
            empty={{
              icon: Users,
              title: "No learners yet",
              description: "Enrolments appear here as people join the course.",
            }}
            columns={[
              {
                key: "learner",
                header: "Learner",
                render: (r) => (
                  <button
                    type="button"
                    className="text-left font-medium hover:underline"
                    onClick={() => setOpen(r.id)}
                  >
                    {r.learner.name || r.learner.email}
                    <span className="block text-xs font-normal text-muted">{r.learner.email}</span>
                  </button>
                ),
              },
              { key: "source", header: "Source", render: (r) => r.source },
              { key: "access", header: "Access", render: (r) => ACCESS_LABEL[r.access] },
              {
                key: "progress",
                header: "Progress",
                render: (r) => `${r.progress_percent}%${r.completed_at ? " · completed" : ""}`,
              },
              {
                key: "activity",
                header: "Last activity",
                render: (r) => (r.last_activity_at ? formatDateTime(r.last_activity_at) : "—"),
              },
            ]}
          />
          <Pagination
            pagination={toPagination(meta)}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
      {course.can.manage_enrollments && (
        <form
          onSubmit={enroll}
          className="grid gap-3 rounded-2xl bg-cream/60 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        >
          <TextField
            label="Enrol an existing customer (email)"
            type="email"
            value={form.email}
            error={fieldError(error, "email")}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <TextField
            label="Reason"
            hint="Recorded in the audit log."
            value={form.reason}
            error={
              fieldError(error, "reason") ?? (error && !error.details ? error.message : undefined)
            }
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
          <Button type="submit" disabled={!form.email.trim() || !form.reason.trim()}>
            Enrol
          </Button>
        </form>
      )}
      {open && (
        <EnrollmentDetail
          course={course}
          enrollmentId={open}
          onClose={() => setOpen(null)}
          onChanged={reload}
        />
      )}
    </div>
  );
}

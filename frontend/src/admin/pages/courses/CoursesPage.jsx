import { GraduationCap, Plus, Tags } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { fieldError } from "../../components/fieldError";
import { CheckboxField, SelectField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { toPagination } from "./courseAdmin";

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-charcoal/10 bg-white p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value ?? "—"}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

/** Course dashboard: real counts from the database (no estimates). */
export function CourseStats({ report }) {
  if (!report) return null;
  const e = report.enrollments;
  return (
    <section aria-label="Course statistics" className="mb-6 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Courses"
          value={report.courses.total}
          hint={`${report.courses.published} published · ${report.courses.draft} drafts · ${report.courses.scheduled} scheduled`}
        />
        <Stat
          label="Enrolments"
          value={e.enrollments}
          hint={`${e.active_enrollments} active · ${e.new_enrollments_30d} in the last 30 days`}
        />
        <Stat label="Active learners (30 days)" value={e.active_learners_30d} />
        <Stat
          label="Completions"
          value={e.completions}
          hint={
            e.completion_rate == null
              ? "No enrolments yet"
              : `${e.completion_rate}% completion rate · ${e.certificates_issued} certificates`
          }
        />
      </div>
      {report.assessment_pass_rates.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-charcoal/10 bg-white">
          <table className="w-full text-sm">
            <caption className="p-3 text-left font-medium">Quiz pass rates</caption>
            <thead className="border-b border-charcoal/10 text-left text-muted">
              <tr>
                <th className="px-3 py-2">Quiz</th>
                <th className="px-3 py-2">Learners</th>
                <th className="px-3 py-2">Passed</th>
                <th className="px-3 py-2">Attempts</th>
                <th className="px-3 py-2">Pass rate</th>
              </tr>
            </thead>
            <tbody>
              {report.assessment_pass_rates.map((row) => (
                <tr key={row.assessment_id} className="border-b border-charcoal/5">
                  <td className="px-3 py-2">{row.title}</td>
                  <td className="px-3 py-2">{row.learners}</td>
                  <td className="px-3 py-2">{row.passed}</td>
                  <td className="px-3 py-2">{row.attempts}</td>
                  <td className="px-3 py-2">{row.pass_rate}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CreateCourseDialog({ onClose }) {
  const api = useAdminApi();
  const navigate = useNavigate();
  const notify = useNotify();
  const [form, setForm] = useState({ title: "", summary: "", access_type: "free" });
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      const res = await api.courses.create(form);
      notify("Course created as a draft. Add modules and lessons, then publish.");
      navigate(`/admin/courses/${res.data.id}/content`);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="New course"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-course" disabled={!form.title.trim()}>
            Create draft
          </Button>
        </>
      }
    >
      <form id="create-course" onSubmit={submit} className="space-y-4">
        <TextField
          label="Title"
          required
          value={form.title}
          error={fieldError(error, "title")}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <TextField
          label="Short summary"
          hint="Shown in the catalogue and search results (up to 400 characters)."
          value={form.summary}
          error={fieldError(error, "summary")}
          onChange={(e) => setForm({ ...form, summary: e.target.value })}
        />
        <SelectField
          label="Access"
          value={form.access_type}
          onChange={(e) => setForm({ ...form, access_type: e.target.value })}
          options={[
            { value: "free", label: "Free (verified account required)" },
            { value: "premium", label: "Premium (sold through a course product)" },
          ]}
        />
      </form>
    </Modal>
  );
}

function CategoriesDialog({ onClose }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, reload } = useAdminQuery(() => api.courses.categories(), []);
  const [form, setForm] = useState({ name: "", description: "" });
  const [error, setError] = useState(null);
  const add = async (event) => {
    event.preventDefault();
    setError(null);
    try {
      await api.courses.createCategory(form);
      setForm({ name: "", description: "" });
      notify("Category added.");
      reload();
    } catch (err) {
      setError(err);
    }
  };
  const toggle = async (category) => {
    await api.courses.updateCategory(category.id, { is_active: !category.is_active });
    reload();
  };
  const remove = async (category) => {
    try {
      await api.courses.removeCategory(category.id);
      reload();
    } catch (err) {
      notify(err.message, "error");
    }
  };
  return (
    <Modal open onClose={onClose} title="Course categories" size="lg">
      <ul className="divide-y divide-charcoal/10">
        {(data ?? []).map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>
              <span className="font-medium">{c.name}</span>{" "}
              <span className="text-sm text-muted">
                · {c.course_count} {c.course_count === 1 ? "course" : "courses"}
              </span>
            </span>
            <span className="flex gap-2">
              <CheckboxField label="Active" checked={c.is_active} onChange={() => toggle(c)} />
              {c.course_count === 0 && (
                <Button size="sm" variant="outline" onClick={() => remove(c)}>
                  Delete
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <TextField
          label="New category"
          value={form.name}
          error={fieldError(error, "name")}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <TextField
          label="Description (optional)"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        <Button type="submit" disabled={!form.name.trim()}>
          Add
        </Button>
      </form>
    </Modal>
  );
}

/** Courses module: list, filters, categories and the real-data course dashboard. */
export function CoursesPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [filters, setFilters] = useState({ q: "", status: "", access: "", page: 1 });
  const location = useLocation();
  const [dialog, setDialog] = useState(() =>
    location.pathname.endsWith("/new") && can("courses.create") ? "create" : null,
  );
  const { data, meta, error, loading, reload } = useAdminQuery(
    () =>
      api.courses.list(
        Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "" && v != null)),
      ),
    [filters.q, filters.status, filters.access, filters.page],
  );
  const reports = useAdminQuery(
    () => (can("courses.view_reports") ? api.courses.reports() : Promise.resolve({ data: null })),
    [],
  );
  const set = (patch) => setFilters({ ...filters, page: 1, ...patch });

  return (
    <>
      <AdminPageHeader
        title="Courses"
        description="Self-paced, text-based courses: modules of written lessons, exercises, quizzes and worksheets. Prices and checkout come from the linked course product."
        breadcrumbs={[{ label: "Courses" }]}
        actions={
          <div className="flex flex-wrap gap-2">
            {can("courses.edit") && (
              <Button variant="outline" onClick={() => setDialog("categories")}>
                <Tags aria-hidden /> Categories
              </Button>
            )}
            {can("courses.create") && (
              <Button onClick={() => setDialog("create")}>
                <Plus aria-hidden /> New course
              </Button>
            )}
          </div>
        }
      />
      <CourseStats report={reports.data} />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <TextField
          label="Search"
          type="search"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
        />
        <SelectField
          label="Status"
          value={filters.status}
          onChange={(e) => set({ status: e.target.value })}
          options={[
            { value: "", label: "All (not archived)" },
            { value: "draft", label: "Drafts" },
            { value: "scheduled", label: "Scheduled" },
            { value: "published", label: "Published" },
            { value: "archived", label: "Archived" },
          ]}
        />
        <SelectField
          label="Access"
          value={filters.access}
          onChange={(e) => set({ access: e.target.value })}
          options={[
            { value: "", label: "Free and premium" },
            { value: "free", label: "Free" },
            { value: "premium", label: "Premium" },
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load courses" onRetry={reload} />
      ) : (
        <>
          <DataTable
            caption="Courses"
            loading={loading}
            rows={data}
            empty={{
              icon: GraduationCap,
              title: "No courses yet",
              description: "Create a course, add modules and lessons, then publish it.",
            }}
            columns={[
              {
                key: "title",
                header: "Course",
                render: (c) => (
                  <Link to={`/admin/courses/${c.id}`} className="font-medium hover:underline">
                    {c.title}
                    <span className="block text-xs font-normal text-muted">
                      {c.category?.name ?? "No category"} · {c.published_lesson_count}/
                      {c.lesson_count} lessons published
                    </span>
                  </Link>
                ),
              },
              {
                key: "access",
                header: "Access",
                render: (c) =>
                  `${c.access_type === "free" ? "Free" : "Premium"}${c.availability === "coming_soon" ? " · coming soon" : ""}`,
              },
              {
                key: "learners",
                header: "Learners",
                render: (c) => `${c.enrollment_count} (${c.completion_count} completed)`,
              },
              { key: "status", header: "Status", render: (c) => <StatusBadge status={c.status} /> },
              { key: "updated", header: "Updated", render: (c) => formatDateTime(c.updated_at) },
            ]}
          />
          <Pagination
            pagination={toPagination(meta)}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
      {dialog === "create" && <CreateCourseDialog onClose={() => setDialog(null)} />}
      {dialog === "categories" && <CategoriesDialog onClose={() => setDialog(null)} />}
    </>
  );
}

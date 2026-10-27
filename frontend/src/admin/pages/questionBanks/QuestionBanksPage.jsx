import { Library, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { formatDateTimeLocal } from "@/utils/datetime";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { DataTable } from "../../components/DataTable";
import { SelectField, TextAreaField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";

/** Reusable question banks shared by every course's quizzes and practice exams. */
export function QuestionBanksPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const { can } = usePermissions();
  const canManage = can("question_banks.manage");
  const [status, setStatus] = useState("active");
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useAdminQuery(
    () => api.questionBanks.list({ ...(status && { status }), ...(q && { q }), page_size: 100 }),
    [status, q],
  );
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", description: "" });
  const [createError, setCreateError] = useState(null);
  const create = async (event) => {
    event.preventDefault();
    setCreateError(null);
    try {
      const res = await api.questionBanks.create(form);
      notify("Question bank created.");
      navigate(`/admin/question-banks/${res.data.id}`);
    } catch (err) {
      setCreateError(err);
    }
  };
  const columns = [
    {
      key: "title",
      header: "Bank",
      render: (b) => (
        <Link
          to={`/admin/question-banks/${b.id}`}
          className="font-medium underline-offset-4 hover:underline"
        >
          {b.title}
          {b.description && (
            <span className="block text-xs font-normal text-muted">{b.description}</span>
          )}
        </Link>
      ),
    },
    {
      key: "questions",
      header: "Questions",
      render: (b) =>
        `${b.question_counts.active} active${b.question_counts.retired ? `, ${b.question_counts.retired} retired` : ""}`,
    },
    { key: "status", header: "Status", render: (b) => <StatusBadge status={b.status} /> },
    { key: "updated", header: "Updated", render: (b) => formatDateTimeLocal(b.updated_at) },
  ];
  return (
    <>
      <AdminPageHeader
        title="Question banks"
        description="Reusable questions that quizzes and practice exams draw from."
        actions={
          canManage && (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus aria-hidden /> New bank
            </Button>
          )
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:max-w-2xl">
        <TextField
          label="Search banks"
          type="search"
          value={q}
          maxLength={100}
          onChange={(e) => setQ(e.target.value)}
        />
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          options={[
            { value: "active", label: "Active" },
            { value: "archived", label: "Archived" },
            { value: "", label: "All" },
          ]}
        />
      </div>
      {error ? (
        <ErrorState title="We couldn't load the question banks" onRetry={reload} />
      ) : (
        <DataTable
          caption="Question banks"
          columns={columns}
          rows={data}
          loading={loading}
          empty={{
            icon: Library,
            title: "No question banks yet",
            description: canManage ? "Create a bank, then add questions to it." : "",
          }}
        />
      )}
      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="New question bank"
        footer={
          <>
            <Button variant="outline" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button type="submit" form="new-bank" disabled={!form.title.trim()}>
              Create bank
            </Button>
          </>
        }
      >
        <form id="new-bank" onSubmit={create} className="space-y-3">
          <ErrorSummary error={createError} />
          <TextField
            label="Title"
            required
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <TextAreaField
            label="Description (optional)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </form>
      </Modal>
    </>
  );
}

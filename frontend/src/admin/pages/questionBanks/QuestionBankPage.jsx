import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { ErrorSummary } from "@/components/ui/ErrorSummary";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { SelectField, TextAreaField, TextField } from "../../components/Fields";
import { Pagination } from "../../components/Pagination";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { QuestionEditor } from "../courses/CourseAssessmentsPanel";
import { QUESTION_KINDS, toPagination } from "../courses/courseAdmin";

const KINDS = QUESTION_KINDS.bank;
const kindLabel = (kind) => KINDS.find((k) => k.value === kind)?.label ?? kind;

function BankDetails({ bank, canManage, onSaved, onDeleted }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [form, setForm] = useState({ title: bank.title, description: bank.description });
  const [error, setError] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const dirty = form.title !== bank.title || form.description !== bank.description;
  const save = async (patch, message) => {
    setError(null);
    try {
      const res = await api.questionBanks.update(bank.id, {
        ...patch,
        lock_version: bank.lock_version,
      });
      notify(message);
      onSaved(res.data);
    } catch (err) {
      setError(err);
    } finally {
      setConfirm(null);
    }
  };
  const remove = async () => {
    try {
      await api.questionBanks.remove(bank.id);
      notify("Question bank deleted.");
      onDeleted();
    } catch (err) {
      setError(err);
      setConfirm(null);
    }
  };
  return (
    <section aria-labelledby="bank-details" className="space-y-4">
      <h2 id="bank-details" className="sr-only">
        Bank details
      </h2>
      <ErrorSummary error={error} />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save(form, "Question bank saved.");
        }}
        className="grid gap-4 lg:max-w-3xl"
      >
        <fieldset disabled={!canManage} className="grid gap-4">
          <legend className="sr-only">Title and description</legend>
          <TextField
            label="Title"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <TextAreaField
            label="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </fieldset>
        {canManage && (
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" disabled={!dirty}>
              Save details
            </Button>
            {bank.status === "active" ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setConfirm("archive")}
              >
                Archive bank
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => save({ status: "active" }, "Question bank restored.")}
              >
                Restore bank
              </Button>
            )}
            {bank.used_by.length === 0 && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setConfirm("delete")}
              >
                <Trash2 aria-hidden /> Delete bank
              </Button>
            )}
          </div>
        )}
      </form>
      <div className="rounded-xl bg-cream/60 p-4 text-sm">
        <p className="font-medium">Used by</p>
        {bank.used_by.length ? (
          <ul className="mt-1 list-disc pl-5">
            {bank.used_by.map((a) => (
              <li key={a.assessment_id}>
                <Link
                  to={`/admin/courses/${a.course_id}/assessments`}
                  className="underline underline-offset-4"
                >
                  {a.title}
                </Link>{" "}
                ({a.status})
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted">No assessment draws from this bank yet.</p>
        )}
      </div>
      <ConfirmDialog
        open={confirm === "archive"}
        title="Archive this bank?"
        message="It can no longer be chosen for new draws. Attempts already started keep their questions. Banks used by published assessments can't be archived."
        confirmLabel="Archive"
        onConfirm={() => save({ status: "archived" }, "Question bank archived.")}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "delete"}
        title="Delete this bank and its questions?"
        message="No assessment uses it. This can't be undone."
        confirmLabel="Delete"
        tone="danger"
        onConfirm={remove}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}

function QuestionRow({ bank, question, canManage, keyVisible, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const save = async (body) => {
    await api.questionBanks.updateQuestion(bank.id, question.id, {
      ...body,
      lock_version: question.lock_version,
    });
    notify("Question saved. Attempts already started keep their own copy.");
    setEditing(false);
    onChanged();
  };
  const setStatus = async (status) => {
    setError(null);
    try {
      await api.questionBanks.updateQuestion(bank.id, question.id, {
        status,
        lock_version: question.lock_version,
      });
      notify(status === "retired" ? "Question retired." : "Question restored.");
      onChanged();
    } catch (err) {
      setError(err);
    }
  };
  const remove = async () => {
    setConfirm(false);
    setError(null);
    try {
      await api.questionBanks.removeQuestion(bank.id, question.id);
      notify("Question deleted.");
      onChanged();
    } catch (err) {
      setError(err);
    }
  };
  if (editing) {
    return (
      <QuestionEditor
        kinds={KINDS}
        question={question}
        keyVisible={keyVisible}
        withTags
        onSave={save}
        onCancel={() => setEditing(false)}
      />
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium break-words">{question.prompt}</p>
          <p className="text-xs text-muted">
            {kindLabel(question.kind)}
            {question.graded
              ? ` · ${question.points} point${question.points === 1 ? "" : "s"}`
              : ""}
            {` · version ${question.version}`}
            {question.tags.length ? ` · tags: ${question.tags.join(", ")}` : ""}
          </p>
          {keyVisible && question.graded && (
            <p className="mt-1 text-xs text-sage-800">
              Answer:{" "}
              {question.kind === "true_false"
                ? question.correct[0]
                : question.options
                    .filter((o) => question.correct.includes(o.id))
                    .map((o) => o.text)
                    .join(", ")}
            </p>
          )}
        </div>
        <span className="flex flex-wrap items-center gap-1">
          <StatusBadge status={question.status === "retired" ? "archived" : "active"} />
          <span className="sr-only">{question.status}</span>
          {canManage && bank.status === "active" && (
            <>
              <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setStatus(question.status === "active" ? "retired" : "active")}
              >
                {question.status === "active" ? "Retire" : "Restore"}
              </Button>
              <button
                type="button"
                aria-label={`Delete question: ${question.prompt}`}
                onClick={() => setConfirm(true)}
                className="rounded p-1.5 text-muted hover:text-red-800"
              >
                <Trash2 aria-hidden className="size-4" />
              </button>
            </>
          )}
        </span>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {error.message}
        </p>
      )}
      <ConfirmDialog
        open={confirm}
        title="Delete this question?"
        message="Attempts already started keep their copy. Retiring keeps it for reference instead."
        confirmLabel="Delete"
        tone="danger"
        onConfirm={remove}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}

/** One bank: details, usage and its questions (answer keys only for managers). */
export function QuestionBankPage() {
  const { bankId } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const { can } = usePermissions();
  const canManage = can("question_banks.manage");
  const bank = useAdminQuery(() => api.questionBanks.get(bankId), [bankId]);
  const [filters, setFilters] = useState({ status: "active", kind: "", tag: "", q: "", page: 1 });
  const questions = useAdminQuery(
    () =>
      api.questionBanks.questions(bankId, {
        ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")),
        page_size: 25,
      }),
    [bankId, JSON.stringify(filters)],
  );
  const [adding, setAdding] = useState(false);
  const refresh = () => {
    questions.reload();
    bank.reload();
  };
  if (bank.error)
    return <ErrorState title="We couldn't load this question bank" onRetry={bank.reload} />;
  if (bank.loading && !bank.data) return <p role="status">Loading question bank…</p>;
  const data = bank.data;
  const keyVisible = data.answer_key_visible;
  const setFilter = (patch) => setFilters((f) => ({ ...f, page: 1, ...patch }));
  const addQuestion = async (body) => {
    await api.questionBanks.addQuestion(data.id, body);
    notify("Question added.");
    setAdding(false);
    refresh();
  };
  return (
    <>
      <AdminPageHeader
        title={data.title}
        description={`${data.question_counts.active} active questions${data.question_counts.retired ? ` · ${data.question_counts.retired} retired` : ""}`}
        breadcrumbs={[
          { label: "Question banks", to: "/admin/question-banks" },
          { label: data.title },
        ]}
        actions={<StatusBadge status={data.status} />}
      />
      {!keyVisible && (
        <p role="note" className="mb-4 rounded-xl bg-cream p-3 text-sm">
          Answer keys and explanations are hidden for your role.
        </p>
      )}
      <BankDetails
        key={data.lock_version}
        bank={data}
        canManage={canManage}
        onSaved={() => bank.reload()}
        onDeleted={() => navigate("/admin/question-banks")}
      />
      <section aria-labelledby="questions-heading" className="mt-8 space-y-4">
        <h2 id="questions-heading" className="text-xl font-medium">
          Questions
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <TextField
            label="Search questions"
            type="search"
            value={filters.q}
            maxLength={100}
            onChange={(e) => setFilter({ q: e.target.value })}
          />
          <SelectField
            label="Status"
            value={filters.status}
            onChange={(e) => setFilter({ status: e.target.value })}
            options={[
              { value: "active", label: "Active" },
              { value: "retired", label: "Retired" },
              { value: "", label: "All" },
            ]}
          />
          <SelectField
            label="Type"
            value={filters.kind}
            onChange={(e) => setFilter({ kind: e.target.value })}
            options={[{ value: "", label: "All types" }, ...KINDS]}
          />
          <SelectField
            label="Tag"
            value={filters.tag}
            onChange={(e) => setFilter({ tag: e.target.value })}
            options={[
              { value: "", label: "All tags" },
              ...data.tags.map((t) => ({ value: t, label: t })),
            ]}
          />
        </div>
        {questions.error ? (
          <ErrorSummary error={questions.error} title="We couldn't load the questions" />
        ) : questions.loading && !questions.data ? (
          <p role="status">Loading questions…</p>
        ) : (
          <ol aria-label="Bank questions" className="space-y-3">
            {questions.data.length === 0 && (
              <li className="rounded-xl border border-charcoal/10 p-4 text-sm text-muted">
                No questions match.
              </li>
            )}
            {questions.data.map((q) => (
              <li key={q.id} className="rounded-xl border border-charcoal/10 bg-white p-4">
                <QuestionRow
                  key={q.lock_version}
                  bank={data}
                  question={q}
                  canManage={canManage}
                  keyVisible={keyVisible}
                  onChanged={refresh}
                />
              </li>
            ))}
          </ol>
        )}
        {toPagination(questions.meta) && (
          <Pagination
            pagination={toPagination(questions.meta)}
            onPage={(page) => setFilters((f) => ({ ...f, page }))}
          />
        )}
        {canManage &&
          data.status === "active" &&
          (adding ? (
            <QuestionEditor
              kinds={KINDS}
              keyVisible={keyVisible}
              withTags
              onSave={addQuestion}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
              <Plus aria-hidden /> Add question
            </Button>
          ))}
      </section>
    </>
  );
}

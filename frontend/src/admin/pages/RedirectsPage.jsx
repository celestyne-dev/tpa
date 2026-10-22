import { Download, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { fieldError } from "../components/fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

const EMPTY = { source_path: "", destination: "", status_code: 301, is_active: true, note: "" };
const ORIGIN_LABELS = { manual: "Manual", slug_change: "Slug change", import: "Imported" };

/** Redirect manager: real HTTP redirects served by the web server (not client-side). */
export function RedirectsPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const canManage = can("redirects.manage");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const list = useAdminQuery(
    () => api.redirects.list({ q: search || undefined, page, page_size: 50 }),
    [search, page],
  );
  const [dialog, setDialog] = useState(null); // {mode, item?, form}
  const [importText, setImportText] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const open = (item) => {
    setError(null);
    setDialog({ item, form: item ? { ...EMPTY, ...item } : { ...EMPTY } });
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { source_path, destination, status_code, is_active, note } = dialog.form;
    const body = { source_path, destination, status_code: Number(status_code), is_active, note };
    try {
      if (dialog.item) await api.redirects.update(dialog.item.id, body);
      else await api.redirects.create(body);
      notify(dialog.item ? "Redirect updated." : "Redirect created.");
      setDialog(null);
      list.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const runImport = async (dryRun) => {
    setBusy(true);
    try {
      const res = await api.redirects.import(importText, dryRun);
      setImportResult({ ...res.data, dryRun });
      if (!dryRun) {
        notify(`Imported ${res.data.created} redirect(s).`);
        list.reload();
      }
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const setForm = (patch) => setDialog((d) => ({ ...d, form: { ...d.form, ...patch } }));

  return (
    <>
      <AdminPageHeader
        title="Redirects"
        description="Keep old and migrated URLs working. Redirects are answered by the server with real 301/302/307/308 status codes and take effect immediately."
        breadcrumbs={[{ label: "Redirects" }]}
        actions={
          <>
            <a
              href={api.redirects.exportUrl()}
              className="inline-flex h-9 items-center gap-2 rounded-full border border-charcoal/20 px-4 text-sm font-medium hover:border-sage-600"
            >
              <Download aria-hidden className="size-4" />
              Export CSV
            </a>
            {canManage && (
              <>
                <Button size="sm" variant="outline" onClick={() => setImportText("")}>
                  <Upload aria-hidden />
                  Import
                </Button>
                <Button size="sm" onClick={() => open(null)}>
                  <Plus aria-hidden />
                  Add redirect
                </Button>
              </>
            )}
          </>
        }
      />
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(1);
          setSearch(q.trim());
        }}
        className="mb-4 flex max-w-xl gap-2"
      >
        <TextField
          className="flex-1"
          label="Search redirects"
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button
          type="submit"
          className="mt-auto h-10 rounded-lg bg-charcoal px-4 text-sm font-medium text-ivory"
        >
          Search
        </button>
      </form>
      {list.error ? (
        <ErrorState title="We couldn't load redirects" onRetry={list.reload} />
      ) : (
        <DataTable
          caption="Redirects"
          rows={list.data}
          loading={list.loading}
          empty={{
            title: "No redirects yet",
            description: "Slug changes on published articles add redirects automatically.",
          }}
          columns={[
            {
              key: "source",
              header: "From",
              render: (r) => <code className="text-xs break-all">{r.source_path}</code>,
            },
            {
              key: "dest",
              header: "To",
              render: (r) => <code className="text-xs break-all">{r.destination}</code>,
            },
            { key: "code", header: "Type", render: (r) => r.status_code },
            {
              key: "status",
              header: "Status",
              render: (r) => <StatusBadge status={r.is_active ? "active" : "inactive"} />,
            },
            { key: "origin", header: "Source", render: (r) => ORIGIN_LABELS[r.origin] ?? r.origin },
            { key: "updated", header: "Updated", render: (r) => formatDateTime(r.updated_at) },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              className: "text-right",
              render: (r) =>
                canManage && (
                  <span className="flex justify-end gap-1">
                    <button
                      type="button"
                      aria-label={`Edit redirect from ${r.source_path}`}
                      className="rounded p-1.5 text-muted hover:bg-beige"
                      onClick={() => open(r)}
                    >
                      <Pencil aria-hidden className="size-4" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete redirect from ${r.source_path}`}
                      className="rounded p-1.5 text-muted hover:bg-red-50 hover:text-red-800"
                      onClick={() => setConfirm(r)}
                    >
                      <Trash2 aria-hidden className="size-4" />
                    </button>
                  </span>
                ),
            },
          ]}
        />
      )}
      <Pagination pagination={list.meta?.pagination} onPage={setPage} />

      <Modal
        open={Boolean(dialog)}
        onClose={() => setDialog(null)}
        title={dialog?.item ? "Edit redirect" : "Add redirect"}
        footer={
          <>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button type="submit" form="redirect-form" disabled={busy}>
              Save
            </Button>
          </>
        }
      >
        {dialog && (
          <form id="redirect-form" onSubmit={submit} className="space-y-4">
            {error && !error.details && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
                {error.message}
              </p>
            )}
            <TextField
              label="Old path"
              required
              placeholder="/2019/05/old-article-name"
              hint="A path on this site. Full old URLs are accepted; only the path is kept."
              value={dialog.form.source_path}
              onChange={(e) => setForm({ source_path: e.target.value })}
              error={fieldError(error, "source_path")}
            />
            <TextField
              label="Destination"
              required
              placeholder="/articles/new-article-name"
              hint="A site path, or an https:// address on an allowed host."
              value={dialog.form.destination}
              onChange={(e) => setForm({ destination: e.target.value })}
              error={fieldError(error, "destination")}
            />
            <SelectField
              label="Redirect type"
              value={String(dialog.form.status_code)}
              options={[
                { value: "301", label: "301 — moved permanently (recommended)" },
                { value: "308", label: "308 — permanent, keeps the request method" },
                { value: "302", label: "302 — temporary" },
                { value: "307", label: "307 — temporary, keeps the request method" },
              ]}
              onChange={(e) => setForm({ status_code: Number(e.target.value) })}
              error={fieldError(error, "status_code")}
            />
            <CheckboxField
              label="Active"
              checked={dialog.form.is_active}
              onChange={(e) => setForm({ is_active: e.target.checked })}
            />
            <TextField
              label="Note (optional)"
              value={dialog.form.note ?? ""}
              onChange={(e) => setForm({ note: e.target.value })}
            />
          </form>
        )}
      </Modal>

      <Modal
        open={importText !== null}
        onClose={() => {
          setImportText(null);
          setImportResult(null);
        }}
        title="Import redirects"
        description="Paste CSV with the columns source_path,destination,status_code,is_active,note. Check it first with a dry run."
        size="lg"
        footer={
          <>
            <Button
              variant="outline"
              disabled={busy || !importText}
              onClick={() => runImport(true)}
            >
              Dry run
            </Button>
            <Button disabled={busy || !importText} onClick={() => runImport(false)}>
              Import
            </Button>
          </>
        }
      >
        <TextAreaField
          label="CSV"
          rows={8}
          value={importText ?? ""}
          onChange={(e) => setImportText(e.target.value)}
        />
        {importResult && (
          <div className="mt-4 text-sm" role="status">
            <p className="font-medium">
              {importResult.dryRun
                ? `${importResult.valid} valid row(s) would be imported.`
                : `${importResult.created} redirect(s) imported.`}{" "}
              {importResult.errors.length} problem(s).
            </p>
            {importResult.errors.length > 0 && (
              <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-red-900">
                {importResult.errors.map((e) => (
                  <li key={e.row}>
                    Row {e.row} ({e.source_path || "no path"}): {e.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={Boolean(confirm)}
        title="Delete this redirect?"
        message={`Visitors to ${confirm?.source_path} will get a 404 page instead.`}
        confirmLabel="Delete redirect"
        tone="danger"
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          setBusy(true);
          try {
            await api.redirects.remove(confirm.id);
            notify("Redirect deleted.");
            list.reload();
          } catch (err) {
            notify(err.message, "error");
          } finally {
            setBusy(false);
            setConfirm(null);
          }
        }}
      />
    </>
  );
}

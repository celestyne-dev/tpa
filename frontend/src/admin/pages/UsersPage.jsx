import { KeyRound, Pencil, UserPlus } from "lucide-react";
import { useState } from "react";
import { useSelector } from "react-redux";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { selectAuth } from "@/store/slices/authSlice";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { DataTable } from "../components/DataTable";
import { fieldError } from "../components/fieldError";
import { SelectField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";

const roleLabel = (r) => r.replace("_", " ");

function RolePicker({ roles, value, onChange, error }) {
  return (
    <fieldset>
      <legend className="text-sm font-medium text-charcoal">Roles</legend>
      <div className="mt-2 space-y-2">
        {roles.map((r) => (
          <label
            key={r.name}
            className="flex items-start gap-3 rounded-lg border border-charcoal/10 p-3 text-sm"
          >
            <input
              type="checkbox"
              className="mt-0.5 accent-sage-700"
              checked={value.includes(r.name)}
              onChange={(e) =>
                onChange(e.target.checked ? [...value, r.name] : value.filter((v) => v !== r.name))
              }
            />
            <span>
              <span className="font-medium capitalize">{roleLabel(r.name)}</span>
              <span className="block text-muted">{r.description}</span>
            </span>
          </label>
        ))}
      </div>
      {error && (
        <p role="alert" className="mt-1 text-sm text-red-800">
          {error}
        </p>
      )}
    </fieldset>
  );
}

export function UsersPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { user: me } = useSelector(selectAuth);
  const users = useAdminQuery(() => api.users.list(), []);
  const roles = useAdminQuery(() => api.users.roles(), []);
  const [dialog, setDialog] = useState(null); // {mode: create|edit|password, user?, form}
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const open = (mode, user) => {
    setError(null);
    setDialog({
      mode,
      user,
      form:
        mode === "create"
          ? { email: "", display_name: "", password: "", roles: ["editor"] }
          : mode === "edit"
            ? { display_name: user.display_name, status: user.status, roles: user.roles }
            : { password: "" },
    });
  };
  const setForm = (patch) => setDialog((d) => ({ ...d, form: { ...d.form, ...patch } }));

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (dialog.mode === "create") await api.users.create(dialog.form);
      if (dialog.mode === "edit") await api.users.update(dialog.user.id, dialog.form);
      if (dialog.mode === "password")
        await api.users.resetPassword(dialog.user.id, dialog.form.password);
      notify(
        dialog.mode === "password"
          ? "Password reset. The user's sessions were signed out."
          : "User saved.",
      );
      setDialog(null);
      users.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const title = {
    create: "Add administrator",
    edit: "Edit administrator",
    password: "Reset password",
  }[dialog?.mode];

  return (
    <>
      <AdminPageHeader
        title="Users"
        description="Administrator accounts and their roles. Only super administrators can manage users."
        breadcrumbs={[{ label: "Users" }]}
        actions={
          <Button size="sm" onClick={() => open("create")}>
            <UserPlus aria-hidden />
            Add administrator
          </Button>
        }
      />
      {users.error ? (
        <ErrorState title="We couldn't load users" onRetry={users.reload} />
      ) : (
        <DataTable
          caption="Administrators"
          rows={users.data}
          loading={users.loading}
          columns={[
            {
              key: "name",
              header: "Name",
              render: (u) => (
                <div>
                  <p className="font-medium">
                    {u.display_name}{" "}
                    {u.id === me?.id && <span className="text-xs text-muted">(you)</span>}
                  </p>
                  <p className="text-xs text-muted">{u.email}</p>
                </div>
              ),
            },
            {
              key: "roles",
              header: "Roles",
              render: (u) => (
                <span className="capitalize">{u.roles.map(roleLabel).join(", ") || "—"}</span>
              ),
            },
            { key: "status", header: "Status", render: (u) => <StatusBadge status={u.status} /> },
            { key: "last", header: "Last sign-in", render: (u) => formatDateTime(u.last_login_at) },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              className: "text-right",
              render: (u) => (
                <div className="flex justify-end gap-1">
                  <button
                    type="button"
                    aria-label={`Edit ${u.display_name}`}
                    onClick={() => open("edit", u)}
                    className="rounded p-1.5 text-muted hover:bg-beige"
                  >
                    <Pencil aria-hidden className="size-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={`Reset password for ${u.display_name}`}
                    onClick={() => open("password", u)}
                    className="rounded p-1.5 text-muted hover:bg-beige"
                  >
                    <KeyRound aria-hidden className="size-4" />
                  </button>
                </div>
              ),
            },
          ]}
        />
      )}

      <Modal
        open={Boolean(dialog)}
        onClose={() => setDialog(null)}
        title={title}
        description={dialog?.user?.email}
        footer={
          <>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button type="submit" form="user-form" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </>
        }
      >
        {dialog && (
          <form id="user-form" onSubmit={submit} className="space-y-4">
            {error && !error.details && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
                {error.message}
              </p>
            )}
            {dialog.mode === "create" && (
              <TextField
                label="Email"
                type="email"
                required
                value={dialog.form.email}
                onChange={(e) => setForm({ email: e.target.value })}
                error={fieldError(error, "email")}
              />
            )}
            {dialog.mode !== "password" && (
              <TextField
                label="Display name"
                required
                value={dialog.form.display_name}
                onChange={(e) => setForm({ display_name: e.target.value })}
                error={fieldError(error, "display_name")}
              />
            )}
            {dialog.mode !== "edit" && (
              <TextField
                label={dialog.mode === "create" ? "Initial password" : "New password"}
                type="password"
                autoComplete="new-password"
                required
                hint="At least 12 characters. Share it securely; the user should change it after signing in."
                value={dialog.form.password}
                onChange={(e) => setForm({ password: e.target.value })}
                error={fieldError(error, "password")}
              />
            )}
            {dialog.mode === "edit" && (
              <SelectField
                label="Status"
                value={dialog.form.status}
                options={[
                  { value: "active", label: "Active" },
                  { value: "disabled", label: "Disabled (signs the user out)" },
                ]}
                onChange={(e) => setForm({ status: e.target.value })}
              />
            )}
            {dialog.mode !== "password" && roles.data && (
              <RolePicker
                roles={roles.data}
                value={dialog.form.roles}
                onChange={(v) => setForm({ roles: v })}
                error={fieldError(error, "roles")}
              />
            )}
          </form>
        )}
      </Modal>
    </>
  );
}

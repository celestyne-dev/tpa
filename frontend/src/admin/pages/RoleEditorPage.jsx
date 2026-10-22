import { Lock, Save, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { fieldError } from "../components/fieldError";
import { CheckboxField, TextAreaField, TextField } from "../components/Fields";
import { useNotify } from "../components/notifyContext";
import { RoleKindBadge } from "../components/RoleBadges";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";

const EMPTY = { label: "", description: "", permissions: [], is_active: true };

function toForm(role) {
  return {
    label: role.label,
    description: role.description ?? "",
    permissions: [...role.permissions].sort(),
    is_active: role.is_active,
  };
}

/** Why a permission cannot be ticked, or null when it can. */
function lockReason(permission, { readOnly, held }) {
  if (permission.sensitive) return "Super Admin only";
  if (!permission.available) return "Module not available yet";
  if (readOnly) return null;
  if (!held.has(permission.key)) return "You don't hold this permission";
  return null;
}

function PermissionGroup({ group, selected, planned, readOnly, held, onToggle, onSetMany }) {
  const assignable = group.permissions.filter((p) => !lockReason(p, { readOnly, held }));
  const allOn = assignable.length > 0 && assignable.every((p) => selected.has(p.key));
  const headingId = `group-${group.name.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <fieldset
      aria-labelledby={headingId}
      className="min-w-0 rounded-xl border border-charcoal/10 bg-white p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={headingId} className="font-sans text-sm font-semibold">
          {group.name}
        </h3>
        {!readOnly && assignable.length > 1 && (
          <button
            type="button"
            className="text-xs font-medium text-sage-700 hover:underline"
            onClick={() =>
              onSetMany(
                assignable.map((p) => p.key),
                !allOn,
              )
            }
          >
            {allOn ? "Clear group" : "Select all available"}
          </button>
        )}
      </div>
      <ul className="mt-3 space-y-2">
        {group.permissions.map((p) => {
          const reason = lockReason(p, { readOnly, held });
          const isPlanned = planned.has(p.key);
          return (
            <li key={p.key}>
              <label
                className={cn(
                  "flex items-start gap-3 rounded-lg p-2 text-sm",
                  reason ? "text-muted" : "hover:bg-cream/60",
                )}
              >
                <input
                  type="checkbox"
                  className="mt-0.5 accent-sage-700"
                  checked={selected.has(p.key)}
                  disabled={readOnly || Boolean(reason)}
                  onChange={(e) => onToggle(p.key, e.target.checked)}
                />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium text-charcoal">{p.label}</span>
                  <code className="block text-xs break-all text-muted">{p.key}</code>
                  {p.description && <span className="block text-xs">{p.description}</span>}
                  <span className="mt-1 flex flex-wrap gap-1.5">
                    {reason && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-beige px-2 py-0.5 text-[0.7rem] font-semibold">
                        {p.sensitive && <Lock aria-hidden className="size-3" />}
                        {reason}
                      </span>
                    )}
                    {isPlanned && (
                      <span className="rounded-full border border-sage-600/40 px-2 py-0.5 text-[0.7rem] font-semibold text-sage-800">
                        Planned for this template
                      </span>
                    )}
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

export function RoleEditorPage() {
  const { id } = useParams();
  const isNew = !id;
  const api = useAdminApi();
  const navigate = useNavigate();
  const notify = useNotify();
  const { can, permissions: myPermissions } = usePermissions();
  const canManage = can("roles.manage");

  const catalogue = useAdminQuery(() => api.roles.permissions(), []);
  const role = useAdminQuery(
    () => (isNew ? Promise.resolve({ data: null }) : api.roles.get(id)),
    [id],
  );
  const record = role.data;

  const [form, setForm] = useState(EMPTY);
  const [saved, setSaved] = useState(EMPTY);
  const [loadedFor, setLoadedFor] = useState(null);
  if (record && loadedFor !== record.updated_at + record.id) {
    setLoadedFor(record.updated_at + record.id);
    setForm(toForm(record));
    setSaved(toForm(record));
  }
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const readOnly = !canManage || Boolean(record?.is_protected);
  const dirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(saved), [form, saved]);
  useUnsavedChanges(dirty && !readOnly);

  const held = useMemo(() => new Set(myPermissions), [myPermissions]);
  const selected = useMemo(() => new Set(form.permissions), [form.permissions]);
  const planned = useMemo(() => new Set(record?.planned_permissions ?? []), [record]);
  const labels = useMemo(
    () =>
      Object.fromEntries(
        (catalogue.data ?? []).flatMap((g) => g.permissions.map((p) => [p.key, p.label])),
      ),
    [catalogue.data],
  );

  const toggle = (key, on) =>
    setForm((f) => ({
      ...f,
      permissions: on
        ? [...new Set([...f.permissions, key])].sort()
        : f.permissions.filter((k) => k !== key),
    }));
  const setMany = (keys, on) =>
    setForm((f) => ({
      ...f,
      permissions: on
        ? [...new Set([...f.permissions, ...keys])].sort()
        : f.permissions.filter((k) => !keys.includes(k)),
    }));

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (isNew) {
        const res = await api.roles.create({
          label: form.label,
          description: form.description,
          permissions: form.permissions,
        });
        setSaved(form);
        notify("Role created.");
        navigate(`/admin/roles/${res.data.id}`, { replace: true });
      } else {
        const res = await api.roles.update(id, form);
        role.setData(res.data);
        notify("Role saved. Changes apply to its users immediately.");
      }
    } catch (err) {
      setError(err);
      notify(err.status === 400 ? "Please fix the highlighted fields." : err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.roles.remove(id);
      setSaved(form);
      notify("Role deleted.");
      navigate("/admin/roles", { replace: true });
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  };

  if (role.error || catalogue.error)
    return (
      <ErrorState
        title="We couldn't load this role"
        message={(role.error ?? catalogue.error).message}
        onRetry={() => {
          role.reload();
          catalogue.reload();
        }}
      />
    );
  if ((!isNew && !record) || !catalogue.data)
    return (
      <div role="status" aria-label="Loading role" className="space-y-4">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-64 w-full" />
      </div>
    );

  const effective = record?.grants_all ? null : form.permissions;
  const plannedOnly = [...planned].filter((k) => !selected.has(k));
  const inUse = (record?.user_count ?? 0) > 0 || (record?.pending_invitations ?? 0) > 0;

  return (
    <>
      <AdminPageHeader
        title={isNew ? "New role" : record.label}
        description={
          record?.is_protected
            ? "Built-in role. It is protected and shown for reference."
            : "Choose a name and the permissions this role grants."
        }
        breadcrumbs={[
          { label: "Roles & Permissions", to: "/admin/roles" },
          { label: isNew ? "New" : record.label },
        ]}
        actions={
          !readOnly && (
            <Button
              type="submit"
              form="role-form"
              size="sm"
              disabled={busy || (!dirty && !isNew) || !form.label.trim()}
            >
              <Save aria-hidden />
              {isNew ? "Create role" : "Save changes"}
            </Button>
          )
        }
      />
      {error && !error.details && (
        <p role="alert" className="mb-4 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-900">
          {error.message}
        </p>
      )}
      {error?.details?.permissions && (
        <ul role="alert" className="mb-4 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-900">
          {error.details.permissions.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      )}
      <form
        id="role-form"
        onSubmit={save}
        className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]"
      >
        <div className="min-w-0 space-y-5">
          <fieldset
            disabled={readOnly}
            className="space-y-4 rounded-xl border border-charcoal/10 bg-white p-5"
          >
            <legend className="sr-only">Role details</legend>
            <TextField
              label="Role name"
              required
              maxLength={80}
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              error={fieldError(error, "label")}
            />
            <TextAreaField
              label="Description"
              maxLength={255}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              error={fieldError(error, "description")}
            />
            {!isNew && !record.is_protected && (
              <CheckboxField
                label="Active"
                hint="Inactive roles grant nothing and cannot be newly assigned. Members keep the role, dormant, until it is reactivated."
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />
            )}
          </fieldset>

          {record?.grants_all ? (
            <p className="rounded-xl border border-charcoal/10 bg-white p-5 text-sm">
              <Lock aria-hidden className="mr-1 inline size-4" />
              Super Admin grants every permission, including sensitive permissions and those of
              modules added in the future.
            </p>
          ) : (
            <section aria-labelledby="perm-heading" className="space-y-3">
              <h2 id="perm-heading" className="font-sans text-base font-semibold">
                Permissions
              </h2>
              <div className="grid gap-4 lg:grid-cols-2">
                {catalogue.data.map((group) => (
                  <PermissionGroup
                    key={group.name}
                    group={group}
                    selected={selected}
                    planned={planned}
                    readOnly={readOnly}
                    held={held}
                    onToggle={toggle}
                    onSetMany={setMany}
                  />
                ))}
              </div>
            </section>
          )}
        </div>

        <aside className="space-y-5">
          <section
            aria-labelledby="summary-heading"
            className="rounded-xl border border-charcoal/10 bg-white p-5 text-sm"
          >
            <h2
              id="summary-heading"
              className="flex items-center justify-between gap-2 font-sans text-base font-semibold"
            >
              Effective permissions
              {record && <RoleKindBadge kind={record.kind} />}
            </h2>
            {record && (
              <p className="mt-2">
                <StatusBadge status={record.is_active ? "active" : "inactive"} />
              </p>
            )}
            {effective === null ? (
              <p className="mt-3">Everything.</p>
            ) : effective.length === 0 ? (
              <p className="mt-3 text-muted">This role grants no permissions yet.</p>
            ) : (
              <>
                <p className="mt-3 text-muted">
                  {effective.length} permission{effective.length === 1 ? "" : "s"}
                </p>
                <ul className="mt-2 space-y-1">
                  {effective.map((k) => (
                    <li key={k}>{labels[k] ?? k}</li>
                  ))}
                </ul>
              </>
            )}
            {plannedOnly.length > 0 && (
              <div className="mt-4 border-t border-charcoal/10 pt-3">
                <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">
                  Unlocks when its module ships
                </h3>
                <ul className="mt-1 space-y-1 text-muted">
                  {plannedOnly.map((k) => (
                    <li key={k}>{labels[k] ?? k}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {record && (
            <section
              aria-labelledby="members-heading"
              className="rounded-xl border border-charcoal/10 bg-white p-5 text-sm"
            >
              <h2 id="members-heading" className="font-sans text-base font-semibold">
                Users with this role
              </h2>
              {record.users.length === 0 ? (
                <p className="mt-2 text-muted">Nobody holds this role.</p>
              ) : (
                <ul className="mt-2 space-y-1.5">
                  {record.users.map((u) => (
                    <li key={u.id} className="flex flex-wrap items-center justify-between gap-2">
                      <span className="min-w-0">
                        <span className="font-medium">{u.display_name}</span>
                        <span className="block text-xs break-all text-muted">{u.email}</span>
                      </span>
                      {u.status !== "active" && <StatusBadge status={u.status} />}
                    </li>
                  ))}
                </ul>
              )}
              {record.pending_invitations > 0 && (
                <p className="mt-3 text-muted">
                  Included in {record.pending_invitations} pending invitation
                  {record.pending_invitations === 1 ? "" : "s"}.
                </p>
              )}
              {can("users.view") && (
                <Link
                  to={`/admin/users`}
                  className="mt-3 inline-block text-sage-700 hover:underline"
                >
                  Manage users
                </Link>
              )}
            </section>
          )}

          {record && !readOnly && (
            <section className="rounded-xl border border-red-200 bg-white p-5 text-sm">
              <h2 className="font-sans text-base font-semibold">Delete role</h2>
              <p className="mt-1 text-muted">
                {inUse
                  ? "Roles that are assigned to users or pending invitations cannot be deleted. Deactivate it instead."
                  : "The role is not assigned to anyone and can be deleted."}
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3 text-red-800"
                disabled={busy || inUse}
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 aria-hidden />
                Delete role
              </Button>
            </section>
          )}
          <ButtonLink to="/admin/roles" variant="ghost" size="sm">
            ← Back to roles
          </ButtonLink>
        </aside>
      </form>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete the ${record?.label} role?`}
        message="This cannot be undone."
        confirmLabel="Delete role"
        tone="danger"
        busy={busy}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={remove}
      />
    </>
  );
}

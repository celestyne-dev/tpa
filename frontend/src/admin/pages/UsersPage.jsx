import {
  Eye,
  KeyRound,
  Mail,
  Pencil,
  RotateCcw,
  Send,
  ShieldOff,
  ShieldCheck,
  UserPlus,
  X,
} from "lucide-react";
import { useState } from "react";
import { useSelector } from "react-redux";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { selectAuth } from "@/store/slices/authSlice";
import { cn, formatDateTime } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { fieldError } from "../components/fieldError";
import { SelectField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { useNotify } from "../components/notifyContext";
import { RoleBadges } from "../components/RoleBadges";
import { StatusBadge } from "../components/StatusBadge";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";
import { previewPermissions } from "../permissions";

const DELIVERY_MESSAGES = {
  development_console:
    "Development mode: the link was written to the Flask server terminal (not emailed).",
  smtp: "The link was emailed.",
  memory: "The link was queued (test mode).",
};

function deliveryMessage(prefix, delivery) {
  return `${prefix} ${DELIVERY_MESSAGES[delivery] ?? ""}`.trim();
}

const KIND_GROUPS = [
  ["system", "Built-in roles"],
  ["template", "Role templates"],
  ["custom", "Custom roles"],
];

function RolePicker({ roles, value, initial = [], labels, onChange, error }) {
  const effective = previewPermissions(roles, value);
  return (
    <fieldset>
      <legend className="text-sm font-medium text-charcoal">Roles</legend>
      <p className="mt-0.5 text-xs text-muted">
        Choose one or more. People receive every permission of their active roles.
      </p>
      {KIND_GROUPS.map(([kind, title]) => {
        // Inactive roles can't be newly assigned, but an existing assignment stays visible.
        const items = roles.filter(
          (r) => r.kind === kind && (r.is_active !== false || initial.includes(r.name)),
        );
        if (!items.length) return null;
        return (
          <div key={kind} className="mt-3">
            <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">{title}</h3>
            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
              {items.map((r) => (
                <label
                  key={r.name}
                  className="flex items-start gap-3 rounded-lg border border-charcoal/10 p-3 text-sm"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-sage-700"
                    checked={value.includes(r.name)}
                    onChange={(e) =>
                      onChange(
                        e.target.checked ? [...value, r.name] : value.filter((v) => v !== r.name),
                      )
                    }
                  />
                  <span className="min-w-0">
                    <span className="font-medium">{r.label ?? r.name}</span>
                    {r.is_active === false && (
                      <span className="ml-1.5 text-xs text-muted">(inactive)</span>
                    )}
                    <span className="block text-xs text-muted">{r.description}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        );
      })}
      {error && (
        <p role="alert" className="mt-1 text-sm text-red-800">
          {error}
        </p>
      )}
      <div
        aria-live="polite"
        className="mt-3 rounded-lg bg-cream/70 px-3 py-2 text-sm"
        data-testid="effective-preview"
      >
        <p className="font-medium">
          Effective permissions:{" "}
          {effective === null ? "all permissions (Super Admin)" : `${effective.length}`}
        </p>
        {effective?.length > 0 && (
          <p className="mt-1 text-xs text-muted">
            {effective.map((k) => labels[k] ?? k).join(" · ")}
          </p>
        )}
      </div>
    </fieldset>
  );
}

function UserDetails({ userId, roleLabels, labels, onClose }) {
  const api = useAdminApi();
  const { data, error, loading } = useAdminQuery(() => api.users.get(userId), [userId]);
  // Resolved by the server from the user's active roles.
  const permissions = data?.permissions ?? [];
  return (
    <Modal open onClose={onClose} title="Administrator details" description={data?.email} size="lg">
      {loading && !data && <Skeleton className="h-40 w-full" />}
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {error.message}
        </p>
      )}
      {data && (
        <div className="space-y-5 text-sm">
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-muted">Name</dt>
              <dd className="font-medium">{data.display_name}</dd>
            </div>
            <div>
              <dt className="text-muted">Status</dt>
              <dd>
                <StatusBadge status={data.status} />
              </dd>
            </div>
            <div>
              <dt className="text-muted">Roles</dt>
              <dd className="mt-1">
                <RoleBadges roles={data.roles} labels={roleLabels} />
              </dd>
            </div>
            <div>
              <dt className="text-muted">Last sign-in</dt>
              <dd>{formatDateTime(data.last_login_at)}</dd>
            </div>
            <div>
              <dt className="text-muted">Created</dt>
              <dd>{formatDateTime(data.created_at)}</dd>
            </div>
            <div>
              <dt className="text-muted">Email verified</dt>
              <dd>
                {data.email_verified_at ? formatDateTime(data.email_verified_at) : "Not verified"}
              </dd>
            </div>
          </dl>
          {data.is_last_super_admin && (
            <p className="rounded-lg bg-gold-100/70 px-3 py-2 text-gold-700">
              This is the last active super administrator. It cannot be disabled or lose that role.
            </p>
          )}
          <section aria-labelledby="perm-heading">
            <h3 id="perm-heading" className="font-sans text-sm font-semibold">
              Effective permissions
            </h3>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {permissions.map((p) => (
                <li key={p} className="rounded bg-cream px-2 py-0.5 text-xs" title={p}>
                  {labels[p] ?? p}
                </li>
              ))}
            </ul>
          </section>
          {data.account_links?.length > 0 && (
            <section aria-labelledby="links-heading">
              <h3 id="links-heading" className="font-sans text-sm font-semibold">
                Password reset links
              </h3>
              <ul className="mt-2 space-y-1">
                {data.account_links.map((l) => (
                  <li key={l.id} className="flex justify-between gap-3">
                    <span>Sent {formatDateTime(l.created_at)}</span>
                    <StatusBadge status={l.status} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section aria-labelledby="activity-heading">
            <h3 id="activity-heading" className="font-sans text-sm font-semibold">
              Recent activity
            </h3>
            {data.recent_activity.length === 0 ? (
              <p className="mt-2 text-muted">No recorded activity.</p>
            ) : (
              <ul className="mt-2 divide-y divide-charcoal/5">
                {data.recent_activity.map((e) => (
                  <li key={e.id} className="flex flex-wrap justify-between gap-x-3 py-1.5">
                    <span className="font-mono text-xs">{e.action}</span>
                    <time className="text-muted" dateTime={e.created_at}>
                      {formatDateTime(e.created_at)}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </Modal>
  );
}

function IconAction({ label, icon: Icon, onClick, danger }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        "rounded p-1.5 text-muted",
        danger ? "hover:bg-red-50 hover:text-red-800" : "hover:bg-beige hover:text-charcoal",
      )}
    >
      <Icon aria-hidden className="size-4" />
    </button>
  );
}

export function UsersPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { user: me } = useSelector(selectAuth);
  const { can } = usePermissions();
  const canManage = can("users.manage");
  // Assigning roles (create, invite, change roles) also needs roles.assign.
  const canAssign = canManage && can("roles.assign");
  const [tab, setTab] = useState("users");
  const [filters, setFilters] = useState({ q: "", role: "", status: "" });
  const [search, setSearch] = useState("");
  const [inviteStatus, setInviteStatus] = useState("pending");

  const users = useAdminQuery(
    () =>
      api.users.list({
        q: filters.q || undefined,
        role: filters.role || undefined,
        status: filters.status || undefined,
      }),
    [filters.q, filters.role, filters.status],
  );
  const invitations = useAdminQuery(
    () => api.invitations.list({ status: inviteStatus || undefined }),
    [inviteStatus],
  );
  const roles = useAdminQuery(() => api.users.roles(), []);
  const catalogue = useAdminQuery(() => api.users.permissions(), []);
  const labels = Object.fromEntries(
    (catalogue.data ?? []).flatMap((g) => g.permissions.map((p) => [p.key, p.label])),
  );
  const roleLabels = Object.fromEntries((roles.data ?? []).map((r) => [r.name, r.label]));

  const [dialog, setDialog] = useState(null); // {mode: invite|create|edit|password, user?, form}
  const [details, setDetails] = useState(null);
  const [confirm, setConfirm] = useState(null); // {title, message, label, tone, run}
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const open = (mode, user) => {
    setError(null);
    const forms = {
      invite: { email: "", display_name: "", roles: ["editor"] },
      create: { email: "", display_name: "", password: "", roles: ["editor"] },
      edit: canAssign
        ? { display_name: user?.display_name, roles: user?.roles }
        : { display_name: user?.display_name },
      password: { password: "" },
    };
    setDialog({ mode, user, form: forms[mode] });
  };
  const setForm = (patch) => setDialog((d) => ({ ...d, form: { ...d.form, ...patch } }));

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (dialog.mode === "invite") {
        const res = await api.invitations.create(dialog.form);
        notify(deliveryMessage(`Invitation created for ${res.data.email}.`, res.data.delivery));
        invitations.reload();
        setTab("invitations");
      } else if (dialog.mode === "create") {
        await api.users.create(dialog.form);
        notify("Administrator created. Share the initial password securely, not by email.");
      } else if (dialog.mode === "edit") {
        await api.users.update(dialog.user.id, dialog.form);
        notify("Administrator updated.");
      } else {
        await api.users.resetPassword(dialog.user.id, dialog.form.password);
        notify("Password set. The user's sessions were signed out.");
      }
      setDialog(null);
      users.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const runConfirmed = async () => {
    setBusy(true);
    try {
      await confirm.run();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const askToggleStatus = (u) => {
    const disabling = u.status === "active";
    setConfirm({
      title: disabling ? `Disable ${u.display_name}?` : `Reactivate ${u.display_name}?`,
      message: disabling
        ? "They will be signed out everywhere immediately, and any pending password reset links stop working."
        : "They will be able to sign in again with their existing password.",
      label: disabling ? "Disable account" : "Reactivate account",
      tone: disabling ? "danger" : "primary",
      run: async () => {
        await api.users.update(u.id, { status: disabling ? "disabled" : "active" });
        notify(disabling ? "Account disabled." : "Account reactivated.");
        users.reload();
      },
    });
  };

  const askResetLink = (u) =>
    setConfirm({
      title: `Send a password reset link to ${u.email}?`,
      message:
        "The link can be used once and expires soon. Existing links for this account are revoked.",
      label: "Send reset link",
      run: async () => {
        const res = await api.users.sendPasswordReset(u.id);
        notify(deliveryMessage("Password reset link created.", res.data.delivery));
      },
    });

  const askInvitation = (inv, action) =>
    setConfirm({
      title:
        action === "revoke"
          ? `Revoke the invitation for ${inv.email}?`
          : `Resend the invitation to ${inv.email}?`,
      message:
        action === "revoke"
          ? "The activation link stops working immediately."
          : "A new link is sent and the previous link stops working.",
      label: action === "revoke" ? "Revoke invitation" : "Resend invitation",
      tone: action === "revoke" ? "danger" : "primary",
      run: async () => {
        const res = await api.invitations[action](inv.id);
        notify(
          action === "revoke"
            ? "Invitation revoked."
            : deliveryMessage("Invitation resent.", res.data.delivery),
        );
        invitations.reload();
      },
    });

  const roleOptions = [
    { value: "", label: "All roles" },
    ...(roles.data ?? []).map((r) => ({ value: r.name, label: r.label ?? r.name })),
  ];
  const titles = {
    invite: "Invite administrator",
    create: "Create administrator",
    edit: "Edit administrator",
    password: "Set a new password",
  };

  return (
    <>
      <AdminPageHeader
        title="Users"
        description="Administrator accounts, roles and invitations."
        breadcrumbs={[{ label: "Users" }]}
        actions={
          canAssign && (
            <>
              <Button size="sm" onClick={() => open("invite")}>
                <Send aria-hidden />
                Invite user
              </Button>
              <Button size="sm" variant="outline" onClick={() => open("create")}>
                <UserPlus aria-hidden />
                Create user
              </Button>
            </>
          )
        }
      />

      <div
        role="tablist"
        aria-label="User management"
        className="mb-4 flex gap-2 border-b border-charcoal/10"
      >
        {[
          ["users", "Administrators"],
          ["invitations", "Invitations"],
        ].map(([key, label]) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              tab === key
                ? "border-sage-700 text-sage-800"
                : "border-transparent text-muted hover:text-charcoal",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <div role="tabpanel" aria-label="Administrators">
          <form
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              setFilters((f) => ({ ...f, q: search.trim() }));
            }}
            className="mb-4 grid gap-3 rounded-xl border border-charcoal/10 bg-white p-4 sm:grid-cols-[1fr_10rem_10rem_auto] sm:items-end"
          >
            <TextField
              label="Search users"
              type="search"
              placeholder="Name or email"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <SelectField
              label="Role"
              options={roleOptions}
              value={filters.role}
              onChange={(e) => setFilters((f) => ({ ...f, role: e.target.value }))}
            />
            <SelectField
              label="Account status"
              options={[
                { value: "", label: "Any status" },
                { value: "active", label: "Active" },
                { value: "disabled", label: "Disabled" },
              ]}
              value={filters.status}
              onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            />
            <button
              type="submit"
              className="h-10 rounded-lg bg-charcoal px-4 text-sm font-medium text-ivory hover:bg-ink"
            >
              Search
            </button>
          </form>
          {users.error ? (
            <ErrorState title="We couldn't load users" onRetry={users.reload} />
          ) : (
            <DataTable
              caption="Administrators"
              rows={users.data}
              loading={users.loading}
              empty={{
                title: "No matching administrators",
                description: "Try a different search or filter.",
              }}
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
                  render: (u) => <RoleBadges roles={u.roles} labels={roleLabels} />,
                },
                {
                  key: "status",
                  header: "Status",
                  render: (u) => <StatusBadge status={u.status} />,
                },
                {
                  key: "last",
                  header: "Last sign-in",
                  render: (u) => formatDateTime(u.last_login_at),
                },
                {
                  key: "actions",
                  header: <span className="sr-only">Actions</span>,
                  className: "text-right",
                  render: (u) => (
                    <div className="flex justify-end gap-0.5">
                      <IconAction
                        label={`View details for ${u.display_name}`}
                        icon={Eye}
                        onClick={() => setDetails(u.id)}
                      />
                      {canManage && (
                        <IconAction
                          label={`Edit ${u.display_name}`}
                          icon={Pencil}
                          onClick={() => open("edit", u)}
                        />
                      )}
                      {canManage && u.status === "active" && (
                        <IconAction
                          label={`Send password reset link to ${u.display_name}`}
                          icon={Mail}
                          onClick={() => askResetLink(u)}
                        />
                      )}
                      {canManage && (
                        <IconAction
                          label={`Set a new password for ${u.display_name}`}
                          icon={KeyRound}
                          onClick={() => open("password", u)}
                        />
                      )}
                      {canManage &&
                        u.id !== me?.id &&
                        (u.status === "active" ? (
                          <IconAction
                            label={`Disable ${u.display_name}`}
                            icon={ShieldOff}
                            onClick={() => askToggleStatus(u)}
                            danger
                          />
                        ) : (
                          <IconAction
                            label={`Reactivate ${u.display_name}`}
                            icon={ShieldCheck}
                            onClick={() => askToggleStatus(u)}
                          />
                        ))}
                    </div>
                  ),
                },
              ]}
            />
          )}
        </div>
      )}

      {tab === "invitations" && (
        <div role="tabpanel" aria-label="Invitations">
          <div className="mb-4 max-w-xs">
            <SelectField
              label="Invitation status"
              value={inviteStatus}
              onChange={(e) => setInviteStatus(e.target.value)}
              options={[
                { value: "", label: "All invitations" },
                { value: "pending", label: "Pending" },
                { value: "accepted", label: "Accepted" },
                { value: "expired", label: "Expired" },
                { value: "revoked", label: "Revoked" },
              ]}
            />
          </div>
          {invitations.error ? (
            <ErrorState title="We couldn't load invitations" onRetry={invitations.reload} />
          ) : (
            <DataTable
              caption="Invitations"
              rows={invitations.data}
              loading={invitations.loading}
              empty={{
                icon: Send,
                title: "No invitations",
                description: "Invite an administrator to give them access with their own password.",
              }}
              columns={[
                {
                  key: "email",
                  header: "Invitee",
                  render: (i) => (
                    <div>
                      <p className="font-medium">{i.display_name || i.email}</p>
                      {i.display_name && <p className="text-xs text-muted">{i.email}</p>}
                    </div>
                  ),
                },
                {
                  key: "roles",
                  header: "Roles",
                  render: (i) => <RoleBadges roles={i.roles} labels={roleLabels} />,
                },
                {
                  key: "status",
                  header: "Status",
                  render: (i) => <StatusBadge status={i.status} />,
                },
                { key: "expires", header: "Expires", render: (i) => formatDateTime(i.expires_at) },
                {
                  key: "by",
                  header: "Invited by",
                  render: (i) => i.created_by?.display_name ?? "—",
                },
                {
                  key: "actions",
                  header: <span className="sr-only">Actions</span>,
                  className: "text-right",
                  render: (i) => (
                    <div className="flex justify-end gap-0.5">
                      {canAssign && ["pending", "expired"].includes(i.status) && (
                        <IconAction
                          label={`Resend invitation to ${i.email}`}
                          icon={RotateCcw}
                          onClick={() => askInvitation(i, "resend")}
                        />
                      )}
                      {canManage && i.status === "pending" && (
                        <IconAction
                          label={`Revoke invitation for ${i.email}`}
                          icon={X}
                          onClick={() => askInvitation(i, "revoke")}
                          danger
                        />
                      )}
                    </div>
                  ),
                },
              ]}
            />
          )}
        </div>
      )}

      <Modal
        open={Boolean(dialog)}
        onClose={() => setDialog(null)}
        title={titles[dialog?.mode]}
        description={
          dialog?.mode === "invite"
            ? "They receive a single-use link to set their own password."
            : dialog?.user?.email
        }
        footer={
          <>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button type="submit" form="user-form" disabled={busy}>
              {busy ? "Saving…" : dialog?.mode === "invite" ? "Send invitation" : "Save"}
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
            {["invite", "create"].includes(dialog.mode) && (
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
                label={dialog.mode === "invite" ? "Name (optional)" : "Display name"}
                required={dialog.mode !== "invite"}
                value={dialog.form.display_name}
                onChange={(e) => setForm({ display_name: e.target.value })}
                error={fieldError(error, "display_name")}
              />
            )}
            {["create", "password"].includes(dialog.mode) && (
              <TextField
                label={dialog.mode === "create" ? "Initial password" : "New password"}
                type="password"
                autoComplete="new-password"
                required
                hint="At least 12 characters. Share it securely in person or via a password manager, never by email. Prefer invitations."
                value={dialog.form.password}
                onChange={(e) => setForm({ password: e.target.value })}
                error={fieldError(error, "password")}
              />
            )}
            {dialog.mode !== "password" && dialog.form.roles && roles.data && (
              <RolePicker
                roles={roles.data}
                labels={labels}
                initial={dialog.user?.roles ?? []}
                value={dialog.form.roles}
                onChange={(v) => setForm({ roles: v })}
                error={fieldError(error, "roles")}
              />
            )}
          </form>
        )}
      </Modal>

      {details && (
        <UserDetails
          userId={details}
          roleLabels={roleLabels}
          labels={labels}
          onClose={() => setDetails(null)}
        />
      )}

      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm?.title ?? ""}
        message={confirm?.message ?? ""}
        confirmLabel={confirm?.label}
        tone={confirm?.tone}
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={runConfirmed}
      />
    </>
  );
}

import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Button } from "@/components/ui/Button";
import { selectAuth, userUpdated } from "@/store/slices/authSlice";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { fieldError } from "../components/fieldError";
import { TextField } from "../components/Fields";
import { useNotify } from "../components/notifyContext";

export function AccountPage() {
  const api = useAdminApi();
  const dispatch = useDispatch();
  const notify = useNotify();
  const { user } = useSelector(selectAuth);
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const mismatch = form.confirm && form.confirm !== form.new_password;

  const submit = async (event) => {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.auth.changePassword({
        current_password: form.current_password,
        new_password: form.new_password,
      });
      dispatch(userUpdated(res.data.user));
      setForm({ current_password: "", new_password: "", confirm: "" });
      notify("Password changed. Other devices have been signed out.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Your account"
        breadcrumbs={[{ label: "Account" }]}
        description={`${user?.display_name} · ${user?.email}`}
      />
      <form
        onSubmit={submit}
        className="max-w-md space-y-4 rounded-xl border border-charcoal/10 bg-white p-5"
      >
        <h2 className="font-sans text-base font-semibold">Change password</h2>
        {error && !error.details && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
            {error.message}
          </p>
        )}
        <TextField
          label="Current password"
          type="password"
          autoComplete="current-password"
          required
          value={form.current_password}
          onChange={(e) => setForm({ ...form, current_password: e.target.value })}
          error={fieldError(error, "current_password")}
        />
        <TextField
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          hint="At least 12 characters."
          value={form.new_password}
          onChange={(e) => setForm({ ...form, new_password: e.target.value })}
          error={fieldError(error, "new_password")}
        />
        <TextField
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          required
          value={form.confirm}
          onChange={(e) => setForm({ ...form, confirm: e.target.value })}
          error={mismatch ? "The passwords do not match." : undefined}
        />
        <Button
          type="submit"
          disabled={busy || !form.current_password || !form.new_password || mismatch}
        >
          {busy ? "Saving…" : "Change password"}
        </Button>
      </form>
    </>
  );
}

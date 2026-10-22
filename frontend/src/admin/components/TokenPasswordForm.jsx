import { useEffect, useState } from "react";
import { ButtonLink, Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { fieldError } from "./fieldError";
import { TextField } from "./Fields";

/**
 * Shared flow for token links: verify the token, then let the person choose a
 * password (and, for invitations, confirm their name).
 */
export function TokenPasswordForm({ token, verify, submit, askName = false, submitLabel, onDone }) {
  const [info, setInfo] = useState(null);
  const [invalid, setInvalid] = useState(!token);
  const [form, setForm] = useState({ display_name: "", password: "", confirm: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    let active = true;
    verify(token)
      .then((res) => {
        if (!active) return;
        setInfo(res.data);
        setForm((f) => ({ ...f, display_name: res.data.display_name ?? "" }));
      })
      .catch(() => active && setInvalid(true));
    return () => {
      active = false;
    };
  }, [token, verify]);

  if (invalid)
    return (
      <div className="space-y-4">
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
          This link is invalid, has already been used, or has expired. Ask a super administrator for
          a new one.
        </p>
        <ButtonLink to="/admin/login" variant="outline" className="w-full">
          Go to sign in
        </ButtonLink>
      </div>
    );
  if (!info)
    return (
      <div role="status" aria-label="Checking your link" className="space-y-3">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-10 w-full" />
      </div>
    );

  const mismatch = form.confirm && form.confirm !== form.password;
  const onSubmit = async (event) => {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      const res = await submit({
        token,
        password: form.password,
        ...(askName && { display_name: form.display_name }),
      });
      onDone(res);
    } catch (err) {
      if (err.code === "link_invalid") setInvalid(true);
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <p className="text-sm text-muted">
        Account: <span className="font-medium text-charcoal">{info.email}</span>
        {info.roles?.length > 0 && (
          <>
            {" "}
            ·{" "}
            <span className="capitalize">
              {info.roles.map((r) => r.replace("_", " ")).join(", ")}
            </span>
          </>
        )}
      </p>
      {error && !error.details && error.code !== "link_invalid" && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
          {error.message}
        </p>
      )}
      {askName && (
        <TextField
          label="Your name"
          required
          autoComplete="name"
          value={form.display_name}
          onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          error={fieldError(error, "display_name")}
        />
      )}
      <TextField
        label="New password"
        type="password"
        required
        autoComplete="new-password"
        hint="At least 12 characters."
        value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
        error={fieldError(error, "password")}
      />
      <TextField
        label="Confirm password"
        type="password"
        required
        autoComplete="new-password"
        value={form.confirm}
        onChange={(e) => setForm({ ...form, confirm: e.target.value })}
        error={mismatch ? "The passwords do not match." : undefined}
      />
      <Button
        type="submit"
        className="w-full"
        disabled={busy || !form.password || mismatch || (askName && !form.display_name.trim())}
      >
        {busy ? "Saving…" : submitLabel}
      </Button>
    </form>
  );
}

import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import { Button } from "@/components/ui/Button";
import { loadSession } from "@/store/slices/authSlice";
import { useAdminApi } from "../adminApiContext";
import { fieldError } from "./fieldError";
import { TextField } from "./Fields";
import { useNotify } from "./notifyContext";

/** Recovery codes, shown once after they are created. */
function RecoveryCodes({ codes, onDone }) {
  return (
    <div role="status" className="space-y-3 rounded-lg border border-gold-300 bg-gold-100/60 p-4">
      <p className="text-sm font-semibold">Save your recovery codes now</p>
      <p className="text-sm">
        Each code signs you in once if you lose your phone. Store them somewhere safe (a password
        manager); they won&apos;t be shown again.
      </p>
      <ul aria-label="Recovery codes" className="grid grid-cols-2 gap-2 font-mono text-sm">
        {codes.map((code) => (
          <li key={code} className="rounded bg-white px-2 py-1">
            {code}
          </li>
        ))}
      </ul>
      <Button size="sm" onClick={onDone}>
        I&apos;ve saved them
      </Button>
    </div>
  );
}

/**
 * Two-step sign-in for the signed-in administrator: set up with an authenticator app,
 * see how many recovery codes are left, replace them, or turn it off.
 */
export function MfaSettings() {
  const api = useAdminApi();
  const dispatch = useDispatch();
  const notify = useNotify();
  const [status, setStatus] = useState(null);
  const [setup, setSetup] = useState(null);
  const [codes, setCodes] = useState(null);
  const [form, setForm] = useState({ code: "", password: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api.auth.mfaStatus().then(
      (res) => alive && setStatus(res.data),
      (err) => alive && setError(err),
    );
    return () => {
      alive = false;
    };
  }, [api]);

  const run = async (fn, message) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      setForm({ code: "", password: "" });
      if (res?.data?.recovery_codes) setCodes(res.data.recovery_codes);
      if (res?.data && "enabled" in res.data) setStatus(res.data);
      if (message) notify(message);
      dispatch(loadSession());
      return res;
    } catch (err) {
      setError(err);
      return null;
    } finally {
      setBusy(false);
    }
  };

  if (!status) return null;
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  return (
    <section
      aria-labelledby="mfa-heading"
      className="max-w-xl space-y-4 rounded-xl border border-charcoal/10 bg-white p-5"
    >
      <h2 id="mfa-heading" className="flex items-center gap-2 font-sans text-base font-semibold">
        <ShieldCheck aria-hidden className="size-5 text-sage-700" />
        Two-step sign-in
      </h2>
      {status.required && !status.enabled && (
        <p role="alert" className="rounded-lg bg-gold-100 px-3 py-2 text-sm">
          Your organisation requires two-step sign-in. Set it up to continue using the admin.
        </p>
      )}
      {error && !error.details && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
          {error.message}
        </p>
      )}
      {codes && <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />}

      {!status.enabled && !setup && (
        <>
          <p className="text-sm text-muted">
            After your password, you&apos;ll also enter a code from an authenticator app on your
            phone (for example Google Authenticator, Microsoft Authenticator or 1Password).
          </p>
          <Button
            disabled={busy}
            onClick={async () => {
              const res = await run(() => api.auth.mfaSetup());
              if (res) setSetup(res.data);
            }}
          >
            Set up two-step sign-in
          </Button>
        </>
      )}

      {!status.enabled && setup && (
        <form
          className="space-y-3"
          onSubmit={async (event) => {
            event.preventDefault();
            const res = await run(
              () => api.auth.mfaEnable(form.code),
              "Two-step sign-in is on.",
            );
            if (res) setSetup(null);
          }}
        >
          <ol className="list-decimal space-y-2 pl-5 text-sm">
            <li>
              In your authenticator app, add an account and choose to enter a setup key. On this
              phone you can also{" "}
              <a href={setup.otpauth_uri} className="text-sage-800 underline underline-offset-4">
                open the authenticator app directly
              </a>
              .
            </li>
            <li>
              Account: <strong>{setup.account}</strong> · Key:{" "}
              <code className="rounded bg-cream px-1.5 py-0.5 font-mono text-sm break-all">
                {setup.setup_key}
              </code>{" "}
              (time-based)
            </li>
            <li>Enter the six-digit code the app shows.</li>
          </ol>
          <TextField
            label="Code from the app"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={8}
            value={form.code}
            onChange={set("code")}
            error={fieldError(error, "code")}
          />
          <Button type="submit" disabled={busy || form.code.trim().length < 6}>
            Turn on
          </Button>
        </form>
      )}

      {status.enabled && (
        <>
          <p className="text-sm">
            On since {new Date(status.enabled_at).toLocaleDateString()} ·{" "}
            {status.recovery_codes_left} recovery {status.recovery_codes_left === 1 ? "code" : "codes"}{" "}
            left.
          </p>
          <form className="space-y-3" onSubmit={(event) => event.preventDefault()}>
            <p className="text-sm text-muted">
              To replace your recovery codes or turn two-step sign-in off, confirm with your
              password and a current code.
            </p>
            <TextField
              label="Password"
              type="password"
              autoComplete="current-password"
              value={form.password}
              onChange={set("password")}
              error={fieldError(error, "password")}
            />
            <TextField
              label="Code (from the app, or a recovery code)"
              autoComplete="one-time-code"
              maxLength={20}
              value={form.code}
              onChange={set("code")}
              error={fieldError(error, "code")}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !form.password || !form.code}
                onClick={() =>
                  run(
                    () => api.auth.mfaRecoveryCodes({ password: form.password, code: form.code }),
                    "New recovery codes created.",
                  )
                }
              >
                New recovery codes
              </Button>
              {!status.required && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy || !form.password || !form.code}
                  onClick={() =>
                    run(
                      () => api.auth.mfaDisable({ password: form.password, code: form.code }),
                      "Two-step sign-in is off.",
                    )
                  }
                >
                  Turn off
                </Button>
              )}
            </div>
          </form>
        </>
      )}
    </section>
  );
}

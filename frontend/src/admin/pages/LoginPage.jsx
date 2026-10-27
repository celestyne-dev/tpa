import { LockKeyhole } from "lucide-react";
import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link, Navigate, useSearchParams } from "react-router";
import { LogoMark } from "@/components/layout/Logo";
import { Seo } from "@/components/seo/Seo";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { login, selectAuth } from "@/store/slices/authSlice";
import { TextField } from "../components/Fields";
import { SessionLoading } from "../components/Guards";
import { safeNextPath } from "../components/safeNextPath";

export function LoginPage() {
  const dispatch = useDispatch();
  const { status, error, sessionExpired } = useSelector(selectAuth);
  const [params] = useSearchParams();
  const next = safeNextPath(params.get("next"));
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") return <Navigate to={next} replace />;
  if (status === "idle" || status === "loading") return <SessionLoading />;

  const onSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    await dispatch(login({ email: form.email, password: form.password }));
    setSubmitting(false);
    setForm((f) => ({ ...f, password: "" }));
  };

  const message =
    error?.status === 429
      ? "Too many sign-in attempts. Please wait a few minutes and try again."
      : error?.status === 401
        ? "Invalid email or password."
        : error
          ? "We couldn't sign you in right now. Please try again."
          : null;

  return (
    <div className="flex min-h-dvh items-center justify-center bg-cream px-4 py-12">
      <Seo title="Staff sign in" path="/admin/login" noIndex />
      <div className="w-full max-w-sm rounded-2xl border border-charcoal/10 bg-ivory p-8 shadow-lift">
        <div className="mb-6 flex items-center gap-3">
          <LogoMark />
          <div>
            <h1 className="text-2xl font-medium">Staff sign in</h1>
            <p className="text-sm text-muted">Think Positive Always</p>
          </div>
        </div>
        {sessionExpired && (
          <div className="mb-4">
            <Notice title="Your session has ended">Please sign in again to continue.</Notice>
          </div>
        )}
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <TextField
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <TextField
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          {message && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
              {message}
            </p>
          )}
          <Button
            type="submit"
            className="w-full"
            disabled={submitting || !form.email || !form.password}
          >
            <LockKeyhole aria-hidden />
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <details className="mt-5 text-sm">
          <summary className="cursor-pointer text-sage-800 underline underline-offset-4">
            Forgot your password?
          </summary>
          <p className="mt-2 text-muted">
            For security, staff passwords are reset by an administrator. Ask a team administrator to
            send you a reset link from Users &amp; access; it arrives by email and works once.
          </p>
        </details>
        <div className="mt-6 space-y-2 border-t border-charcoal/10 pt-5 text-sm text-muted">
          <p>
            Shopping or reading with us?{" "}
            <Link to="/login" className="text-charcoal underline underline-offset-4">
              Customer log in
            </Link>
          </p>
          <p>
            <Link to="/" className="underline underline-offset-4 hover:text-charcoal">
              Back to the website
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

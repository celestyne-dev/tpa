import { useState } from "react";
import { useDispatch } from "react-redux";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { InputField } from "@/components/ui/FormField";
import { routes } from "@/config/navigation";
import { customerSignedIn, fetchCustomer } from "@/store/slices/customerSlice";
import { fieldErrors, safeNext } from "../hooks";

function AuthCard({ title, intro, children }) {
  return (
    <Container size="narrow" className="py-14 sm:py-20">
      <div className="mx-auto max-w-md rounded-[var(--radius-card)] border border-charcoal/10 bg-white p-7 shadow-soft sm:p-9">
        <h1 className="text-3xl font-medium">{title}</h1>
        {intro && <p className="mt-2 text-muted">{intro}</p>}
        <div className="mt-7">{children}</div>
      </div>
    </Container>
  );
}

export function SignInForm({ onSignedIn, compact = false }) {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  const [form, setForm] = useState({ email: "", password: "" });
  const [state, setState] = useState({ busy: false, error: null });
  const submit = async (event) => {
    event.preventDefault();
    setState({ busy: true, error: null });
    try {
      const res = await shopApi.login(form);
      dispatch(customerSignedIn(res.data.customer));
      onSignedIn?.(res.data.customer);
    } catch (error) {
      setState({ busy: false, error });
    }
  };
  return (
    <form onSubmit={submit} className="space-y-4" noValidate={false}>
      <InputField
        label="Email"
        type="email"
        autoComplete="email"
        required
        value={form.email}
        onChange={(e) => setForm({ ...form, email: e.target.value })}
      />
      <InputField
        label="Password"
        type="password"
        autoComplete="current-password"
        required
        value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
      />
      {state.error && (
        <p role="alert" className="text-sm text-red-800">
          {state.error.message}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={state.busy}>
        {state.busy ? "Signing in…" : "Sign in"}
      </Button>
      {!compact && (
        <p className="text-center text-sm">
          <Link to={routes.resetPassword} className="underline underline-offset-4">
            Forgot your password?
          </Link>
        </p>
      )}
    </form>
  );
}

export function RegisterForm({ onRegistered }) {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  const [form, setForm] = useState({
    display_name: "",
    email: "",
    password: "",
    accept_terms: false,
  });
  const [state, setState] = useState({ busy: false, error: null, done: false });
  const errors = fieldErrors(state.error);
  const submit = async (event) => {
    event.preventDefault();
    setState({ busy: true, error: null, done: false });
    try {
      const res = await shopApi.register(form);
      if (res.data.signed_in) {
        dispatch(customerSignedIn(res.data.customer));
        onRegistered?.(res.data.customer);
      } else {
        setState({ busy: false, error: null, done: true });
      }
    } catch (error) {
      setState({ busy: false, error, done: false });
    }
  };
  if (state.done) {
    return (
      <p role="status" className="rounded-xl bg-sage-50 p-4 text-sm">
        Check your inbox: we've sent you an email with the next step. If you already have an
        account, the email explains how to sign in.
      </p>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <InputField
        label="Your name (optional)"
        autoComplete="name"
        value={form.display_name}
        error={errors.display_name}
        onChange={(e) => setForm({ ...form, display_name: e.target.value })}
      />
      <InputField
        label="Email"
        type="email"
        autoComplete="email"
        required
        value={form.email}
        error={errors.email}
        onChange={(e) => setForm({ ...form, email: e.target.value })}
      />
      <InputField
        label="Password"
        type="password"
        autoComplete="new-password"
        required
        minLength={12}
        hint="At least 12 characters."
        value={form.password}
        error={errors.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
      />
      <label className="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          className="mt-1 size-4 accent-sage-700"
          checked={form.accept_terms}
          onChange={(e) => setForm({ ...form, accept_terms: e.target.checked })}
          required
        />
        <span>
          I agree to the{" "}
          <Link to={routes.terms} className="underline underline-offset-4">
            terms
          </Link>{" "}
          and{" "}
          <Link to={routes.privacy} className="underline underline-offset-4">
            privacy policy
          </Link>
          .
        </span>
      </label>
      {errors.accept_terms && (
        <p role="alert" className="text-sm text-red-800">
          {errors.accept_terms}
        </p>
      )}
      {state.error && !Object.keys(errors).length && (
        <p role="alert" className="text-sm text-red-800">
          {state.error.message}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={state.busy}>
        {state.busy ? "Creating your account…" : "Create account"}
      </Button>
    </form>
  );
}

export function SignInPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = safeNext(params.get("next"));
  return (
    <>
      <Seo title="Sign in" path={routes.signIn} noIndex />
      <AuthCard title="Sign in" intro="Access your library, downloads and orders.">
        <SignInForm onSignedIn={() => navigate(next, { replace: true })} />
        <p className="mt-6 border-t border-charcoal/10 pt-6 text-center text-sm">
          New here?{" "}
          <Link
            to={`${routes.register}?next=${encodeURIComponent(next)}`}
            className="font-medium underline underline-offset-4"
          >
            Create an account
          </Link>
        </p>
      </AuthCard>
    </>
  );
}

export function RegisterPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = safeNext(params.get("next"));
  return (
    <>
      <Seo title="Create an account" path={routes.register} noIndex />
      <AuthCard
        title="Create your account"
        intro="Your purchases and free resources are kept in your library."
      >
        <RegisterForm onRegistered={() => navigate(next, { replace: true })} />
        <p className="mt-6 border-t border-charcoal/10 pt-6 text-center text-sm">
          Already have an account?{" "}
          <Link
            to={`${routes.signIn}?next=${encodeURIComponent(next)}`}
            className="font-medium underline underline-offset-4"
          >
            Sign in
          </Link>
        </p>
      </AuthCard>
    </>
  );
}

function tokenFromHash() {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
}

export function VerifyEmailPage() {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  const [state, setState] = useState({ status: "idle", message: "" });
  const verify = async () => {
    setState({ status: "busy", message: "" });
    try {
      await shopApi.verifyEmail(tokenFromHash());
      dispatch(fetchCustomer({ force: true }));
      setState({ status: "done", message: "" });
    } catch (error) {
      setState({ status: "error", message: error.message });
    }
  };
  return (
    <>
      <Seo title="Confirm your email" path={routes.verifyEmail} noIndex />
      <AuthCard title="Confirm your email">
        {state.status === "done" ? (
          <div role="status" className="space-y-4">
            <p>Thank you — your email address is confirmed.</p>
            <Link to={routes.account} className="font-medium underline underline-offset-4">
              Go to your account
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-muted">Press the button to confirm this email address.</p>
            {state.status === "error" && (
              <p role="alert" className="text-sm text-red-800">
                {state.message}
              </p>
            )}
            <Button onClick={verify} disabled={state.status === "busy"} className="w-full">
              {state.status === "busy" ? "Confirming…" : "Confirm my email"}
            </Button>
          </div>
        )}
      </AuthCard>
    </>
  );
}

export function ResetPasswordPage() {
  const shopApi = useShopApi();
  const token = tokenFromHash();
  const [value, setValue] = useState("");
  const [state, setState] = useState({ status: "idle", error: null, message: "" });
  const submit = async (event) => {
    event.preventDefault();
    setState({ status: "busy", error: null, message: "" });
    try {
      if (token) {
        await shopApi.completePasswordReset(token, value);
        setState({
          status: "done",
          error: null,
          message: "Your password has been changed. You can sign in now.",
        });
      } else {
        const res = await shopApi.requestPasswordReset(value);
        setState({ status: "done", error: null, message: res.data.message });
      }
    } catch (error) {
      setState({ status: "idle", error, message: "" });
    }
  };
  const errors = fieldErrors(state.error);
  return (
    <>
      <Seo title="Reset your password" path={routes.resetPassword} noIndex />
      <AuthCard title={token ? "Choose a new password" : "Reset your password"}>
        {state.status === "done" ? (
          <div role="status" className="space-y-4">
            <p>{state.message}</p>
            <Link to={routes.signIn} className="font-medium underline underline-offset-4">
              Sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <InputField
              label={token ? "New password" : "Email"}
              type={token ? "password" : "email"}
              autoComplete={token ? "new-password" : "email"}
              required
              value={value}
              error={errors.password}
              hint={
                token ? "At least 12 characters." : "We'll email you a link if an account exists."
              }
              onChange={(e) => setValue(e.target.value)}
            />
            {state.error && !errors.password && (
              <p role="alert" className="text-sm text-red-800">
                {state.error.message}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={state.status === "busy"}>
              {token ? "Save new password" : "Send reset link"}
            </Button>
          </form>
        )}
      </AuthCard>
    </>
  );
}

import { MailCheck } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useDispatch } from "react-redux";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useShopApi } from "@/components/products/shopApiContext";
import { safeNextPath } from "@/admin/components/safeNextPath";
import { Seo } from "@/components/seo/Seo";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { InputField } from "@/components/ui/FormField";
import { routes } from "@/config/navigation";
import { useAccountStatus } from "@/hooks/useAccountStatus";
import { customerSignedIn, fetchCustomer } from "@/store/slices/customerSlice";
import { authErrorMessage } from "../authMessages";
import { fieldErrors, safeNext } from "../hooks";
import { PasswordField, PasswordRequirements } from "../PasswordField";
import { meetsPasswordRules } from "../passwordRules";

function AuthCard({ title, intro, children }) {
  return (
    <Container size="narrow" className="py-14 sm:py-20">
      <div className="mx-auto max-w-md rounded-[var(--radius-card)] border border-charcoal/10 bg-white p-6 shadow-soft sm:p-9">
        <h1 className="text-3xl font-medium">{title}</h1>
        {intro && <p className="mt-2 text-muted">{intro}</p>}
        <div className="mt-7">{children}</div>
      </div>
    </Container>
  );
}

function Alert({ children, tone = "error" }) {
  return (
    <p
      role={tone === "error" ? "alert" : "status"}
      className={
        tone === "error"
          ? "rounded-xl bg-red-50 p-3 text-sm text-red-800"
          : "rounded-xl bg-sage-50 p-3 text-sm text-charcoal"
      }
    >
      {children}
    </p>
  );
}

function tokenFromHash() {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
}

// ---- sign in ------------------------------------------------------------------------------

export function SignInForm({ onSignedIn, onBeforeSubmit, compact = false }) {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  const [form, setForm] = useState({ email: "", password: "", remember: false });
  const [state, setState] = useState({ busy: false, error: null });
  const submit = async (event) => {
    event.preventDefault();
    setState({ busy: true, error: null });
    onBeforeSubmit?.();
    try {
      const res = await shopApi.login(form);
      dispatch(customerSignedIn(res.data.customer));
      onSignedIn?.(res.data.customer);
    } catch (error) {
      setState({ busy: false, error });
    }
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <InputField
        label="Email"
        type="email"
        autoComplete="email"
        required
        value={form.email}
        onChange={(e) => setForm({ ...form, email: e.target.value })}
      />
      <PasswordField
        label="Password"
        autoComplete="current-password"
        required
        value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
      />
      <label className="flex items-center gap-3 text-sm">
        <input
          type="checkbox"
          className="size-4 accent-sage-700"
          checked={form.remember}
          onChange={(e) => setForm({ ...form, remember: e.target.checked })}
        />
        <span>
          Keep me signed in on this device
          <span className="block text-muted">Don't tick this on a shared computer.</span>
        </span>
      </label>
      {state.error && <Alert>{authErrorMessage(state.error)}</Alert>}
      <Button type="submit" className="w-full" disabled={state.busy}>
        {state.busy ? "Signing in…" : "Log in"}
      </Button>
      {!compact && (
        <p className="text-center text-sm">
          <Link to={routes.forgotPassword} className="underline underline-offset-4">
            Forgot your password?
          </Link>
        </p>
      )}
    </form>
  );
}

/**
 * Send people who arrive already signed in straight on. Sign-ins that happen on the page
 * itself navigate on their own (with their own state), so they're excluded via `handled`.
 */
function useRedirectWhenSignedIn(next) {
  const { status } = useAccountStatus();
  const navigate = useNavigate();
  const handledRef = useRef(false);
  useEffect(() => {
    if (status === "signed_in" && !handledRef.current) navigate(next, { replace: true });
  }, [status, next, navigate]);
  return useCallback(() => {
    handledRef.current = true;
  }, []);
}

/**
 * Staff use their own sign-in (separate accounts, sessions and rate limits). A staff-only
 * return path (/admin/…) is handed over to it; anything else stays with the customer login.
 */
function staffSignInHref(rawNext) {
  const adminNext = safeNextPath(rawNext);
  return adminNext === "/admin"
    ? "/admin/login"
    : `/admin/login?next=${encodeURIComponent(adminNext)}`;
}

export function SignInPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const rawNext = params.get("next");
  const next = safeNext(rawNext);
  const markHandled = useRedirectWhenSignedIn(next);
  const staffHref = staffSignInHref(rawNext);
  const wantsStaffArea = staffHref !== "/admin/login" || rawNext === "/admin";
  return (
    <>
      <Seo title="Log in" path={routes.signIn} noIndex />
      <AuthCard title="Log in" intro="Access your library, downloads and orders.">
        {params.get("reason") === "expired" && (
          <div className="mb-5">
            <Alert tone="info">Your session has ended. Please log in again to continue.</Alert>
          </div>
        )}
        {wantsStaffArea && (
          <div className="mb-5">
            <Alert tone="info">
              That page is for the Think Positive Always team.{" "}
              <Link to={staffHref} className="font-medium underline underline-offset-4">
                Sign in as staff
              </Link>{" "}
              to continue.
            </Alert>
          </div>
        )}
        {params.get("reset") === "1" && (
          <div className="mb-5">
            <Alert tone="info">
              Your password has been changed. Log in with your new password.
            </Alert>
          </div>
        )}
        <SignInForm
          onBeforeSubmit={markHandled}
          onSignedIn={() => navigate(next, { replace: true })}
        />
        <p className="mt-6 border-t border-charcoal/10 pt-6 text-center text-sm">
          New here?{" "}
          <Link
            to={`${routes.register}?next=${encodeURIComponent(next)}`}
            className="font-medium underline underline-offset-4"
          >
            Create an account
          </Link>
        </p>
        <p className="mt-3 text-center text-sm">
          Bought as a guest?{" "}
          <Link to={routes.purchases} className="underline underline-offset-4">
            Find your purchase
          </Link>
        </p>
        <p className="mt-6 text-center text-xs text-muted">
          Part of the team?{" "}
          <Link to={staffHref} className="underline underline-offset-4 hover:text-charcoal">
            Sign in as staff
          </Link>
        </p>
      </AuthCard>
    </>
  );
}

// ---- registration -------------------------------------------------------------------------

function NewsletterOptIn({ checked, onChange, status }) {
  if (!status?.signup_open) return null;
  return (
    <label className="flex items-start gap-3 rounded-xl bg-cream p-3 text-sm">
      <input
        type="checkbox"
        className="mt-1 size-4 shrink-0 accent-sage-700"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="font-medium">Optional:</span> {status.consent_text}
        <span className="mt-1 block text-muted">
          We'll email you to confirm first. Leave this unticked if you'd rather not.
        </span>
      </span>
    </label>
  );
}

export function RegisterForm({ onRegistered, onBeforeSubmit }) {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  const rulesId = useId();
  const [form, setForm] = useState({
    display_name: "",
    email: "",
    password: "",
    password_confirm: "",
    accept_terms: false,
    newsletter_opt_in: false,
  });
  const [newsletter, setNewsletter] = useState(null);
  const [local, setLocal] = useState({});
  const [state, setState] = useState({ busy: false, error: null, done: false });
  useEffect(() => {
    let alive = true;
    shopApi
      .newsletterStatus?.()
      .then((res) => alive && setNewsletter(res?.data ?? null))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [shopApi]);
  const errors = { ...fieldErrors(state.error), ...local };
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (event) => {
    event.preventDefault();
    const problems = {};
    if (!form.display_name.trim()) problems.display_name = "Enter your name.";
    if (!meetsPasswordRules(form.password, form.email))
      problems.password = "Choose a password that meets all the requirements.";
    if (form.password !== form.password_confirm)
      problems.password_confirm = "The passwords don't match.";
    if (!form.accept_terms) problems.accept_terms = "Please accept the terms and privacy policy.";
    setLocal(problems);
    if (Object.keys(problems).length) return;
    setState({ busy: true, error: null, done: false });
    onBeforeSubmit?.();
    try {
      const res = await shopApi.register({
        ...form,
        newsletter_opt_in: Boolean(newsletter?.signup_open && form.newsletter_opt_in),
        newsletter_consent_version: newsletter?.consent_version,
      });
      if (res.data.signed_in) {
        dispatch(customerSignedIn(res.data.customer));
        onRegistered?.(res.data.customer, res.data.newsletter);
      } else {
        setState({ busy: false, error: null, done: true });
      }
    } catch (error) {
      setState({ busy: false, error, done: false });
    }
  };

  if (state.done) {
    return (
      <div role="status" className="space-y-3 rounded-xl bg-sage-50 p-4 text-sm">
        <MailCheck aria-hidden className="size-6 text-sage-700" />
        <p>
          Check your inbox: we've sent an email with the next step. If you already have an account,
          the email explains how to log in or reset your password.
        </p>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <InputField
        label="Your name"
        autoComplete="name"
        required
        maxLength={120}
        value={form.display_name}
        error={errors.display_name}
        onChange={set("display_name")}
      />
      <InputField
        label="Email"
        type="email"
        autoComplete="email"
        required
        value={form.email}
        error={errors.email}
        onChange={set("email")}
      />
      <PasswordField
        label="Password"
        autoComplete="new-password"
        required
        aria-describedby={rulesId}
        value={form.password}
        error={errors.password}
        onChange={set("password")}
      />
      <PasswordRequirements id={rulesId} password={form.password} email={form.email} />
      <PasswordField
        label="Confirm password"
        autoComplete="new-password"
        required
        value={form.password_confirm}
        error={errors.password_confirm}
        onChange={set("password_confirm")}
      />
      <NewsletterOptIn
        status={newsletter}
        checked={form.newsletter_opt_in}
        onChange={(value) => setForm({ ...form, newsletter_opt_in: value })}
      />
      <label className="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          className="mt-1 size-4 accent-sage-700"
          checked={form.accept_terms}
          aria-invalid={errors.accept_terms ? true : undefined}
          onChange={(e) => setForm({ ...form, accept_terms: e.target.checked })}
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
      {errors.accept_terms && <Alert>{errors.accept_terms}</Alert>}
      {state.error && !Object.keys(fieldErrors(state.error)).length && (
        <Alert>{authErrorMessage(state.error)}</Alert>
      )}
      <Button type="submit" className="w-full" disabled={state.busy}>
        {state.busy ? "Creating your account…" : "Create account"}
      </Button>
    </form>
  );
}

export function RegisterPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const next = safeNext(params.get("next"));
  const markHandled = useRedirectWhenSignedIn(next);
  return (
    <>
      <Seo title="Create an account" path={routes.register} noIndex />
      <AuthCard
        title="Create your account"
        intro="Your purchases and free resources are kept in your library."
      >
        <RegisterForm
          onBeforeSubmit={markHandled}
          onRegistered={(_customer, newsletter) =>
            navigate(next, { replace: true, state: { welcome: true, newsletter } })
          }
        />
        <p className="mt-6 border-t border-charcoal/10 pt-6 text-center text-sm">
          Already have an account?{" "}
          <Link
            to={`${routes.signIn}?next=${encodeURIComponent(next)}`}
            className="font-medium underline underline-offset-4"
          >
            Log in
          </Link>
        </p>
      </AuthCard>
    </>
  );
}

// ---- email verification -------------------------------------------------------------------

/** Ask for a new confirmation link (signed in: for this account; otherwise by email). */
export function ResendVerification({ signedIn }) {
  const shopApi = useShopApi();
  const [email, setEmail] = useState("");
  const [state, setState] = useState({ busy: false, message: "", error: null });
  const send = async (event) => {
    event?.preventDefault();
    setState({ busy: true, message: "", error: null });
    try {
      const res = signedIn
        ? await shopApi.resendVerification()
        : await shopApi.requestVerification(email);
      const message = signedIn
        ? res.data.already_verified
          ? "Your email address is already confirmed."
          : "We've sent a new confirmation link. Check your inbox (and spam folder)."
        : res.data.message;
      setState({ busy: false, message, error: null });
    } catch (error) {
      setState({ busy: false, message: "", error });
    }
  };
  return (
    <div className="space-y-3">
      {state.message && <Alert tone="info">{state.message}</Alert>}
      {state.error && <Alert>{authErrorMessage(state.error)}</Alert>}
      {signedIn ? (
        <Button variant="outline" onClick={send} disabled={state.busy}>
          {state.busy ? "Sending…" : "Send a new confirmation link"}
        </Button>
      ) : (
        <form onSubmit={send} className="space-y-3">
          <InputField
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Button type="submit" variant="outline" className="w-full" disabled={state.busy}>
            {state.busy ? "Sending…" : "Send a new confirmation link"}
          </Button>
        </form>
      )}
    </div>
  );
}

export function VerifyEmailPage() {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  const { status } = useAccountStatus();
  const [token] = useState(tokenFromHash);
  const [state, setState] = useState({ status: "idle", error: null });
  // Confirmation needs a click (link scanners that prefetch URLs can't use it up).
  const verify = async () => {
    setState({ status: "busy", error: null });
    try {
      await shopApi.verifyEmail(token);
      dispatch(fetchCustomer({ force: true }));
      setState({ status: "done", error: null });
    } catch (error) {
      setState({ status: "error", error });
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
        ) : token && state.status !== "error" ? (
          <div className="space-y-4">
            <p className="text-muted">Press the button to confirm this email address.</p>
            <Button onClick={verify} disabled={state.status === "busy"} className="w-full">
              {state.status === "busy" ? "Confirming…" : "Confirm my email"}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {state.status === "error" ? (
              <Alert>
                {state.error?.status === 400
                  ? "This confirmation link is invalid, has already been used or has expired."
                  : authErrorMessage(state.error)}
              </Alert>
            ) : (
              <p className="text-muted">
                Open the link in the email we sent you to confirm your address.
              </p>
            )}
            <p className="text-sm">Need a new link?</p>
            <ResendVerification signedIn={status === "signed_in"} />
          </div>
        )}
      </AuthCard>
    </>
  );
}

// ---- password recovery --------------------------------------------------------------------

export function ForgotPasswordPage() {
  const shopApi = useShopApi();
  const [email, setEmail] = useState("");
  const [state, setState] = useState({ busy: false, message: "", error: null, sent: 0 });
  const send = async (event) => {
    event.preventDefault();
    setState((s) => ({ ...s, busy: true, error: null }));
    try {
      const res = await shopApi.requestPasswordReset(email);
      setState((s) => ({ busy: false, message: res.data.message, error: null, sent: s.sent + 1 }));
    } catch (error) {
      setState((s) => ({ ...s, busy: false, error }));
    }
  };
  return (
    <>
      <Seo title="Forgot your password" path={routes.forgotPassword} noIndex />
      <AuthCard
        title="Forgot your password?"
        intro="Enter your email and we'll send you a link to choose a new password."
      >
        <form onSubmit={send} className="space-y-4">
          {state.message && (
            <Alert tone="info">
              {state.message} The link works once and expires after a short time.
            </Alert>
          )}
          {state.error && <Alert>{authErrorMessage(state.error)}</Alert>}
          <InputField
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Button type="submit" className="w-full" disabled={state.busy}>
            {state.busy ? "Sending…" : state.sent ? "Send the link again" : "Send reset link"}
          </Button>
        </form>
        <p className="mt-6 border-t border-charcoal/10 pt-6 text-center text-sm">
          Remembered it?{" "}
          <Link to={routes.signIn} className="font-medium underline underline-offset-4">
            Log in
          </Link>
        </p>
      </AuthCard>
    </>
  );
}

export function ResetPasswordPage() {
  const shopApi = useShopApi();
  const navigate = useNavigate();
  const rulesId = useId();
  const [token] = useState(tokenFromHash);
  const [form, setForm] = useState({ password: "", confirm: "" });
  const [local, setLocal] = useState({});
  const [state, setState] = useState({ busy: false, error: null });
  const errors = { ...fieldErrors(state.error), ...local };
  const submit = async (event) => {
    event.preventDefault();
    const problems = {};
    if (!meetsPasswordRules(form.password, ""))
      problems.password = "Choose a password that meets all the requirements.";
    if (form.password !== form.confirm) problems.confirm = "The passwords don't match.";
    setLocal(problems);
    if (Object.keys(problems).length) return;
    setState({ busy: true, error: null });
    try {
      await shopApi.completePasswordReset(token, form.password);
      navigate(`${routes.signIn}?reset=1`, { replace: true });
    } catch (error) {
      setState({ busy: false, error });
    }
  };
  const invalid = !token || state.error?.code === "link_invalid";
  return (
    <>
      <Seo title="Choose a new password" path={routes.resetPassword} noIndex />
      <AuthCard title="Choose a new password">
        {invalid ? (
          <div className="space-y-4">
            <Alert>
              {token
                ? "This reset link is invalid, has already been used or has expired."
                : "Open the reset link from your email to choose a new password."}
            </Alert>
            <Link to={routes.forgotPassword} className="font-medium underline underline-offset-4">
              Request a new reset link
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4" noValidate>
            <PasswordField
              label="New password"
              autoComplete="new-password"
              required
              aria-describedby={rulesId}
              value={form.password}
              error={errors.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <PasswordRequirements id={rulesId} password={form.password} />
            <PasswordField
              label="Confirm new password"
              autoComplete="new-password"
              required
              value={form.confirm}
              error={errors.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })}
            />
            <p className="text-sm text-muted">
              For your security you'll be signed out everywhere and asked to log in again.
            </p>
            {state.error && !errors.password && <Alert>{authErrorMessage(state.error)}</Alert>}
            <Button type="submit" className="w-full" disabled={state.busy}>
              {state.busy ? "Saving…" : "Save new password"}
            </Button>
          </form>
        )}
      </AuthCard>
    </>
  );
}

import { MailCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useShopApi } from "@/components/products/shopApiContext";
import { Button } from "@/components/ui/Button";
import { cn } from "@/utils/format";
import { ConsentCheckbox, Honeypot, SignupInput } from "./SignupFields";
import { EMAIL_PATTERN, signupErrorMessage, toneClasses } from "./signupUtils";
import { useNewsletterStatus } from "./useNewsletterStatus";

const EMPTY = { email: "", first_name: "", consent: false, website: "" };

/**
 * The Positive Reset signup form (double opt-in). Every form on the site uses this one
 * component and the one subscribe endpoint (POST /newsletter/subscribe). It renders only
 * while the backend's readiness check reports sign-ups open; the consent wording and
 * version come from the API, so what people agree to is exactly what is recorded.
 *
 * The public response is the same for new, pending and existing subscribers (so the form
 * never reveals whether an address is on the list); existing subscribers get a short email
 * instead and nothing about their subscription changes.
 */
export function NewsletterSignupForm({
  source = "other",
  sourceDetail = "",
  showFirstName = true,
  compact = false,
  tone = "dark",
  emailId,
  className,
}) {
  const shopApi = useShopApi();
  const { status, isOpen, refresh } = useNewsletterStatus();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [state, setState] = useState({ phase: "idle", message: "" });
  const started = useRef(0);
  const formRef = useRef(null);
  const doneRef = useRef(null);
  const t = toneClasses(tone);

  useEffect(() => {
    started.current = Date.now();
  }, []);

  useEffect(() => {
    if (state.phase === "done") doneRef.current?.focus();
  }, [state.phase]);

  if (!isOpen && state.phase !== "done") return null;

  const focusFirstInvalid = () =>
    requestAnimationFrame(() => formRef.current?.querySelector('[aria-invalid="true"]')?.focus());

  const submit = async (event) => {
    event.preventDefault();
    if (state.phase === "sending") return;
    const next = {};
    if (!EMAIL_PATTERN.test(form.email.trim())) next.email = "Enter a valid email address.";
    if (!form.consent) next.consent = "Please tick the box to agree to receive emails.";
    setErrors(next);
    if (Object.keys(next).length) {
      setState({ phase: "idle", message: "" });
      focusFirstInvalid();
      return;
    }
    setState({ phase: "sending", message: "" });
    try {
      const res = await shopApi.subscribe({
        email: form.email.trim(),
        first_name: showFirstName && !compact ? form.first_name.trim() : "",
        consent: true,
        consent_version: status.consent_version,
        source,
        source_detail: sourceDetail,
        website: form.website,
        elapsed_ms: Date.now() - started.current,
      });
      setState({ phase: "done", message: res?.data?.message ?? "" });
    } catch (error) {
      const code = error?.details?.code;
      if (code === "consent_changed") {
        // The wording changed since the page loaded: show the new text, untick, ask again.
        await refresh();
        setForm((f) => ({ ...f, consent: false }));
      } else if (error?.status === 409) {
        // Sign-ups were closed on the server: switch every placement to the closed state.
        refresh();
      }
      const fieldErrors = error?.details ?? {};
      setErrors({
        email: fieldErrors.email?.join?.(" "),
        consent: fieldErrors.consent?.join?.(" "),
      });
      setState({ phase: "error", message: signupErrorMessage(error) });
      if (fieldErrors.email || fieldErrors.consent) focusFirstInvalid();
    }
  };

  if (state.phase === "done") {
    return (
      <div
        ref={doneRef}
        tabIndex={-1}
        role="status"
        className={cn("mx-auto max-w-lg text-center outline-none", className)}
      >
        <MailCheck aria-hidden className="mx-auto size-8 text-gold-300" />
        <p className={cn("mt-3 text-lg font-medium", t.label)}>Almost there — check your inbox.</p>
        <p className={cn("mt-1 text-[0.95rem]", t.hint)}>
          {state.message} We&apos;ll only add you once you click the confirmation link. If it
          doesn&apos;t arrive in a few minutes, check your spam folder.
        </p>
        <p className={cn("mt-2 text-sm", t.hint)}>
          Already subscribed? We&apos;ll send you a short note instead, and nothing about your
          subscription changes.
        </p>
      </div>
    );
  }

  const sending = state.phase === "sending";
  return (
    <form
      ref={formRef}
      noValidate
      onSubmit={submit}
      aria-busy={sending || undefined}
      className={cn("relative mx-auto max-w-lg space-y-4", className)}
      aria-label={`Subscribe to ${status?.name ?? "The Positive Reset"}`}
    >
      <div className={cn("grid gap-3", !compact && showFirstName && "sm:grid-cols-2")}>
        {showFirstName && !compact && (
          <SignupInput
            tone={tone}
            label="First name"
            optional
            autoComplete="given-name"
            maxLength={80}
            value={form.first_name}
            onChange={(e) => setForm({ ...form, first_name: e.target.value })}
          />
        )}
        <SignupInput
          id={emailId}
          tone={tone}
          label="Email address"
          type="email"
          required
          autoComplete="email"
          inputMode="email"
          maxLength={254}
          value={form.email}
          error={errors.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
      </div>
      <ConsentCheckbox
        tone={tone}
        text={status?.consent_text}
        checked={form.consent}
        error={errors.consent}
        required
        onChange={(consent) => setForm({ ...form, consent })}
      />
      <Honeypot value={form.website} onChange={(website) => setForm({ ...form, website })} />
      {state.phase === "error" && (
        <p role="alert" className={cn("text-sm", t.error)}>
          {state.message}
        </p>
      )}
      <Button
        type="submit"
        variant={tone === "dark" ? "light" : undefined}
        disabled={sending}
        className="w-full sm:w-auto"
      >
        {sending ? "Subscribing…" : "Subscribe"}
      </Button>
      <p className={cn("text-xs", t.hint)}>
        We&apos;ll email you to confirm. Every email has a one-click unsubscribe link, and we never
        sell your address.
      </p>
    </form>
  );
}

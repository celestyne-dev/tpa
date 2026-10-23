import { MailCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useShopApi } from "@/components/products/shopApiContext";
import { Button } from "@/components/ui/Button";
import { useSite } from "@/hooks/useContent";
import { cn } from "@/utils/format";
import { ConsentCheckbox, Honeypot, SignupInput } from "./SignupFields";
import { EMAIL_PATTERN, signupErrorMessage, toneClasses } from "./signupUtils";

/**
 * The Positive Reset signup form (double opt-in). Every form on the site uses this one
 * component and the one subscribe endpoint. The consent wording is refreshed from the API
 * so what people agree to is exactly what is recorded.
 */
export function NewsletterSignupForm({
  source = "other",
  sourceDetail = "",
  showFirstName = true,
  compact = false,
  tone = "dark",
  className,
}) {
  const shopApi = useShopApi();
  const { data: site } = useSite();
  const [status, setStatus] = useState(() => site?.newsletter ?? null);
  const [form, setForm] = useState({ email: "", first_name: "", consent: false, website: "" });
  const [errors, setErrors] = useState({});
  const [state, setState] = useState({ phase: "idle", message: "" });
  const started = useRef(0);
  const t = toneClasses(tone);

  useEffect(() => {
    started.current = Date.now();
    let alive = true;
    shopApi
      .newsletterStatus?.()
      .then((res) => {
        const live = res?.data;
        if (alive && live)
          setStatus((prev) => ({
            ...prev,
            is_open: live.signup_open,
            consent_text: live.consent_text,
            consent_version: live.consent_version,
          }));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [shopApi]);

  if (!status?.is_open) return null;

  const submit = async (event) => {
    event.preventDefault();
    const next = {};
    if (!EMAIL_PATTERN.test(form.email.trim())) next.email = "Enter a valid email address.";
    if (!form.consent) next.consent = "Please tick the box to agree to receive emails.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setState({ phase: "sending", message: "" });
    try {
      const res = await shopApi.subscribe({
        email: form.email.trim(),
        first_name: form.first_name.trim(),
        consent: true,
        consent_version: status.consent_version,
        source,
        source_detail: sourceDetail,
        website: form.website,
        elapsed_ms: Date.now() - started.current,
      });
      setState({ phase: "done", message: res?.data?.message ?? "" });
    } catch (error) {
      if (error?.details?.code === "consent_changed") {
        const live = (await shopApi.newsletterStatus()).data;
        setStatus((prev) => ({
          ...prev,
          consent_text: live.consent_text,
          consent_version: live.consent_version,
        }));
        setForm((f) => ({ ...f, consent: false }));
      }
      const fieldErrors = error?.details ?? {};
      setErrors({
        email: fieldErrors.email?.join?.(" "),
        consent: fieldErrors.consent?.join?.(" "),
      });
      setState({ phase: "error", message: signupErrorMessage(error) });
    }
  };

  if (state.phase === "done") {
    return (
      <div role="status" className={cn("mx-auto max-w-lg text-center", className)}>
        <MailCheck aria-hidden className="mx-auto size-8 text-gold-300" />
        <p className={cn("mt-3 text-lg font-medium", t.label)}>Almost there — check your inbox.</p>
        <p className={cn("mt-1 text-[0.95rem]", t.hint)}>
          {state.message} We'll only add you once you click the confirmation link. If it doesn't
          arrive in a few minutes, check your spam folder.
        </p>
      </div>
    );
  }

  return (
    <form
      noValidate
      onSubmit={submit}
      className={cn("relative mx-auto max-w-lg space-y-4", className)}
      aria-label={`Subscribe to ${status.name ?? "The Positive Reset"}`}
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
          tone={tone}
          label="Email address"
          type="email"
          required
          autoComplete="email"
          maxLength={254}
          value={form.email}
          error={errors.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
      </div>
      <ConsentCheckbox
        tone={tone}
        text={status.consent_text}
        checked={form.consent}
        error={errors.consent}
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
        disabled={state.phase === "sending"}
        className="w-full sm:w-auto"
      >
        {state.phase === "sending" ? "Subscribing…" : "Subscribe"}
      </Button>
      <p className={cn("text-xs", t.hint)}>
        We'll email you to confirm. Every email has a one-click unsubscribe link, and we never sell
        your address.
      </p>
    </form>
  );
}

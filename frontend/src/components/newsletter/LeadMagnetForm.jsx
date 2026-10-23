import { MailCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useShopApi } from "@/components/products/shopApiContext";
import { Button } from "@/components/ui/Button";
import { useSite } from "@/hooks/useContent";
import { cn } from "@/utils/format";
import { ConsentCheckbox, Honeypot, SignupInput } from "./SignupFields";
import { EMAIL_PATTERN, signupErrorMessage, toneClasses } from "./signupUtils";

/**
 * Request a free resource by email. The resource arrives as a secure, expiring link.
 * Subscribing to the newsletter is a separate, unticked choice — unless the resource is
 * explicitly offered in exchange for subscribing, in which case the notice says so.
 */
export function LeadMagnetForm({ leadMagnet, showFirstName = false, tone = "light", className }) {
  const shopApi = useShopApi();
  const { data: site } = useSite();
  const newsletter = site?.newsletter;
  const required = leadMagnet.newsletter_optin === "required";
  const [form, setForm] = useState({ email: "", first_name: "", newsletter: false, website: "" });
  const [errors, setErrors] = useState({});
  const [state, setState] = useState({ phase: "idle", message: "" });
  const started = useRef(0);
  const t = toneClasses(tone);

  useEffect(() => {
    started.current = Date.now();
  }, []);

  if (!leadMagnet.available) return null;
  const canSubscribe = newsletter?.is_open === true;
  if (required && !canSubscribe) return null; // never take an address for an offer we can't honour

  const submit = async (event) => {
    event.preventDefault();
    const next = {};
    if (!EMAIL_PATTERN.test(form.email.trim())) next.email = "Enter a valid email address.";
    if (required && !form.newsletter)
      next.newsletter = "Tick the box to subscribe and get the resource.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setState({ phase: "sending", message: "" });
    try {
      const res = await shopApi.claimLeadMagnet(leadMagnet.slug, {
        email: form.email.trim(),
        first_name: form.first_name.trim(),
        newsletter_consent: form.newsletter,
        consent_version: form.newsletter ? newsletter?.consent_version : undefined,
        website: form.website,
        elapsed_ms: Date.now() - started.current,
      });
      setState({ phase: "done", message: res?.data?.message ?? "" });
    } catch (error) {
      setErrors({
        email: error?.details?.email?.join?.(" "),
        newsletter: error?.details?.newsletter_consent?.join?.(" "),
      });
      setState({ phase: "error", message: signupErrorMessage(error) });
    }
  };

  if (state.phase === "done") {
    return (
      <div role="status" className={cn("max-w-lg", className)}>
        <MailCheck aria-hidden className="size-8 text-sage-700" />
        <p className={cn("mt-3 text-lg font-medium", t.label)}>Check your inbox.</p>
        <p className={cn("mt-1 text-[0.95rem]", t.hint)}>
          We've sent a secure download link for “{leadMagnet.title}”. The link expires after a
          while; you can always request a new one here.
          {form.newsletter && " We've also sent a separate email to confirm your subscription."}
        </p>
      </div>
    );
  }

  return (
    <form
      noValidate
      onSubmit={submit}
      className={cn("relative max-w-lg space-y-4", className)}
      aria-label={`Get ${leadMagnet.title}`}
    >
      <div className={cn("grid gap-3", showFirstName && "sm:grid-cols-2")}>
        {showFirstName && (
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
      {required && leadMagnet.optin_notice && (
        <p className={cn("rounded-xl border border-current/20 p-3 text-sm", t.label)}>
          {leadMagnet.optin_notice}
        </p>
      )}
      {canSubscribe && (
        <ConsentCheckbox
          tone={tone}
          required={required}
          text={newsletter.consent_text}
          checked={form.newsletter}
          error={errors.newsletter}
          onChange={(value) => setForm({ ...form, newsletter: value })}
        />
      )}
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
      >
        {state.phase === "sending" ? "Sending…" : "Email me the free resource"}
      </Button>
      {leadMagnet.product_slug && (
        <p className={cn("text-xs", t.hint)}>
          Have an account?{" "}
          <Link to={`/shop/${leadMagnet.product_slug}`} className="underline underline-offset-4">
            Add it to your library instead
          </Link>
          .
        </p>
      )}
    </form>
  );
}

import { CheckCircle2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { Honeypot, SignupInput } from "@/components/newsletter/SignupFields";
import {
  EMAIL_PATTERN,
  signupErrorMessage,
  toneClasses,
} from "@/components/newsletter/signupUtils";
import { useShopApi } from "@/components/products/shopApiContext";
import { Button } from "@/components/ui/Button";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";
import { BUDGET_RANGES, COLLABORATION_TYPES, PRIVACY_NOTICE } from "./partnershipOptions";

const EMPTY = {
  organization: "",
  contact_name: "",
  email: "",
  website: "",
  collaboration_type: "sponsorship",
  budget_range: "",
  objectives: "",
  message: "",
  privacy_consent: false,
  company_fax: "",
};

function Select({ label, value, onChange, options, tone }) {
  const id = useId();
  const t = toneClasses(tone);
  return (
    <div className="text-left">
      <label htmlFor={id} className={cn("block text-sm font-medium", t.label)}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn("mt-1.5 w-full rounded-full border px-4 py-2.5 text-[0.95rem]", t.input)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function TextArea({ label, error, optional, tone, ...props }) {
  const id = useId();
  const t = toneClasses(tone);
  return (
    <div className="text-left">
      <label htmlFor={id} className={cn("block text-sm font-medium", t.label)}>
        {label}
        {optional && <span className={cn("font-normal", t.hint)}> (optional)</span>}
      </label>
      <textarea
        id={id}
        rows={4}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={cn("mt-1.5 w-full rounded-2xl border px-4 py-2.5 text-[0.95rem]", t.input)}
        {...props}
      />
      {error && (
        <p id={`${id}-error`} className={cn("mt-1 text-sm", t.error)}>
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * The partnership inquiry form. A success message is shown only when the server confirms
 * the inquiry was stored (HTTP 201); nothing is sent to the organisation automatically.
 */
export function PartnershipInquiryForm({ tone = "light", className }) {
  const shopApi = useShopApi();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [state, setState] = useState({ phase: "idle", message: "", reference: "" });
  const started = useRef(0);
  const t = toneClasses(tone);
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  useEffect(() => {
    started.current = Date.now();
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    const next = {};
    if (!form.organization.trim()) next.organization = "Enter your organisation's name.";
    if (!form.contact_name.trim()) next.contact_name = "Enter your name.";
    if (!EMAIL_PATTERN.test(form.email.trim())) next.email = "Enter a valid business email.";
    if (form.website && !/^https:\/\//i.test(form.website.trim()))
      next.website = "Use a full https:// address.";
    if (!form.message.trim()) next.message = "Tell us a little about what you have in mind.";
    if (!form.privacy_consent) next.privacy_consent = "Please confirm you've read the notice.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setState({ phase: "sending", message: "", reference: "" });
    try {
      const res = await shopApi.submitPartnershipInquiry({
        ...form,
        email: form.email.trim(),
        website: form.website.trim(),
        elapsed_ms: Date.now() - started.current,
      });
      const data = res?.data ?? {};
      if (data.status === "received") {
        setState({ phase: "done", message: data.message, reference: data.reference ?? "" });
      } else {
        setState({ phase: "unconfirmed", message: "", reference: "" });
      }
    } catch (error) {
      const details = error?.details ?? {};
      setErrors(
        Object.fromEntries(Object.entries(details).map(([k, v]) => [k, [v].flat().join(" ")])),
      );
      setState({ phase: "error", message: signupErrorMessage(error), reference: "" });
    }
  };

  if (state.phase === "done") {
    return (
      <div role="status" className={cn("rounded-2xl bg-sage-50 p-6 text-left", className)}>
        <CheckCircle2 aria-hidden className="size-7 text-sage-700" />
        <p className="mt-3 text-lg font-medium text-charcoal">{state.message}</p>
        {state.reference && (
          <p className="mt-1 text-sm text-muted">Your reference: {state.reference}</p>
        )}
      </div>
    );
  }

  return (
    <form
      noValidate
      onSubmit={submit}
      aria-label="Partnership inquiry"
      className={cn("relative grid gap-4", className)}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <SignupInput
          tone={tone}
          label="Organisation"
          required
          maxLength={160}
          value={form.organization}
          error={errors.organization}
          onChange={set("organization")}
        />
        <SignupInput
          tone={tone}
          label="Your name"
          required
          maxLength={120}
          autoComplete="name"
          value={form.contact_name}
          error={errors.contact_name}
          onChange={set("contact_name")}
        />
        <SignupInput
          tone={tone}
          label="Business email"
          type="email"
          required
          maxLength={254}
          autoComplete="email"
          value={form.email}
          error={errors.email}
          onChange={set("email")}
        />
        <SignupInput
          tone={tone}
          label="Website"
          optional
          type="url"
          maxLength={300}
          placeholder="https://"
          value={form.website}
          error={errors.website}
          onChange={set("website")}
        />
        <Select
          tone={tone}
          label="Type of collaboration"
          value={form.collaboration_type}
          options={COLLABORATION_TYPES}
          onChange={(v) => setForm({ ...form, collaboration_type: v })}
        />
        <Select
          tone={tone}
          label="Budget range (optional)"
          value={form.budget_range}
          options={BUDGET_RANGES}
          onChange={(v) => setForm({ ...form, budget_range: v })}
        />
      </div>
      <TextArea
        tone={tone}
        label="Campaign objectives"
        optional
        maxLength={2000}
        value={form.objectives}
        onChange={set("objectives")}
      />
      <TextArea
        tone={tone}
        label="Message"
        required
        maxLength={4000}
        value={form.message}
        error={errors.message}
        onChange={set("message")}
      />
      <div className="text-left">
        <p className={cn("text-sm", t.hint)}>
          {PRIVACY_NOTICE}{" "}
          <Link to={routes.privacy} className="underline underline-offset-4">
            Privacy policy
          </Link>
        </p>
        <label className={cn("mt-3 flex items-start gap-3 text-sm", t.label)}>
          <input
            type="checkbox"
            className="mt-0.5 size-4 shrink-0 accent-sage-700"
            checked={form.privacy_consent}
            aria-invalid={errors.privacy_consent ? true : undefined}
            onChange={(e) => setForm({ ...form, privacy_consent: e.target.checked })}
          />
          <span>I have read the privacy notice above.</span>
        </label>
        {errors.privacy_consent && (
          <p className={cn("mt-1 text-sm", t.error)}>{errors.privacy_consent}</p>
        )}
      </div>
      <Honeypot value={form.company_fax} onChange={(v) => setForm({ ...form, company_fax: v })} />
      {state.phase === "error" && (
        <p role="alert" className={cn("text-sm", t.error)}>
          {state.message}
        </p>
      )}
      {state.phase === "unconfirmed" && (
        <p role="alert" className={cn("text-sm", t.error)}>
          We couldn't confirm your inquiry was received. Please try again later or contact us
          another way.
        </p>
      )}
      <div>
        <Button type="submit" disabled={state.phase === "sending"}>
          {state.phase === "sending" ? "Sending…" : "Send inquiry"}
        </Button>
      </div>
    </form>
  );
}

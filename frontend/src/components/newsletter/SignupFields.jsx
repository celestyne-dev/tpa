import { useId } from "react";
import { cn } from "@/utils/format";
import { toneClasses } from "./signupUtils";

/** Accessible text input for the newsletter and free-resource forms. */
export function SignupInput({
  label,
  error,
  tone = "dark",
  optional = false,
  className,
  ...props
}) {
  const id = useId();
  const t = toneClasses(tone);
  return (
    <div className={cn("text-left", className)}>
      <label htmlFor={id} className={cn("block text-sm font-medium", t.label)}>
        {label}
        {optional && <span className={cn("font-normal", t.hint)}> (optional)</span>}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={cn(
          "mt-1.5 w-full rounded-full border px-4 py-2.5 text-[0.95rem] outline-none",
          t.input,
        )}
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

/** Unticked consent checkbox with the exact wording that is recorded. */
export function ConsentCheckbox({ text, checked, onChange, error, tone = "dark", required }) {
  const id = useId();
  const t = toneClasses(tone);
  return (
    <div className="text-left">
      <label htmlFor={id} className={cn("flex items-start gap-3 text-sm", t.label)}>
        <input
          id={id}
          type="checkbox"
          className="mt-0.5 size-4 shrink-0 accent-gold-300"
          checked={checked}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>{text}</span>
      </label>
      {error && (
        <p id={`${id}-error`} className={cn("mt-1 text-sm", t.error)}>
          {error}
        </p>
      )}
    </div>
  );
}

/** Hidden from people (and assistive tech); bots that fill every field reveal themselves. */
export function Honeypot({ value, onChange }) {
  return (
    <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
      <label>
        Website
        <input
          type="text"
          name="website"
          tabIndex={-1}
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    </div>
  );
}

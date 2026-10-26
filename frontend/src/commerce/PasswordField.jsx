import { Check, Eye, EyeOff, X } from "lucide-react";
import { useState } from "react";
import { FieldShell } from "@/components/ui/FormField";
import { cn } from "@/utils/format";
import { passwordChecks } from "./passwordRules";

const controlStyles =
  "w-full rounded-xl border border-charcoal/20 bg-white/80 py-3 pr-14 pl-4 text-base text-charcoal transition-colors focus:border-sage-600 focus:outline-none focus-visible:outline-3 focus-visible:outline-sage-600/40 aria-[invalid=true]:border-red-700";

/** Password input with an accessible show/hide toggle. */
export function PasswordField({ label, hint, error, required, className, ...props }) {
  const [visible, setVisible] = useState(false);
  return (
    <FieldShell label={label} hint={hint} error={error} required={required} className={className}>
      {({ id, describedBy }) => (
        <div className="relative">
          <input
            id={id}
            type={visible ? "text" : "password"}
            required={required}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={controlStyles}
            autoCapitalize="none"
            spellCheck={false}
            {...props}
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            aria-pressed={visible}
            aria-controls={id}
            aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
            className="absolute inset-y-0 right-1 my-1 grid w-11 place-items-center rounded-lg text-muted hover:bg-beige hover:text-charcoal"
          >
            {visible ? (
              <EyeOff aria-hidden className="size-5" />
            ) : (
              <Eye aria-hidden className="size-5" />
            )}
          </button>
        </div>
      )}
    </FieldShell>
  );
}

/** The server's password rules, shown up front and ticked off as people type. */
export function PasswordRequirements({ password, email, id }) {
  return (
    <ul id={id} className="space-y-1 text-sm" aria-label="Password requirements">
      {passwordChecks(password, email).map((rule) => (
        <li
          key={rule.key}
          className={cn("flex items-center gap-2", rule.ok ? "text-sage-800" : "text-muted")}
        >
          {rule.ok ? (
            <Check aria-hidden className="size-4" />
          ) : (
            <X aria-hidden className="size-4" />
          )}
          <span>
            {rule.label}
            <span className="sr-only">{rule.ok ? " (met)" : " (not met yet)"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

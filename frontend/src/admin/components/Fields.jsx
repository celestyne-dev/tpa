import { FieldShell } from "@/components/ui/FormField";
import { cn } from "@/utils/format";

const control =
  "w-full rounded-lg border border-charcoal/20 bg-white px-3 py-2 text-[0.95rem] text-charcoal placeholder:text-muted/70 focus:border-sage-600 focus:outline-none focus-visible:outline-3 focus-visible:outline-sage-600/30 disabled:cursor-not-allowed disabled:bg-beige/50 aria-[invalid=true]:border-red-700";

export function TextField({ label, hint, error, required, className, ...props }) {
  return (
    <FieldShell label={label} hint={hint} error={error} required={required} className={className}>
      {({ id, describedBy }) => (
        <input
          id={id}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={control}
          {...props}
        />
      )}
    </FieldShell>
  );
}

export function TextAreaField({ label, hint, error, required, className, rows = 3, ...props }) {
  return (
    <FieldShell label={label} hint={hint} error={error} required={required} className={className}>
      {({ id, describedBy }) => (
        <textarea
          id={id}
          rows={rows}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(control, "resize-y")}
          {...props}
        />
      )}
    </FieldShell>
  );
}

export function SelectField({ label, hint, error, required, className, options, ...props }) {
  return (
    <FieldShell label={label} hint={hint} error={error} required={required} className={className}>
      {({ id, describedBy }) => (
        <select
          id={id}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={control}
          {...props}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}

export function CheckboxField({ label, hint, className, ...props }) {
  return (
    <label className={cn("flex items-start gap-3 text-sm text-charcoal", className)}>
      <input type="checkbox" className="mt-0.5 size-4 accent-sage-700" {...props} />
      <span>
        <span className="font-medium">{label}</span>
        {hint && <span className="block text-muted">{hint}</span>}
      </span>
    </label>
  );
}

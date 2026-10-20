import { useId, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const controlStyles =
  "w-full rounded-xl border border-charcoal/20 bg-white/80 px-4 py-3 text-base text-charcoal placeholder:text-muted/70 transition-colors focus:border-sage-600 focus:outline-none focus-visible:outline-3 focus-visible:outline-sage-600/40 disabled:cursor-not-allowed disabled:bg-beige/50 aria-[invalid=true]:border-red-700";

interface FieldShellProps {
  label: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  children: (ids: { id: string; describedBy?: string }) => ReactNode;
  className?: string;
}

/** Label + hint + error wrapper that wires up accessible ids for any control. */
export function FieldShell({ label, hint, error, required, children, className }: FieldShellProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-charcoal">
        {label}
        {required && (
          <span aria-hidden className="ml-0.5 text-gold-700">
            *
          </span>
        )}
      </label>
      {children({ id, describedBy })}
      {hint && (
        <p id={hintId} className="text-sm text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-sm text-red-800">
          {error}
        </p>
      )}
    </div>
  );
}

type InputFieldProps = Omit<ComponentPropsWithoutRef<"input">, "id"> &
  Omit<FieldShellProps, "children">;

export function InputField({ label, hint, error, required, className, ...props }: InputFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error} required={required} className={className}>
      {({ id, describedBy }) => (
        <input
          id={id}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={controlStyles}
          {...props}
        />
      )}
    </FieldShell>
  );
}

type TextareaFieldProps = Omit<ComponentPropsWithoutRef<"textarea">, "id"> &
  Omit<FieldShellProps, "children">;

export function TextareaField({
  label,
  hint,
  error,
  required,
  className,
  ...props
}: TextareaFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error} required={required} className={className}>
      {({ id, describedBy }) => (
        <textarea
          id={id}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(controlStyles, "min-h-32 resize-y")}
          {...props}
        />
      )}
    </FieldShell>
  );
}

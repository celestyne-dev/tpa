import { cn } from "@/utils/format";
import { SelectField, TextField } from "../Fields";
import { errorText, fromLocalInput, toLocalInput } from "./draft";

// Visual swatches for the approved background presets.
const SWATCH = {
  ivory: "bg-ivory",
  cream: "bg-cream",
  beige: "bg-beige",
  sage: "bg-sage-50",
  sage_dark: "bg-sage-800",
  charcoal: "bg-charcoal",
};

/** Approved design presets for a section (no free-form CSS). */
export function DesignControls({ type, design, onChange, errors = {}, disabled }) {
  if (!type.design.length) return null;
  return (
    <div className="space-y-4">
      {type.design.map((option) =>
        option.name === "background" ? (
          <fieldset key={option.name}>
            <legend className="text-sm font-medium text-charcoal">{option.label}</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {option.choices.map((c) => (
                <label
                  key={c.value}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-sm has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-sage-600/40",
                    (design.background ?? "") === c.value
                      ? "border-sage-700 bg-sage-50 font-medium text-sage-800"
                      : "border-charcoal/15 bg-white",
                  )}
                >
                  <input
                    type="radio"
                    name={`bg-${type.type}`}
                    value={c.value}
                    checked={(design.background ?? "") === c.value}
                    disabled={disabled}
                    onChange={() => onChange({ ...design, background: c.value })}
                    className="sr-only"
                  />
                  <span
                    aria-hidden
                    className={cn("size-4 rounded-full border border-charcoal/15", SWATCH[c.value])}
                  />
                  {c.label}
                </label>
              ))}
            </div>
            {errorText(errors["design.background"]) && (
              <p role="alert" className="mt-1 text-sm text-red-800">
                {errorText(errors["design.background"])}
              </p>
            )}
          </fieldset>
        ) : (
          <SelectField
            key={option.name}
            label={option.label}
            value={design[option.name] ?? ""}
            disabled={disabled}
            options={option.choices}
            error={errorText(errors[`design.${option.name}`])}
            onChange={(e) => onChange({ ...design, [option.name]: e.target.value })}
          />
        ),
      )}
      {errorText(errors.design) && (
        <p role="alert" className="text-sm text-red-800">
          {errorText(errors.design)}
        </p>
      )}
    </div>
  );
}

export function VisibilityControls({ visibility, onChange, errors = {}, disabled }) {
  const v = visibility ?? {};
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <SelectField
        className="sm:col-span-2"
        label="Show on"
        value={v.devices ?? "all"}
        disabled={disabled}
        options={[
          { value: "all", label: "All devices" },
          { value: "desktop", label: "Desktop and tablet only" },
          { value: "mobile", label: "Mobile only" },
        ]}
        onChange={(e) => onChange({ ...v, devices: e.target.value })}
      />
      <TextField
        type="datetime-local"
        label="Show from (optional)"
        value={toLocalInput(v.starts_at)}
        disabled={disabled}
        error={errorText(errors["visibility.starts_at"])}
        onChange={(e) => onChange({ ...v, starts_at: fromLocalInput(e.target.value) })}
      />
      <TextField
        type="datetime-local"
        label="Hide after (optional)"
        value={toLocalInput(v.ends_at)}
        disabled={disabled}
        error={errorText(errors["visibility.ends_at"])}
        onChange={(e) => onChange({ ...v, ends_at: fromLocalInput(e.target.value) })}
      />
      <p className="text-sm text-muted sm:col-span-2">
        Dates are in your local time. The website is rebuilt automatically when a scheduled section
        starts or ends.
      </p>
    </div>
  );
}

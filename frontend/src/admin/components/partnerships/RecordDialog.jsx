import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../Fields";
import { fieldError } from "../fieldError";
import { Modal } from "../Modal";
import { initialValues, toBody } from "./formValues";

/**
 * A small form dialog driven by field specs, shared by the partnership screens.
 * Field types: text, textarea, select, id (select of records), number, money, date,
 * datetime, checkbox, lines. The server validates everything again.
 */
export function RecordDialog({
  title,
  fields,
  record,
  onSave,
  onClose,
  submitLabel = "Save",
  children,
}) {
  const [values, setValues] = useState(() => initialValues(fields, record));
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const set = (name, value) => setValues((v) => ({ ...v, [name]: value }));
  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await onSave(toBody(fields, values), values);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      open
      size="lg"
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="record-form" disabled={saving}>
            {submitLabel}
          </Button>
        </>
      }
    >
      <form id="record-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => {
          const common = {
            label: f.label,
            hint: f.hint,
            required: f.required,
            disabled: f.readOnly,
            error: fieldError(error, f.name),
            className:
              f.wide || ["textarea", "lines"].includes(f.type) ? "sm:col-span-2" : undefined,
          };
          if (f.type === "textarea" || f.type === "lines")
            return (
              <TextAreaField
                key={f.name}
                {...common}
                rows={f.rows ?? 3}
                value={values[f.name]}
                onChange={(e) => set(f.name, e.target.value)}
              />
            );
          if (f.type === "select" || f.type === "id")
            return (
              <SelectField
                key={f.name}
                {...common}
                value={String(values[f.name] ?? "")}
                options={[...(f.required ? [] : [{ value: "", label: "—" }]), ...f.options]}
                onChange={(e) => set(f.name, e.target.value)}
              />
            );
          if (f.type === "checkbox")
            return (
              <CheckboxField
                key={f.name}
                label={f.label}
                hint={f.hint}
                className={common.className}
                checked={Boolean(values[f.name])}
                disabled={f.readOnly}
                onChange={(e) => set(f.name, e.target.checked)}
              />
            );
          const type =
            { number: "number", date: "date", datetime: "datetime-local", money: "text" }[f.type] ??
            "text";
          return (
            <TextField
              key={f.name}
              {...common}
              type={type}
              inputMode={f.type === "money" ? "decimal" : undefined}
              value={values[f.name]}
              onChange={(e) => set(f.name, e.target.value)}
            />
          );
        })}
        {children?.(values, set)}
        {error && !Object.keys(error.details ?? {}).length && (
          <p role="alert" className="text-sm text-red-800 sm:col-span-2">
            {error.message}
          </p>
        )}
        {error?.details?.conflicts && (
          <p role="alert" className="text-sm text-red-800 sm:col-span-2">
            Conflicts with booking(s) {error.details.conflicts.map((c) => `#${c.id}`).join(", ")}.
          </p>
        )}
      </form>
    </Modal>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div
      role="tablist"
      aria-label="Views"
      className="mb-5 flex flex-wrap gap-1 border-b border-charcoal/10"
    >
      {tabs.map(([key, text]) => (
        <button
          key={key}
          role="tab"
          type="button"
          aria-selected={value === key}
          onClick={() => onChange(key)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
            value === key ? "border-sage-700" : "border-transparent text-muted"
          }`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

import { ArrowDown, ArrowUp, Plus, Trash2, X } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/utils/format";
import { BlockEditor } from "../BlockEditor";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../Fields";
import { ImageChooser } from "../media/ImageChooser";
import { errorText, move } from "./draft";
import { useBuilderLookups } from "./lookups";

const STYLE_OPTIONS = [
  { value: "", label: "Default for this section" },
  { value: "primary", label: "Sage (primary)" },
  { value: "secondary", label: "Charcoal" },
  { value: "outline", label: "Outline" },
  { value: "light", label: "Light" },
];

function visible(spec, variant, content) {
  if (spec.show_for && !spec.show_for.includes(variant)) return false;
  if (spec.show_for_mode && content.mode !== spec.show_for_mode) return false;
  return true;
}

const isRequired = (spec, variant) =>
  Boolean(spec.required) || (spec.required_for ?? []).includes(variant);

/** Internal path or https link, with suggestions from the site's pages, topics and articles. */
export function LinkField({ label, value, onChange, error, required, hint, disabled }) {
  const { links } = useBuilderLookups();
  const listId = useId();
  return (
    <>
      <TextField
        label={label}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder="/articles or https://…"
        list={listId}
        required={required}
        error={error}
        disabled={disabled}
        hint={hint ?? "A site path such as /about, or a full https:// link."}
      />
      <datalist id={listId}>
        {links.map((l) => (
          <option key={`${l.group}-${l.url}`} value={l.url}>
            {`${l.label} (${l.group}${l.note ? `, ${l.note}` : ""})`}
          </option>
        ))}
      </datalist>
    </>
  );
}

function CtaField({ spec, value, onChange, errors, path, disabled }) {
  const { ctas } = useBuilderLookups();
  const cta = value ?? { label: "", url: "", style: "", cta_id: null };
  const saved = Boolean(cta.cta_id);
  const set = (patch) => onChange({ ...cta, ...patch });
  return (
    <fieldset className="rounded-lg border border-charcoal/10 p-3">
      <legend className="px-1 text-sm font-semibold text-charcoal">{spec.label}</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField
          label="Button source"
          value={saved ? "saved" : "custom"}
          disabled={disabled}
          options={[
            { value: "custom", label: "Write a button" },
            { value: "saved", label: "Use a saved call to action" },
          ]}
          onChange={(e) =>
            e.target.value === "saved"
              ? set({ cta_id: ctas[0]?.id ?? null, label: "", url: "" })
              : set({ cta_id: null })
          }
        />
        <SelectField
          label="Button style"
          value={cta.style ?? ""}
          options={STYLE_OPTIONS}
          disabled={disabled}
          onChange={(e) => set({ style: e.target.value })}
          error={errorText(errors[`${path}.style`])}
        />
        {saved ? (
          <SelectField
            label="Saved call to action"
            className="sm:col-span-2"
            value={cta.cta_id ?? ""}
            disabled={disabled}
            options={
              ctas.length
                ? ctas.map((c) => ({ value: c.id, label: `${c.name}: “${c.label}” → ${c.url}` }))
                : [{ value: "", label: "No saved calls to action yet" }]
            }
            onChange={(e) => set({ cta_id: Number(e.target.value) || null })}
            error={errorText(errors[`${path}.cta_id`])}
            hint="Edit its text and link once in Shared sections › Calls to action."
          />
        ) : (
          <>
            <TextField
              label="Button text"
              value={cta.label ?? ""}
              maxLength={60}
              disabled={disabled}
              onChange={(e) => set({ label: e.target.value })}
              error={errorText(errors[`${path}.label`])}
            />
            <LinkField
              label="Button link"
              value={cta.url}
              disabled={disabled}
              onChange={(url) => set({ url })}
              error={errorText(errors[`${path}.url`])}
            />
          </>
        )}
      </div>
      {errorText(errors[path]) && (
        <p role="alert" className="mt-2 text-sm text-red-800">
          {errorText(errors[path])}
        </p>
      )}
    </fieldset>
  );
}

/** Ordered selection from a list (articles, topics); keeps the editor's chosen order. */
function OrderedPicker({ label, items, value, onChange, max, error, hint, disabled, itemLabel }) {
  const chosen = (value ?? []).map((id) => items.find((i) => i.id === id) ?? { id, missing: true });
  const available = items.filter((i) => !(value ?? []).includes(i.id));
  const addId = useId();
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-charcoal">{label}</legend>
      {hint && <p className="text-sm text-muted">{hint}</p>}
      {chosen.length > 0 && (
        <ol className="space-y-1.5">
          {chosen.map((item, index) => (
            <li
              key={item.id}
              className="flex items-center gap-2 rounded-lg border border-charcoal/10 bg-white px-3 py-2 text-sm"
            >
              <span className="flex-1">
                {item.missing ? `Unavailable item #${item.id}` : itemLabel(item)}
              </span>
              <button
                type="button"
                disabled={disabled || index === 0}
                onClick={() => onChange(move(value, index, index - 1))}
                aria-label={`Move ${itemLabel(item)} up`}
                className="rounded p-1 text-muted hover:bg-beige disabled:opacity-40"
              >
                <ArrowUp aria-hidden className="size-4" />
              </button>
              <button
                type="button"
                disabled={disabled || index === chosen.length - 1}
                onClick={() => onChange(move(value, index, index + 1))}
                aria-label={`Move ${itemLabel(item)} down`}
                className="rounded p-1 text-muted hover:bg-beige disabled:opacity-40"
              >
                <ArrowDown aria-hidden className="size-4" />
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(value.filter((id) => id !== item.id))}
                aria-label={`Remove ${itemLabel(item)}`}
                className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-800"
              >
                <X aria-hidden className="size-4" />
              </button>
            </li>
          ))}
        </ol>
      )}
      {(value ?? []).length < max && (
        <div>
          <label htmlFor={addId} className="sr-only">
            Add to {label}
          </label>
          <select
            id={addId}
            disabled={disabled || available.length === 0}
            value=""
            onChange={(e) => e.target.value && onChange([...(value ?? []), Number(e.target.value)])}
            className="w-full rounded-lg border border-charcoal/20 bg-white px-3 py-2 text-sm"
          >
            <option value="">
              {available.length ? `Add to ${label.toLowerCase()}…` : "Nothing else to add"}
            </option>
            {available.map((i) => (
              <option key={i.id} value={i.id}>
                {itemLabel(i)}
              </option>
            ))}
          </select>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {error}
        </p>
      )}
    </fieldset>
  );
}

function ItemsField({ spec, value, onChange, errors, path, variant, disabled }) {
  const items = value ?? [];
  const blank = Object.fromEntries(
    spec.fields.map((f) => [f.name, f.default ?? (f.type === "media" ? null : "")]),
  );
  const setItem = (index, item) => onChange(items.map((it, i) => (i === index ? item : it)));
  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-semibold text-charcoal">{spec.label}</legend>
      {spec.help && <p className="text-sm text-muted">{spec.help}</p>}
      {items.map((item, index) => (
        <div key={index} className="rounded-lg border border-charcoal/10 bg-white p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-sm font-medium text-charcoal">
              {spec.label.replace(/s$/, "")} {index + 1}
            </p>
            <div className="flex gap-1">
              <button
                type="button"
                disabled={disabled || index === 0}
                aria-label={`Move item ${index + 1} up`}
                onClick={() => onChange(move(items, index, index - 1))}
                className="rounded p-1 text-muted hover:bg-beige disabled:opacity-40"
              >
                <ArrowUp aria-hidden className="size-4" />
              </button>
              <button
                type="button"
                disabled={disabled || index === items.length - 1}
                aria-label={`Move item ${index + 1} down`}
                onClick={() => onChange(move(items, index, index + 1))}
                className="rounded p-1 text-muted hover:bg-beige disabled:opacity-40"
              >
                <ArrowDown aria-hidden className="size-4" />
              </button>
              <button
                type="button"
                disabled={disabled}
                aria-label={`Remove item ${index + 1}`}
                onClick={() => onChange(items.filter((_, i) => i !== index))}
                className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-800"
              >
                <Trash2 aria-hidden className="size-4" />
              </button>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {spec.fields.map((sub) => (
              <Field
                key={sub.name}
                spec={sub}
                value={item[sub.name]}
                variant={variant}
                disabled={disabled}
                errors={errors}
                path={`${path}.${index}.${sub.name}`}
                onChange={(v) => setItem(index, { ...item, [sub.name]: v })}
              />
            ))}
          </div>
        </div>
      ))}
      {items.length < (spec.max_items ?? 10) && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => onChange([...items, { ...blank }])}
        >
          <Plus aria-hidden />
          Add {spec.label.replace(/s$/, "").toLowerCase()}
        </Button>
      )}
      {errorText(errors[path]) && (
        <p role="alert" className="text-sm text-red-800">
          {errorText(errors[path])}
        </p>
      )}
    </fieldset>
  );
}

function Field({ spec, value, onChange, errors, path, variant, disabled }) {
  const { options } = useBuilderLookups();
  const error = errorText(errors[path]);
  const required = isRequired(spec, variant);
  const wide = ["textarea", "rich", "items", "cta", "articles", "topics", "string_list"].includes(
    spec.type,
  );
  const className = cn(wide && "sm:col-span-2");
  switch (spec.type) {
    case "text":
      return (
        <TextField
          className={className}
          label={spec.label}
          value={value ?? ""}
          maxLength={spec.max}
          required={required}
          disabled={disabled}
          hint={spec.help}
          error={error}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "textarea":
      return (
        <TextAreaField
          className={className}
          label={spec.label}
          value={value ?? ""}
          maxLength={spec.max}
          rows={spec.max > 600 ? 6 : 3}
          required={required}
          disabled={disabled}
          hint={spec.help ?? `Up to ${spec.max} characters.`}
          error={error}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "link":
      return (
        <div className={className}>
          <LinkField
            label={spec.label}
            value={value}
            onChange={onChange}
            error={error}
            required={required}
            disabled={disabled}
          />
        </div>
      );
    case "cta":
      return (
        <div className={className}>
          <CtaField
            spec={spec}
            value={value}
            onChange={onChange}
            errors={errors}
            path={path}
            disabled={disabled}
          />
        </div>
      );
    case "media":
      return (
        <div className={cn("space-y-1.5", className)}>
          <p className="text-sm font-medium text-charcoal">
            {spec.label}
            {required && <span className="text-red-800"> *</span>}
          </p>
          {spec.help && <p className="text-sm text-muted">{spec.help}</p>}
          <ImageChooser
            mediaId={value}
            label={spec.label.toLowerCase()}
            disabled={disabled}
            onChange={(id) => onChange(id ?? null)}
          />
          {error && (
            <p role="alert" className="text-sm text-red-800">
              {error}
            </p>
          )}
        </div>
      );
    case "select":
      return (
        <SelectField
          className={className}
          label={spec.label}
          value={value ?? spec.default ?? ""}
          options={spec.choices}
          disabled={disabled}
          error={error}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "number":
      return (
        <TextField
          className={className}
          type="number"
          label={spec.label}
          min={spec.min}
          max={spec.max}
          value={value ?? spec.default ?? ""}
          disabled={disabled}
          error={error}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        />
      );
    case "boolean":
      return (
        <CheckboxField
          className={cn("sm:col-span-2", className)}
          label={spec.label}
          hint={spec.help}
          checked={Boolean(value ?? spec.default)}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
      );
    case "articles":
      return (
        <div className={className}>
          <OrderedPicker
            label={spec.label}
            items={options.articles}
            value={value}
            max={spec.max_items ?? 12}
            hint={spec.help}
            error={error}
            disabled={disabled}
            itemLabel={(a) => a.title}
            onChange={onChange}
          />
        </div>
      );
    case "topics":
      return (
        <div className={className}>
          <OrderedPicker
            label={spec.label}
            items={options.topics}
            value={value}
            max={spec.max_items ?? 12}
            hint={spec.help}
            error={error}
            disabled={disabled}
            itemLabel={(t) => t.name}
            onChange={onChange}
          />
        </div>
      );
    case "author":
      return (
        <SelectField
          className={className}
          label={spec.label}
          value={value ?? ""}
          disabled={disabled}
          error={error}
          options={[
            { value: "", label: "Choose an author…" },
            ...options.authors.map((a) => ({ value: a.id, label: a.name })),
          ]}
          onChange={(e) => onChange(Number(e.target.value) || null)}
        />
      );
    case "string_list":
      return (
        <TextAreaField
          className={className}
          label={spec.label}
          rows={4}
          disabled={disabled}
          hint={`One per line (up to ${spec.max_items ?? 10}).`}
          value={(value ?? []).join("\n")}
          error={error}
          onChange={(e) => onChange(e.target.value.split("\n"))}
        />
      );
    case "items":
      return (
        <div className={className}>
          <ItemsField
            spec={spec}
            value={value}
            onChange={onChange}
            errors={errors}
            path={path}
            variant={variant}
            disabled={disabled}
          />
        </div>
      );
    case "rich":
      return (
        <div className={cn("space-y-2", className)}>
          <p className="text-sm font-medium text-charcoal">{spec.label}</p>
          <BlockEditor
            blocks={Array.isArray(value) ? value : []}
            onChange={onChange}
            disabled={disabled}
            errors={
              errors[path] && typeof errors[path] === "object" && !Array.isArray(errors[path])
                ? errors[path]
                : undefined
            }
          />
          {Array.isArray(errors[path]) && (
            <p role="alert" className="text-sm text-red-800">
              {errorText(errors[path])}
            </p>
          )}
        </div>
      );
    default:
      return null;
  }
}

/** Content fields for one section, generated from the server's section-type schema. */
export function SectionFields({ type, section, onChange, errors = {}, disabled = false }) {
  const content = section.content ?? {};
  const setContent = (name, value) =>
    onChange({ ...section, content: { ...content, [name]: value } });
  return (
    <div className="space-y-4">
      {type.variants.length > 1 && (
        <SelectField
          label="Layout"
          value={section.variant}
          options={type.variants}
          disabled={disabled}
          error={errorText(errors.variant)}
          onChange={(e) => onChange({ ...section, variant: e.target.value })}
        />
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {type.fields
          .filter((spec) => visible(spec, section.variant, content))
          .map((spec) => (
            <Field
              key={spec.name}
              spec={spec}
              value={content[spec.name]}
              variant={section.variant}
              errors={Object.fromEntries(
                Object.entries(errors)
                  .filter(([k]) => k.startsWith("content."))
                  .map(([k, v]) => [k.slice("content.".length), v]),
              )}
              path={spec.name}
              disabled={disabled}
              onChange={(value) => setContent(spec.name, value)}
            />
          ))}
      </div>
      {errorText(errors.content) && (
        <p role="alert" className="text-sm text-red-800">
          {errorText(errors.content)}
        </p>
      )}
    </div>
  );
}

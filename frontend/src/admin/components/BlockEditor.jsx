import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { BLOCK_TEMPLATES, blockLabel } from "./blocks";
import { SelectField, TextAreaField, TextField } from "./Fields";

function BlockFields({ block, index, onChange, errors }) {
  const n = index + 1;
  const set = (patch) => onChange({ ...block, ...patch });
  const error = errors?.join(" ");
  switch (block.type) {
    case "paragraph":
      return (
        <TextAreaField
          label={`Paragraph ${n} text`}
          rows={4}
          value={block.text}
          error={error}
          onChange={(e) => set({ text: e.target.value })}
        />
      );
    case "heading":
      return (
        <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
          <TextField
            label={`Heading ${n} text`}
            value={block.text}
            error={error}
            onChange={(e) => set({ text: e.target.value })}
          />
          <SelectField
            label="Level"
            value={String(block.level ?? 2)}
            options={[
              { value: "2", label: "Section (H2)" },
              { value: "3", label: "Subsection (H3)" },
            ]}
            onChange={(e) => set({ level: Number(e.target.value) })}
          />
        </div>
      );
    case "list":
      return (
        <TextAreaField
          label={`List ${n} items`}
          hint="One item per line."
          rows={4}
          error={error}
          value={block.items.join("\n")}
          onChange={(e) => set({ items: e.target.value.split("\n") })}
        />
      );
    case "quote":
      return (
        <div className="grid gap-3">
          <TextAreaField
            label={`Quote ${n} text`}
            value={block.text}
            error={error}
            onChange={(e) => set({ text: e.target.value })}
          />
          <TextField
            label="Attribution (optional)"
            value={block.cite ?? ""}
            onChange={(e) => set({ cite: e.target.value })}
          />
        </div>
      );
    case "callout":
      return (
        <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
          <TextField
            label={`Callout ${n} title (optional)`}
            value={block.title ?? ""}
            onChange={(e) => set({ title: e.target.value })}
          />
          <SelectField
            label="Style"
            value={block.tone ?? "info"}
            options={[
              { value: "info", label: "Info" },
              { value: "tip", label: "Tip" },
              { value: "warning", label: "Warning" },
            ]}
            onChange={(e) => set({ tone: e.target.value })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Callout text"
            value={block.text}
            error={error}
            onChange={(e) => set({ text: e.target.value })}
          />
        </div>
      );
    case "divider":
      return (
        <hr className="my-2 border-t-2 border-dashed border-gold-300" aria-label={`Divider ${n}`} />
      );
    default:
      return <p className="text-sm text-red-800">Unsupported block type.</p>;
  }
}

/** Structured content editor (plain-text blocks; no HTML). */
export function BlockEditor({ blocks, onChange, errors, disabled = false }) {
  const update = (index, block) => onChange(blocks.map((b, i) => (i === index ? block : b)));
  const move = (index, delta) => {
    const next = [...blocks];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    onChange(next);
  };
  const remove = (index) => onChange(blocks.filter((_, i) => i !== index));
  const add = (key) => onChange([...blocks, BLOCK_TEMPLATES[key].make()]);

  return (
    <fieldset disabled={disabled} className="space-y-3">
      <legend className="mb-2 text-sm font-semibold text-charcoal">Content</legend>
      {blocks.length === 0 && (
        <p className="rounded-xl border border-dashed border-charcoal/20 bg-cream/50 p-6 text-center text-sm text-muted">
          No content yet. Add a paragraph or heading to begin.
        </p>
      )}
      <ol className="space-y-3">
        {blocks.map((block, index) => (
          <li key={index} className="rounded-xl border border-charcoal/10 bg-white p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold tracking-wide text-sage-700 uppercase">
                {index + 1}. {blockLabel(block)}
              </span>
              <span className="flex gap-1">
                <IconButton
                  label={`Move block ${index + 1} up`}
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                  icon={ArrowUp}
                />
                <IconButton
                  label={`Move block ${index + 1} down`}
                  disabled={index === blocks.length - 1}
                  onClick={() => move(index, 1)}
                  icon={ArrowDown}
                />
                <IconButton
                  label={`Remove block ${index + 1}`}
                  onClick={() => remove(index)}
                  icon={Trash2}
                  danger
                />
              </span>
            </div>
            <BlockFields
              block={block}
              index={index}
              onChange={(b) => update(index, b)}
              errors={errors?.[String(index)]}
            />
          </li>
        ))}
      </ol>
      <div
        className="flex flex-wrap items-center gap-2 rounded-xl bg-cream/60 p-3"
        role="group"
        aria-label="Add a block"
      >
        <span className="text-sm text-muted">Add:</span>
        {Object.entries(BLOCK_TEMPLATES).map(([key, t]) => (
          <button
            key={key}
            type="button"
            onClick={() => add(key)}
            className="inline-flex items-center gap-1 rounded-full border border-charcoal/15 bg-white px-3 py-1 text-sm hover:border-sage-600 hover:text-sage-800"
          >
            <Plus aria-hidden className="size-3.5" />
            {t.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function IconButton({ label, icon: Icon, danger, ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={
        danger
          ? "rounded p-1.5 text-muted hover:bg-red-50 hover:text-red-800 disabled:opacity-40"
          : "rounded p-1.5 text-muted hover:bg-beige hover:text-charcoal disabled:opacity-40"
      }
      {...props}
    >
      <Icon aria-hidden className="size-4" />
    </button>
  );
}

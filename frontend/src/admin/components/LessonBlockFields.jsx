import { Plus, Trash2 } from "lucide-react";
import { CheckboxField, SelectField, TextAreaField, TextField } from "./Fields";

const LINK_HINT = "A site path such as /articles/rest, or a full https:// address.";

function Lines({ label, items, onChange, error, hint }) {
  return (
    <TextAreaField
      label={label}
      hint={hint ?? "One item per line."}
      rows={4}
      value={(items ?? []).join("\n")}
      error={error}
      onChange={(e) => onChange(e.target.value.split("\n"))}
    />
  );
}

function ChecklistItems({ n, items, onChange, error }) {
  const list = (items ?? []).map((i) => (typeof i === "string" ? { text: i } : i));
  const update = (index, patch) =>
    onChange(list.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">Checklist {n} items</legend>
      {list.map((item, i) => (
        <div key={item.id ?? `new-${i}`} className="flex items-end gap-2">
          <TextField
            className="flex-1"
            label={`Item ${i + 1}`}
            value={item.text ?? ""}
            onChange={(e) => update(i, { text: e.target.value })}
          />
          <button
            type="button"
            aria-label={`Remove item ${i + 1}`}
            disabled={list.length === 1}
            onClick={() => onChange(list.filter((_, j) => j !== i))}
            className="mb-1 rounded p-2 text-muted hover:bg-beige disabled:opacity-40"
          >
            <Trash2 aria-hidden className="size-4" />
          </button>
        </div>
      ))}
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={() => onChange([...list, { text: "" }])}
        className="inline-flex items-center gap-1 text-sm font-medium text-sage-800 underline underline-offset-4"
      >
        <Plus aria-hidden className="size-4" /> Add item
      </button>
    </fieldset>
  );
}

/** Field editors for the lesson-only blocks (key points, examples, exercises, …). */
export function LessonBlockFields({ block, n, set, error, files }) {
  switch (block.type) {
    case "key_points":
      return (
        <div className="space-y-3">
          <TextField
            label={`Key points ${n} title (optional)`}
            value={block.title ?? ""}
            onChange={(e) => set({ title: e.target.value })}
          />
          <Lines
            label="Key points"
            items={block.items}
            error={error}
            onChange={(items) => set({ items })}
          />
        </div>
      );
    case "example":
      return (
        <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
          <TextField
            label={`Example ${n} title`}
            value={block.title ?? ""}
            error={error}
            onChange={(e) => set({ title: e.target.value })}
          />
          <SelectField
            label="Kind"
            value={block.variant ?? "example"}
            options={[
              { value: "example", label: "Example" },
              { value: "case_study", label: "Case study" },
            ]}
            onChange={(e) => set({ variant: e.target.value })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Text"
            rows={5}
            value={block.text ?? ""}
            onChange={(e) => set({ text: e.target.value })}
          />
        </div>
      );
    case "exercise":
      return (
        <div className="space-y-3">
          <TextField
            label={`Exercise ${n} title (optional)`}
            value={block.title ?? ""}
            onChange={(e) => set({ title: e.target.value })}
          />
          <TextAreaField
            label="Prompt or reflection question"
            rows={3}
            value={block.prompt ?? ""}
            error={error}
            onChange={(e) => set({ prompt: e.target.value })}
          />
          <div className="flex flex-wrap gap-6">
            <CheckboxField
              label="Required to complete the lesson"
              checked={Boolean(block.required)}
              onChange={(e) => set({ required: e.target.checked })}
            />
            <CheckboxField
              label="Learners can write a private answer"
              checked={block.allow_response !== false}
              onChange={(e) => set({ allow_response: e.target.checked })}
            />
          </div>
          <p className="text-xs text-muted">
            Answers are private notes for the learner; they are never marked right or wrong.
          </p>
        </div>
      );
    case "checklist":
      return (
        <div className="space-y-3">
          <TextField
            label={`Checklist ${n} title (optional)`}
            value={block.title ?? ""}
            onChange={(e) => set({ title: e.target.value })}
          />
          <ChecklistItems
            n={n}
            items={block.items}
            error={error}
            onChange={(items) => set({ items })}
          />
          <CheckboxField
            label="Required: learners must tick every item to complete the lesson"
            checked={Boolean(block.required)}
            onChange={(e) => set({ required: e.target.checked })}
          />
        </div>
      );
    case "download":
      return (
        <div className="grid gap-3 sm:grid-cols-2">
          {files?.length ? (
            <SelectField
              label={`Worksheet ${n}`}
              value={block.file_id ?? ""}
              error={error}
              options={[
                { value: "", label: "Choose a file…" },
                ...files.map((f) => ({
                  value: f.id,
                  label: `${f.title}${f.format ? ` (${f.format})` : ""}${f.status !== "active" ? " — inactive" : ""}`,
                })),
              ]}
              onChange={(e) => set({ file_id: e.target.value })}
            />
          ) : (
            <p role="alert" className="text-sm text-red-800 sm:col-span-2">
              {error ||
                "Link this course to a course product and upload worksheets to it (Commerce → Products) to offer downloads."}
            </p>
          )}
          <TextField
            label="Title shown to learners (optional)"
            value={block.title ?? ""}
            onChange={(e) => set({ title: e.target.value })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Description (optional)"
            value={block.description ?? ""}
            onChange={(e) => set({ description: e.target.value })}
          />
          <p className="text-xs text-muted sm:col-span-2">
            Files stay in private storage and are delivered through short-lived download links to
            learners with access.
          </p>
        </div>
      );
    case "further_reading": {
      const items = block.items ?? [];
      const update = (i, patch) =>
        set({ items: items.map((item, j) => (j === i ? { ...item, ...patch } : item)) });
      return (
        <div className="space-y-3">
          <TextField
            label={`Further reading ${n} title (optional)`}
            value={block.title ?? ""}
            onChange={(e) => set({ title: e.target.value })}
          />
          {items.map((item, i) => (
            <div key={i} className="grid gap-2 rounded-lg bg-cream/50 p-3 sm:grid-cols-3">
              <TextField
                label={`Link ${i + 1} label`}
                value={item.label ?? ""}
                onChange={(e) => update(i, { label: e.target.value })}
              />
              <TextField
                label="Address"
                hint={LINK_HINT}
                value={item.href ?? ""}
                onChange={(e) => update(i, { href: e.target.value })}
              />
              <div className="flex items-end gap-2">
                <TextField
                  className="flex-1"
                  label="Note (optional)"
                  value={item.note ?? ""}
                  onChange={(e) => update(i, { note: e.target.value })}
                />
                <button
                  type="button"
                  aria-label={`Remove link ${i + 1}`}
                  onClick={() => set({ items: items.filter((_, j) => j !== i) })}
                  className="mb-1 rounded p-2 text-muted hover:bg-red-50 hover:text-red-800"
                >
                  <Trash2 aria-hidden className="size-4" />
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() => set({ items: [...items, { label: "", href: "", note: "" }] })}
            className="inline-flex items-center gap-1 text-sm text-sage-800 underline underline-offset-4"
          >
            <Plus aria-hidden className="size-3.5" /> Add a link
          </button>
          {error && (
            <p role="alert" className="text-sm text-red-800">
              {error}
            </p>
          )}
        </div>
      );
    }
    default:
      return null;
  }
}

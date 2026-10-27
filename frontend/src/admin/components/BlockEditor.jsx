import { ArrowDown, ArrowUp, Copy, ImagePlus, Plus, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../adminApiContext";
import { BLOCK_TEMPLATES, LESSON_BLOCK_TYPES, blockLabel, videoUrl } from "./blocks";
import { CheckboxField, SelectField, TextAreaField, TextField } from "./Fields";
import { LessonBlockFields } from "./LessonBlockFields";
import { ImageChooser, MediaThumb } from "./media/ImageChooser";
import { rememberMedia } from "./media/mediaCache";
import { MediaPicker } from "./media/MediaPicker";

function GalleryEditor({ block, set, n }) {
  const [open, setOpen] = useState(false);
  const items = block.items ?? [];
  return (
    <div className="space-y-3">
      <ul aria-label={`Gallery ${n} images`} className="flex flex-wrap gap-3">
        {items.map((item, i) => (
          <li key={`${item.media_id}-${i}`} className="relative">
            <MediaThumb id={item.media_id} />
            <button
              type="button"
              aria-label={`Remove image ${i + 1} from gallery`}
              onClick={() => set({ items: items.filter((_, j) => j !== i) })}
              className="absolute -top-2 -right-2 grid size-6 place-items-center rounded-full bg-charcoal text-ivory"
            >
              <X aria-hidden className="size-3.5" />
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-end gap-3">
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
          <ImagePlus aria-hidden />
          Add images
        </Button>
        <SelectField
          label="Columns"
          value={String(block.columns ?? 3)}
          options={["2", "3", "4"].map((v) => ({ value: v, label: v }))}
          onChange={(e) => set({ columns: Number(e.target.value) })}
        />
      </div>
      <TextField
        label="Gallery caption (optional)"
        value={block.caption ?? ""}
        onChange={(e) => set({ caption: e.target.value })}
      />
      <MediaPicker
        open={open}
        multiple
        title="Add images to the gallery"
        onClose={() => setOpen(false)}
        onSelect={(assets) => {
          assets.forEach(rememberMedia);
          set({ items: [...items, ...assets.map((a) => ({ media_id: a.id }))].slice(0, 12) });
        }}
      />
      <p className="text-xs text-muted">Between 2 and 12 images.</p>
    </div>
  );
}

function RelatedEditor({ block, set }) {
  const api = useAdminApi();
  const [articles, setArticles] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api.articles
      .list({ status: "published", page_size: 100 })
      .then((res) => !cancelled && setArticles(res.data))
      .catch(() => !cancelled && setArticles([]));
    return () => {
      cancelled = true;
    };
  }, [api]);
  const ids = block.article_ids ?? [];
  const byId = Object.fromEntries((articles ?? []).map((a) => [a.id, a]));
  return (
    <div className="space-y-3">
      <TextField
        label="Heading (optional)"
        placeholder="Related reading"
        value={block.title ?? ""}
        onChange={(e) => set({ title: e.target.value })}
      />
      <ol className="space-y-1 text-sm">
        {ids.map((id) => (
          <li
            key={id}
            className="flex items-center justify-between gap-2 rounded bg-cream px-2 py-1"
          >
            <span>{byId[id]?.title ?? `Article #${id}`}</span>
            <button
              type="button"
              className="text-muted hover:text-red-800"
              aria-label={`Remove ${byId[id]?.title ?? id}`}
              onClick={() => set({ article_ids: ids.filter((x) => x !== id) })}
            >
              <X aria-hidden className="size-4" />
            </button>
          </li>
        ))}
      </ol>
      {ids.length < 4 && (
        <SelectField
          label="Add a published article"
          value=""
          options={[
            { value: "", label: articles ? "— Choose —" : "Loading…" },
            ...(articles ?? [])
              .filter((a) => !ids.includes(a.id))
              .map((a) => ({ value: String(a.id), label: a.title })),
          ]}
          onChange={(e) => e.target.value && set({ article_ids: [...ids, Number(e.target.value)] })}
        />
      )}
    </div>
  );
}

function TableEditor({ block, set, n }) {
  const rows = block.rows ?? [[""]];
  const width = rows[0]?.length ?? 1;
  const setCell = (r, c, value) =>
    set({ rows: rows.map((row, i) => (i === r ? row.map((v, j) => (j === c ? value : v)) : row)) });
  return (
    <div className="space-y-3">
      <TextField
        label="Caption (optional)"
        value={block.caption ?? ""}
        onChange={(e) => set({ caption: e.target.value })}
      />
      <CheckboxField
        label="First row is a header"
        checked={block.header_row ?? true}
        onChange={(e) => set({ header_row: e.target.checked })}
      />
      <div className="overflow-x-auto">
        <table className="text-sm">
          <tbody>
            {rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, c) => (
                  <td key={c} className="p-0.5">
                    <input
                      aria-label={`Table ${n} row ${r + 1} column ${c + 1}`}
                      value={cell}
                      onChange={(e) => setCell(r, c, e.target.value)}
                      className={`w-32 rounded border border-charcoal/15 px-2 py-1 ${r === 0 && block.header_row ? "font-semibold" : ""}`}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={rows.length >= 30}
          onClick={() => set({ rows: [...rows, Array(width).fill("")] })}
        >
          Add row
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={width >= 6}
          onClick={() => set({ rows: rows.map((row) => [...row, ""]) })}
        >
          Add column
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={rows.length <= 1}
          onClick={() => set({ rows: rows.slice(0, -1) })}
        >
          Remove last row
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={width <= 1}
          onClick={() => set({ rows: rows.map((row) => row.slice(0, -1)) })}
        >
          Remove last column
        </Button>
      </div>
    </div>
  );
}

const LINK_HINT = "A site path such as /topics/confidence, or a full https:// address.";

function BlockFields({ block, index, onChange, errors, files }) {
  const n = index + 1;
  const set = (patch) => onChange({ ...block, ...patch });
  const error = errors?.join(" ");
  if (LESSON_BLOCK_TYPES.has(block.type))
    return <LessonBlockFields block={block} n={n} set={set} error={error} files={files} />;
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
    case "pullquote":
      return (
        <div className="grid gap-3">
          <TextAreaField
            label={`${block.type === "pullquote" ? "Pull quote" : "Quote"} ${n} text`}
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
              { value: "success", label: "Success" },
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
    case "image":
      return (
        <div className="grid gap-3">
          <ImageChooser
            label="image"
            mediaId={block.media_id}
            allowClear={false}
            onChange={(id) => set({ media_id: id })}
          />
          <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
            <TextField
              label="Caption (optional)"
              value={block.caption ?? ""}
              onChange={(e) => set({ caption: e.target.value })}
            />
            <SelectField
              label="Alignment"
              value={block.align ?? "center"}
              options={[
                { value: "center", label: "Text width" },
                { value: "wide", label: "Wide" },
                { value: "full", label: "Full width" },
                { value: "left", label: "Float left" },
                { value: "right", label: "Float right" },
              ]}
              onChange={(e) => set({ align: e.target.value })}
            />
          </div>
          <TextField
            label="Alt text for this placement (optional)"
            hint="Leave empty to use the image's alt text from the media library."
            value={block.alt ?? ""}
            onChange={(e) => set({ alt: e.target.value })}
          />
          {error && (
            <p role="alert" className="text-sm text-red-800">
              {error}
            </p>
          )}
        </div>
      );
    case "gallery":
      return (
        <>
          <GalleryEditor block={block} set={set} n={n} />
          {error && (
            <p role="alert" className="text-sm text-red-800">
              {error}
            </p>
          )}
        </>
      );
    case "video":
      return (
        <div className="grid gap-3">
          <TextField
            label={`Video ${n} link`}
            hint="YouTube or Vimeo only. The video loads only when a reader presses play."
            placeholder="https://www.youtube.com/watch?v=…"
            value={videoUrl(block)}
            error={error}
            onChange={(e) =>
              onChange({ ...block, url: e.target.value, provider: undefined, video_id: undefined })
            }
          />
          <TextField
            label="Video title"
            hint="Describes the video for screen readers and the play button."
            value={block.title ?? ""}
            onChange={(e) => set({ title: e.target.value })}
          />
          <TextField
            label="Caption (optional)"
            value={block.caption ?? ""}
            onChange={(e) => set({ caption: e.target.value })}
          />
        </div>
      );
    case "button":
      return (
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label={`Button ${n} label`}
            value={block.label ?? ""}
            error={error}
            onChange={(e) => set({ label: e.target.value })}
          />
          <TextField
            label="Link"
            hint={LINK_HINT}
            value={block.href ?? ""}
            onChange={(e) => set({ href: e.target.value })}
          />
          <SelectField
            label="Style"
            value={block.style ?? "primary"}
            options={[
              { value: "primary", label: "Primary" },
              { value: "secondary", label: "Secondary" },
            ]}
            onChange={(e) => set({ style: e.target.value })}
          />
          <SelectField
            label="Alignment"
            value={block.align ?? "left"}
            options={[
              { value: "left", label: "Left" },
              { value: "center", label: "Centre" },
            ]}
            onChange={(e) => set({ align: e.target.value })}
          />
        </div>
      );
    case "cta":
      return (
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            className="sm:col-span-2"
            label={`Call to action ${n} heading`}
            value={block.title ?? ""}
            error={error}
            onChange={(e) => set({ title: e.target.value })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Text (optional)"
            value={block.text ?? ""}
            onChange={(e) => set({ text: e.target.value })}
          />
          <TextField
            label="Button label"
            value={block.button_label ?? ""}
            onChange={(e) => set({ button_label: e.target.value })}
          />
          <TextField
            label="Button link"
            hint={LINK_HINT}
            value={block.button_href ?? ""}
            onChange={(e) => set({ button_href: e.target.value })}
          />
        </div>
      );
    case "related":
      return (
        <>
          <RelatedEditor block={block} set={set} />
          {error && (
            <p role="alert" className="text-sm text-red-800">
              {error}
            </p>
          )}
        </>
      );
    case "resource":
      return (
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label={`Resource ${n} title`}
            value={block.title ?? ""}
            error={error}
            onChange={(e) => set({ title: e.target.value })}
          />
          <TextField
            label="Link"
            hint={LINK_HINT}
            value={block.href ?? ""}
            onChange={(e) => set({ href: e.target.value })}
          />
          <TextAreaField
            className="sm:col-span-2"
            label="Description (optional)"
            value={block.description ?? ""}
            onChange={(e) => set({ description: e.target.value })}
          />
          <TextField
            label="Link text (optional)"
            placeholder="Learn more"
            value={block.label ?? ""}
            onChange={(e) => set({ label: e.target.value })}
          />
          <div className="sm:col-span-2">
            <ImageChooser
              label="image (optional)"
              mediaId={block.media_id}
              onChange={(id) => set({ media_id: id })}
            />
          </div>
          <p className="text-xs text-muted sm:col-span-2">
            Product recommendations will connect to the shop when it launches; for now link to
            existing pages or free resources.
          </p>
        </div>
      );
    case "table":
      return (
        <>
          <TableEditor block={block} set={set} n={n} />
          {error && (
            <p role="alert" className="text-sm text-red-800">
              {error}
            </p>
          )}
        </>
      );
    default:
      return <p className="text-sm text-red-800">Unsupported block type.</p>;
  }
}

/** Structured content editor (validated data blocks; no HTML). */
export function BlockEditor({
  blocks,
  onChange,
  errors,
  disabled = false,
  allowed,
  legend = "Content",
  files,
}) {
  const update = (index, block) => onChange(blocks.map((b, i) => (i === index ? block : b)));
  const move = (index, delta) => {
    const next = [...blocks];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    onChange(next);
  };
  const duplicate = (index) => {
    const next = [...blocks];
    next.splice(index + 1, 0, structuredClone(blocks[index]));
    onChange(next);
  };
  const remove = (index) => onChange(blocks.filter((_, i) => i !== index));
  const add = (key) => onChange([...blocks, BLOCK_TEMPLATES[key].make()]);
  // ``allowed`` limits the "Add" choices (e.g. email-safe blocks for newsletters).
  const templates = Object.entries(BLOCK_TEMPLATES).filter(([key, t]) =>
    allowed ? allowed.includes(key) : !t.lessonOnly,
  );

  return (
    <fieldset disabled={disabled} className="space-y-3">
      <legend className="mb-2 text-sm font-semibold text-charcoal">{legend}</legend>
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
                  label={`Duplicate block ${index + 1}`}
                  onClick={() => duplicate(index)}
                  icon={Copy}
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
              files={files}
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
        {templates.map(([key, t]) => (
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

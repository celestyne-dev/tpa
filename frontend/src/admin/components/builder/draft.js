/** Client-side page draft helpers (the server validates everything again). */

let counter = 0;
export const clientId = () => `new-${Date.now().toString(36)}-${(counter += 1)}`;

const SECTION_KEYS = [
  "id",
  "key",
  "name",
  "section_type",
  "variant",
  "content",
  "design",
  "visibility",
  "is_visible",
  "reusable_section_id",
];
export const META_KEYS = [
  "title",
  "slug",
  "parent_id",
  "seo_title",
  "meta_description",
  "noindex",
  "canonical_url",
  "social_title",
  "social_description",
  "social_image_id",
];

const clone = (value) => JSON.parse(JSON.stringify(value ?? null));

export function toDraft(detail) {
  return {
    meta: Object.fromEntries(
      META_KEYS.map((k) => [k, detail[k] ?? (k === "noindex" ? false : null)]),
    ),
    sections: detail.sections.map((s) => ({ ...clone(s), cid: `s-${s.id}` })),
  };
}

export function toPayload(draft) {
  return {
    page: { ...draft.meta },
    sections: draft.sections.map((s) => {
      const out = Object.fromEntries(SECTION_KEYS.map((k) => [k, s[k] ?? null]));
      if (!out.id) delete out.id;
      if (s.reusable_section_id) {
        // Linked sections only carry their link, name, visibility and on/off state.
        return {
          ...(out.id && { id: out.id }),
          key: out.key,
          name: out.name,
          reusable_section_id: s.reusable_section_id,
          visibility: out.visibility ?? {},
          is_visible: out.is_visible ?? true,
        };
      }
      return out;
    }),
  };
}

export const sameDraft = (a, b) => JSON.stringify(toPayload(a)) === JSON.stringify(toPayload(b));

export function newSection(type, overrides = {}) {
  const defaults = clone(type.defaults);
  return {
    cid: clientId(),
    key: null,
    name: overrides.name ?? type.label,
    section_type: type.type,
    type_label: type.label,
    variant: defaults.variant,
    content: defaults.content,
    design: defaults.design,
    visibility: { devices: "all", starts_at: null, ends_at: null },
    is_visible: true,
    reusable_section_id: null,
    ...overrides,
  };
}

export function linkedSection(shared) {
  return {
    cid: clientId(),
    key: null,
    name: shared.name,
    section_type: shared.section_type,
    type_label: shared.type_label,
    variant: shared.variant,
    content: clone(shared.content),
    design: clone(shared.design),
    visibility: { devices: "all", starts_at: null, ends_at: null },
    is_visible: true,
    reusable_section_id: shared.id,
    reusable_name: shared.name,
  };
}

export function duplicateSection(section) {
  return {
    ...clone(section),
    cid: clientId(),
    id: undefined,
    key: null,
    name: `${section.name || section.type_label} (copy)`,
  };
}

export function move(list, from, to) {
  if (to < 0 || to >= list.length || from === to) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** Server error details for one section (prefix "sections.N." removed). */
export function sectionErrors(details, index) {
  const prefix = `sections.${index}.`;
  const out = {};
  for (const [key, value] of Object.entries(details ?? {})) {
    if (key.startsWith(prefix)) out[key.slice(prefix.length)] = value;
  }
  return out;
}

export const errorText = (value) =>
  Array.isArray(value) ? value.flat().join(" ") : typeof value === "string" ? value : undefined;

/** ISO (with zone) <-> <input type="datetime-local"> in the editor's local time. */
export function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
export const fromLocalInput = (value) => (value ? new Date(value).toISOString() : null);

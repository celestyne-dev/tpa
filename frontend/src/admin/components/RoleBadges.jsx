const tones = {
  super_admin: "bg-charcoal text-ivory",
  editor: "bg-sage-100 text-sage-800",
  moderator: "bg-gold-100 text-gold-700",
  analyst: "bg-beige text-ink",
};

const humanise = (name) => name.replaceAll("_", " ");

/** Role chips; `labels` maps role keys to display names when available. */
export function RoleBadges({ roles, labels = {} }) {
  if (!roles?.length) return <span className="text-muted">No roles</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {roles.map((r) => (
        <span
          key={r}
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${labels[r] ? "" : "capitalize"} ${tones[r] ?? "bg-beige text-ink"}`}
        >
          {labels[r] ?? humanise(r)}
        </span>
      ))}
    </span>
  );
}

const KIND_LABELS = { system: "Built-in", template: "Template", custom: "Custom" };
const KIND_TONES = {
  system: "bg-charcoal/10 text-charcoal",
  template: "bg-sage-100 text-sage-800",
  custom: "bg-gold-100 text-gold-700",
};

export function RoleKindBadge({ kind }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${KIND_TONES[kind] ?? "bg-beige text-ink"}`}
    >
      {KIND_LABELS[kind] ?? kind}
    </span>
  );
}

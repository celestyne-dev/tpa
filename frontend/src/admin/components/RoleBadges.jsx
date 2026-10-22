const tones = {
  super_admin: "bg-charcoal text-ivory",
  editor: "bg-sage-100 text-sage-800",
  moderator: "bg-gold-100 text-gold-700",
  analyst: "bg-beige text-ink",
};

export function RoleBadges({ roles }) {
  if (!roles?.length) return <span className="text-muted">No roles</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {roles.map((r) => (
        <span
          key={r}
          className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${tones[r] ?? "bg-beige text-ink"}`}
        >
          {r.replace("_", " ")}
        </span>
      ))}
    </span>
  );
}

/** Shared building blocks for the Analytics pages (Website and Commerce). */
export function Stat({ label, value, hint }) {
  return (
    <div className="rounded-xl border border-charcoal/10 bg-white p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function RankTable({ caption, rows, columns, empty = "Nothing recorded in this period." }) {
  return (
    <section aria-label={caption} className="rounded-xl border border-charcoal/10 bg-white p-4">
      <h2 className="text-base font-semibold">{caption}</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{empty}</p>
      ) : (
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="text-muted">
            <tr>
              {columns.map((c) => (
                <th key={c.header} scope="col" className={c.numeric ? "text-right" : undefined}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-charcoal/10">
                {columns.map((c) => (
                  <td key={c.header} className={c.numeric ? "py-1 text-right" : "py-1 pr-2"}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

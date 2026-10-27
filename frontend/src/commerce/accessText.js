/** "Lifetime access · 5 downloads" — a resource's access rules in plain words. */
export function accessText(access) {
  const period = access.lifetime ? "Lifetime access" : `${access.days}-day access`;
  return access.download_limit
    ? `${period} · ${access.download_limit} download${access.download_limit === 1 ? "" : "s"}`
    : `${period} · unlimited downloads`;
}

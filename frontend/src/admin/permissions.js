/**
 * Permission groups mirrored from the Flask API (backend/app/api/admin). They
 * only decide what the interface shows; the API authorises every request.
 */
export const ARTICLE_ACCESS = [
  "articles.view",
  "articles.create",
  "articles.edit_own",
  "articles.edit_any",
];
export const TAXONOMY_READ = [...ARTICLE_ACCESS, "topics.manage", "tags.manage", "authors.manage"];
export const SETTINGS_ACCESS = ["settings.manage", "seo.manage"];
export const ROLE_READ = ["roles.manage", "roles.assign", "users.view"];
export const SEO_READ = ["seo.view", "seo.manage"];
export const REDIRECT_READ = ["redirects.manage", "seo.view"];

/** Permissions granted by the chosen roles (inactive roles grant nothing); null = all. */
export function previewPermissions(roles, chosen) {
  const picked = roles.filter((r) => chosen.includes(r.name) && r.is_active !== false);
  if (picked.some((r) => r.grants_all)) return null;
  return [...new Set(picked.flatMap((r) => r.permissions))].sort();
}

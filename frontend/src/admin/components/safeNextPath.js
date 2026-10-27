/** Only internal admin paths are accepted as post-login destinations. */
export function safeNextPath(value) {
  if (typeof value !== "string" || value.length > 500) return "/admin";
  const unsafeChar = [...value].some((c) => c === "\\" || c.charCodeAt(0) < 33);
  if (value.startsWith("//") || unsafeChar) return "/admin";
  const path = value.split(/[?#]/)[0];
  // "/administrator" or "/admin-x" are not admin pages; "/admin/login" would loop.
  if (path !== "/admin" && !path.startsWith("/admin/")) return "/admin";
  return path === "/admin/login" || path.startsWith("/admin/login/") ? "/admin" : value;
}

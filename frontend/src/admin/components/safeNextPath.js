/** Only internal admin paths are accepted as post-login destinations. */
export function safeNextPath(value) {
  if (typeof value !== "string" || !value.startsWith("/admin")) return "/admin";
  if (value.startsWith("//") || value.includes("\\") || /[\r\n]/.test(value)) return "/admin";
  return value.startsWith("/admin/login") ? "/admin" : value;
}

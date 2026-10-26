/** Friendly wording for errors that aren't about a specific field. */
export function authErrorMessage(error) {
  if (!error) return "";
  if (error.status === 429) return "Too many attempts. Please wait a few minutes and try again.";
  if (!error.status || error.status >= 500)
    return "We couldn't reach the server. Check your connection and try again.";
  return error.message || "Something went wrong. Please try again.";
}

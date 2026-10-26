/** Mirrors backend/app/auth/passwords.py (the server always re-checks). */
export const MIN_PASSWORD_LENGTH = 12;

export function passwordChecks(password = "", email = "") {
  const local = (email.split("@")[0] || "").toLowerCase();
  return [
    {
      key: "length",
      label: `At least ${MIN_PASSWORD_LENGTH} characters`,
      ok: password.length >= MIN_PASSWORD_LENGTH,
    },
    {
      key: "variety",
      label: "Not too repetitive (5+ different characters)",
      ok: new Set(password).size >= 5,
    },
    {
      key: "email",
      label: "Doesn't contain the name part of your email",
      ok: Boolean(password) && !(local.length >= 3 && password.toLowerCase().includes(local)),
    },
    {
      key: "spaces",
      label: "Doesn't start or end with a space",
      ok: Boolean(password) && password.trim() === password,
    },
  ];
}

export const meetsPasswordRules = (password, email) =>
  passwordChecks(password, email).every((r) => r.ok);

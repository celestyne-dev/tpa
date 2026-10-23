const TONES = {
  dark: {
    label: "text-ivory",
    input:
      "border-ivory/25 bg-ivory/10 text-ivory placeholder:text-sage-100/70 focus:border-gold-300",
    hint: "text-sage-100",
    error: "text-gold-300",
  },
  light: {
    label: "text-charcoal",
    input: "border-charcoal/20 bg-white text-charcoal placeholder:text-muted focus:border-sage-600",
    hint: "text-muted",
    error: "text-red-800",
  },
};

export function toneClasses(tone) {
  return TONES[tone] ?? TONES.dark;
}

export const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

export function signupErrorMessage(error) {
  if (error?.status === 429) return "Too many attempts. Please wait a little and try again.";
  if (error?.status === 409) return error.message;
  if (error?.status >= 500 || !error?.status)
    return "Something went wrong on our side. Please try again in a moment.";
  return error.message || "Please check the form and try again.";
}

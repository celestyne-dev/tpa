import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextAreaField, TextField } from "../Fields";
import { fieldError } from "../fieldError";

/**
 * Sponsor and disclosure for a newsletter edition. The disclosure is added at the top of
 * the email (HTML and plain text); approval of a sponsored edition needs sponsorship rights.
 */
export function NewsletterSponsorship({ value, editable, onSave }) {
  const [form, setForm] = useState({
    sponsor_name: value?.sponsor_name ?? "",
    disclosure_text: value?.disclosure_text ?? "",
  });
  const [error, setError] = useState(null);
  const submit = async (next) => {
    setError(null);
    try {
      await onSave(next);
    } catch (err) {
      setError(err);
    }
  };
  return (
    <section className="space-y-3 rounded-2xl bg-white p-5 shadow-sm">
      <h2 className="font-medium">Sponsorship</h2>
      <p className="text-xs text-muted">
        {value ? "This edition is sponsored." : "This edition is not sponsored."} Sponsored editions
        show “Sponsored by …” at the top of the email.
      </p>
      <TextField
        label="Sponsor"
        disabled={!editable}
        value={form.sponsor_name}
        error={fieldError(error, "sponsorship")}
        onChange={(e) => setForm({ ...form, sponsor_name: e.target.value })}
      />
      <TextAreaField
        label="Disclosure"
        disabled={!editable}
        hint="For example: “This edition is sponsored by Calm Co.”"
        value={form.disclosure_text}
        onChange={(e) => setForm({ ...form, disclosure_text: e.target.value })}
      />
      {error && !error.details && (
        <p role="alert" className="text-sm text-red-800">
          {error.message}
        </p>
      )}
      {editable && (
        <div className="flex gap-2">
          <Button size="sm" onClick={() => submit(form)}>
            Save sponsorship
          </Button>
          {value && (
            <Button size="sm" variant="outline" onClick={() => submit(null)}>
              Remove
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

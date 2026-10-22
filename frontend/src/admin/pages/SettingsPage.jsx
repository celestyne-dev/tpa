import { Save } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { fieldError } from "../components/fieldError";
import { CheckboxField, TextAreaField, TextField } from "../components/Fields";
import { useNotify } from "../components/notifyContext";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";

const INPUT_TYPES = { email: "email", https_url: "url", path_or_https: "text", string: "text" };

export function SettingsPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, error, reload, setData } = useAdminQuery(() => api.settings.get(), []);
  const [values, setValues] = useState({});
  const [saveError, setSaveError] = useState(null);
  const [busy, setBusy] = useState(false);

  const original = useMemo(() => {
    const out = {};
    data?.groups.forEach((g) => g.settings.forEach((s) => (out[s.key] = s.value)));
    return out;
  }, [data]);
  const changed = Object.fromEntries(Object.entries(values).filter(([k, v]) => original[k] !== v));
  const dirty = Object.keys(changed).length > 0;
  useUnsavedChanges(dirty);

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setSaveError(null);
    try {
      const res = await api.settings.save(changed);
      setData(res.data);
      setValues({});
      notify("Settings saved. The static site updates after the next build.");
    } catch (err) {
      setSaveError(err);
      notify(err.status === 400 ? "Please fix the highlighted settings." : err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Site settings"
        description="Branding, contact details, social links, SEO defaults and footer text."
        breadcrumbs={[{ label: "Settings" }]}
      />
      {error && <ErrorState title="We couldn't load settings" onRetry={reload} />}
      {!data && !error && <Skeleton className="h-96 w-full" />}
      {data && (
        <form onSubmit={save} className="space-y-6">
          {data.groups.map((group) => (
            <fieldset
              key={group.name}
              className="rounded-xl border border-charcoal/10 bg-white p-5"
            >
              <legend className="px-1 font-sans text-base font-semibold">{group.name}</legend>
              <div className="mt-2 grid gap-4 md:grid-cols-2">
                {group.settings.map((s) => {
                  const value = s.key in values ? values[s.key] : s.value;
                  const onChange = (e) =>
                    setValues((v) => ({
                      ...v,
                      [s.key]: s.type === "boolean" ? e.target.checked : e.target.value,
                    }));
                  if (s.type === "boolean")
                    return (
                      <CheckboxField
                        key={s.key}
                        className="md:col-span-2"
                        label={s.label}
                        hint={s.help}
                        checked={Boolean(value)}
                        onChange={onChange}
                      />
                    );
                  if (s.type === "text")
                    return (
                      <TextAreaField
                        key={s.key}
                        className="md:col-span-2"
                        label={s.label}
                        hint={s.help || `Up to ${s.max_length} characters.`}
                        maxLength={s.max_length}
                        value={value ?? ""}
                        onChange={onChange}
                        error={fieldError(saveError, s.key)}
                      />
                    );
                  return (
                    <TextField
                      key={s.key}
                      label={s.label}
                      hint={s.help}
                      type={INPUT_TYPES[s.type] ?? "text"}
                      maxLength={s.max_length}
                      value={value ?? ""}
                      onChange={onChange}
                      error={fieldError(saveError, s.key)}
                    />
                  );
                })}
              </div>
            </fieldset>
          ))}
          <div className="sticky bottom-0 flex items-center justify-end gap-3 border-t border-charcoal/10 bg-ivory/95 py-4">
            {dirty && (
              <span className="text-sm text-gold-700">
                {Object.keys(changed).length} unsaved change(s)
              </span>
            )}
            <Button type="submit" disabled={!dirty || busy}>
              <Save aria-hidden />
              {busy ? "Saving…" : "Save settings"}
            </Button>
          </div>
        </form>
      )}
    </>
  );
}

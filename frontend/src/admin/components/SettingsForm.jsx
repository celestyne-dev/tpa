import { Save } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/utils/format";
import { useAdminApi } from "../adminApiContext";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import { fieldError } from "./fieldError";
import { CheckboxField, SelectField, TextAreaField, TextField } from "./Fields";
import { ImageChooser } from "./media/ImageChooser";
import { useNotify } from "./notifyContext";

const INPUT_TYPES = { email: "email", https_url: "url", path_or_https: "text", string: "text" };

function SettingField({ setting, value, onChange, error }) {
  const common = { label: setting.label, hint: setting.help, error };
  switch (setting.type) {
    case "boolean":
      return (
        <CheckboxField
          className="md:col-span-2"
          label={setting.label}
          hint={setting.help}
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
        />
      );
    case "text":
    case "path_list":
      return (
        <TextAreaField
          {...common}
          className="md:col-span-2"
          rows={setting.type === "path_list" ? 4 : 3}
          hint={setting.help || `Up to ${setting.max_length} characters.`}
          maxLength={setting.max_length}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "choice":
      return (
        <SelectField
          {...common}
          value={value ?? ""}
          options={setting.choices}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "media":
      return (
        <div className="space-y-1.5">
          <p className="text-sm font-medium text-charcoal">{setting.label}</p>
          {setting.help && <p className="text-sm text-muted">{setting.help}</p>}
          <ImageChooser mediaId={value} label="image" onChange={(id) => onChange(id ?? null)} />
          {error && (
            <p role="alert" className="text-sm text-red-800">
              {error}
            </p>
          )}
        </div>
      );
    default:
      return (
        <TextField
          {...common}
          type={INPUT_TYPES[setting.type] ?? "text"}
          maxLength={setting.max_length}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      );
  }
}

/**
 * Registered site settings for the given groups (or all except `exclude`). Saving
 * updates the live website after the next rebuild, so the button says so.
 */
export function SettingsForm({ groups = null, exclude = [], children, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const { data, error, reload, setData } = useAdminQuery(
    () => api.settings.get(groups),
    [(groups ?? []).join(",")],
  );
  const [values, setValues] = useState({});
  const [saveError, setSaveError] = useState(null);
  const [busy, setBusy] = useState(false);
  const shown = (data?.groups ?? []).filter((g) => !exclude.includes(g.name));

  const original = Object.fromEntries(
    shown.flatMap((g) => g.settings.map((s) => [s.key, s.value])),
  );
  const changed = Object.fromEntries(Object.entries(values).filter(([k, v]) => original[k] !== v));
  const dirty = Object.keys(changed).length > 0;
  useUnsavedChanges(dirty);

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setSaveError(null);
    try {
      const res = await api.settings.save(changed, groups);
      setData(res.data);
      setValues({});
      notify("Saved. The website updates after the queued rebuild finishes.");
      onSaved?.(res.data);
    } catch (err) {
      setSaveError(err);
      notify(err.status === 400 ? "Please fix the highlighted settings." : err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  if (error) return <ErrorState title="We couldn't load these settings" onRetry={reload} />;
  if (!data) return <Skeleton className="h-64 w-full" />;
  const current = (key, fallback) => (key in values ? values[key] : fallback);
  return (
    <form onSubmit={save} className="space-y-6">
      {shown.map((group) => (
        <fieldset key={group.name} className="rounded-xl border border-charcoal/10 bg-white p-5">
          <legend className="px-1 font-sans text-base font-semibold">{group.name}</legend>
          <div className="mt-2 grid gap-4 md:grid-cols-2">
            {group.settings.map((s) => (
              <SettingField
                key={s.key}
                setting={s}
                value={current(s.key, s.value)}
                error={fieldError(saveError, s.key)}
                onChange={(v) => setValues((all) => ({ ...all, [s.key]: v }))}
              />
            ))}
          </div>
        </fieldset>
      ))}
      {children?.({ values: { ...original, ...values } })}
      <div
        className={cn(
          "sticky bottom-0 flex flex-wrap items-center justify-end gap-3 border-t border-charcoal/10 bg-ivory/95 py-4",
        )}
      >
        {dirty && (
          <span className="text-sm text-gold-700">
            {Object.keys(changed).length} unsaved change(s)
          </span>
        )}
        <Button type="submit" disabled={!dirty || busy}>
          <Save aria-hidden />
          {busy ? "Saving…" : "Save and publish"}
        </Button>
      </div>
    </form>
  );
}

import { ArrowDown, ArrowUp, Save } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdminApi } from "../adminApiContext";
import { fieldError } from "../components/fieldError";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { CheckboxField, SelectField, TextAreaField, TextField } from "../components/Fields";
import { useNotify } from "../components/notifyContext";
import { useAdminQuery } from "../hooks/useAdminQuery";
import { usePermissions } from "../hooks/usePermissions";

function SectionEditor({ section, type, pageId, canWrite, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [content, setContent] = useState(section.content);
  const [variant, setVariant] = useState(section.variant);
  const [visible, setVisible] = useState(section.is_visible);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.pages.updateSection(pageId, section.id, {
        content,
        variant,
        is_visible: visible,
      });
      onSaved(res.data);
      notify(`Section “${section.key}” saved.`);
    } catch (err) {
      setError(err);
      notify("Please fix the highlighted fields.", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <fieldset disabled={!canWrite} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField
          label="Layout variant"
          value={variant}
          options={type.variants.map((v) => ({ value: v, label: v.replaceAll("_", " ") }))}
          onChange={(e) => setVariant(e.target.value)}
          error={fieldError(error, "variant")}
        />
        <CheckboxField
          className="sm:mt-7"
          label="Visible"
          checked={visible}
          onChange={(e) => setVisible(e.target.checked)}
        />
      </div>
      {type.fields.map((f) => {
        const props = {
          label: f.label,
          required: f.required,
          error: fieldError(error, f.name),
        };
        if (f.type === "string_list")
          return (
            <TextAreaField
              key={f.name}
              {...props}
              hint="One item per line."
              rows={4}
              value={(content[f.name] ?? []).join("\n")}
              onChange={(e) => setContent({ ...content, [f.name]: e.target.value.split("\n") })}
            />
          );
        if (f.type === "textarea")
          return (
            <TextAreaField
              key={f.name}
              {...props}
              rows={3}
              value={content[f.name] ?? ""}
              onChange={(e) => setContent({ ...content, [f.name]: e.target.value })}
            />
          );
        return (
          <TextField
            key={f.name}
            {...props}
            hint={f.type === "path" ? "Internal link, e.g. /articles" : undefined}
            value={content[f.name] ?? ""}
            onChange={(e) => setContent({ ...content, [f.name]: e.target.value })}
          />
        );
      })}
      {canWrite && (
        <Button size="sm" onClick={save} disabled={busy}>
          <Save aria-hidden />
          {busy ? "Saving…" : "Save section"}
        </Button>
      )}
    </fieldset>
  );
}

export function PageEditorPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const notify = useNotify();
  const { can } = usePermissions();
  const canWrite = can("pages.write");
  const page = useAdminQuery(() => api.pages.get(id), [id]);
  const types = useAdminQuery(() => api.pages.sectionTypes(), []);

  if (page.error) return <ErrorState title="We couldn't load this page" onRetry={page.reload} />;
  if (!page.data || !types.data)
    return (
      <div role="status" aria-label="Loading page" className="space-y-3">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-48 w-full" />
      </div>
    );

  const typeMap = Object.fromEntries(types.data.map((t) => [t.type, t]));
  const sections = page.data.sections;

  const move = async (index, delta) => {
    const order = sections.map((s) => s.id);
    const [item] = order.splice(index, 1);
    order.splice(index + delta, 0, item);
    try {
      const res = await api.pages.reorder(page.data.id, order);
      page.setData(res.data);
      notify("Section order saved.");
    } catch (err) {
      notify(err.message, "error");
    }
  };

  return (
    <>
      <AdminPageHeader
        title={page.data.title}
        description={`/${page.data.slug === "home" ? "" : page.data.slug} · ${sections.length} sections`}
        breadcrumbs={[{ label: "Pages", to: "/admin/pages" }, { label: page.data.title }]}
      />
      {!page.data.rendered_publicly && (
        <p className="mb-4 rounded-lg bg-gold-100/60 px-4 py-3 text-sm">
          These sections are saved and validated but are not yet rendered on the public page. The
          current public page keeps its approved design until the page builder is connected (Batch
          04).
        </p>
      )}
      <ol className="space-y-4">
        {sections.map((section, index) => (
          <li key={section.id} className="rounded-xl border border-charcoal/10 bg-white">
            <details>
              <summary className="flex cursor-pointer items-center justify-between gap-3 px-5 py-4">
                <span>
                  <span className="font-medium">
                    {index + 1}. {section.type_label}
                  </span>
                  <span className="ml-2 text-xs text-muted">{section.key}</span>
                  {!section.is_visible && (
                    <span className="ml-2 text-xs text-gold-700">(hidden)</span>
                  )}
                </span>
                {canWrite && (
                  <span className="flex gap-1">
                    <button
                      type="button"
                      aria-label={`Move ${section.key} up`}
                      disabled={index === 0}
                      onClick={(e) => {
                        e.preventDefault();
                        move(index, -1);
                      }}
                      className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                    >
                      <ArrowUp aria-hidden className="size-4" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Move ${section.key} down`}
                      disabled={index === sections.length - 1}
                      onClick={(e) => {
                        e.preventDefault();
                        move(index, 1);
                      }}
                      className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
                    >
                      <ArrowDown aria-hidden className="size-4" />
                    </button>
                  </span>
                )}
              </summary>
              <div className="border-t border-charcoal/10 px-5 py-4">
                {typeMap[section.section_type] ? (
                  <SectionEditor
                    section={section}
                    type={typeMap[section.section_type]}
                    pageId={page.data.id}
                    canWrite={canWrite}
                    onSaved={(updated) =>
                      page.setData((p) => ({
                        ...p,
                        sections: p.sections.map((s) => (s.id === updated.id ? updated : s)),
                      }))
                    }
                  />
                ) : (
                  <p className="text-sm text-red-800">Unknown section type.</p>
                )}
              </div>
            </details>
          </li>
        ))}
      </ol>
    </>
  );
}

import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { CheckboxField, SelectField, TextField } from "../components/Fields";
import { useNotify } from "../components/notifyContext";
import { useAdminQuery } from "../hooks/useAdminQuery";

const blankLink = () => ({
  label: "",
  link_type: "internal",
  url: "/",
  open_in_new_tab: false,
  is_visible: true,
  children: [],
});

function moveItem(list, index, delta) {
  const next = [...list];
  const [item] = next.splice(index, 1);
  next.splice(index + delta, 0, item);
  return next;
}

function ItemRow({ item, index, count, path, errors, onChange, onMove, onRemove, allowHeading }) {
  const label = item.label || `Item ${index + 1}`;
  return (
    <div className="grid gap-3 rounded-lg border border-charcoal/10 bg-white p-3 md:grid-cols-[1fr_9rem_1fr_auto] md:items-end">
      <TextField
        label="Label"
        value={item.label}
        onChange={(e) => onChange({ ...item, label: e.target.value })}
      />
      <SelectField
        label="Type"
        value={item.link_type}
        options={[
          { value: "internal", label: "Internal" },
          { value: "external", label: "External" },
          ...(allowHeading ? [{ value: "heading", label: "Group heading" }] : []),
        ]}
        onChange={(e) =>
          onChange({
            ...item,
            link_type: e.target.value,
            url: e.target.value === "heading" ? "" : item.url,
          })
        }
      />
      {item.link_type === "heading" ? (
        <p className="text-sm text-muted md:pb-2">Groups the links below it.</p>
      ) : (
        <TextField
          label="Link"
          placeholder={item.link_type === "external" ? "https://" : "/articles"}
          value={item.url ?? ""}
          onChange={(e) => onChange({ ...item, url: e.target.value })}
        />
      )}
      <div className="flex items-center gap-1 md:pb-1">
        <button
          type="button"
          aria-label={`Move ${label} up`}
          disabled={index === 0}
          onClick={() => onMove(-1)}
          className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
        >
          <ArrowUp aria-hidden className="size-4" />
        </button>
        <button
          type="button"
          aria-label={`Move ${label} down`}
          disabled={index === count - 1}
          onClick={() => onMove(1)}
          className="rounded p-1.5 text-muted hover:bg-beige disabled:opacity-40"
        >
          <ArrowDown aria-hidden className="size-4" />
        </button>
        <button
          type="button"
          aria-label={`Remove ${label}`}
          onClick={onRemove}
          className="rounded p-1.5 text-muted hover:bg-red-50 hover:text-red-800"
        >
          <Trash2 aria-hidden className="size-4" />
        </button>
      </div>
      <div className="flex flex-wrap gap-4 md:col-span-4">
        <CheckboxField
          label="Visible"
          checked={item.is_visible}
          onChange={(e) => onChange({ ...item, is_visible: e.target.checked })}
        />
        {item.link_type === "external" && (
          <CheckboxField
            label="Open in new tab"
            checked={item.open_in_new_tab}
            onChange={(e) => onChange({ ...item, open_in_new_tab: e.target.checked })}
          />
        )}
      </div>
      {errors?.[path] && (
        <p role="alert" className="text-sm text-red-800 md:col-span-4">
          {errors[path].join(" ")}
        </p>
      )}
    </div>
  );
}

function MenuEditor({ menu, onSaved }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [items, setItems] = useState(menu.items);
  const [errors, setErrors] = useState(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    setErrors(null);
    try {
      const res = await api.navigation.save(menu.key, items);
      onSaved(res.data);
      notify(`${menu.name} saved. The static site updates after the next build.`);
    } catch (err) {
      setErrors(err.details ?? null);
      notify(err.status === 400 ? "Please fix the highlighted items." : err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const setItem = (i, value) => setItems(items.map((it, idx) => (idx === i ? value : it)));

  return (
    <section
      aria-labelledby={`menu-${menu.key}`}
      className="rounded-xl border border-charcoal/10 bg-cream/40 p-5"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id={`menu-${menu.key}`} className="font-sans text-lg font-semibold">
            {menu.name}
          </h2>
          {menu.is_default && (
            <p className="text-sm text-muted">Using built-in defaults until you save.</p>
          )}
        </div>
        <Button size="sm" onClick={save} disabled={busy}>
          <Save aria-hidden />
          {busy ? "Saving…" : "Save menu"}
        </Button>
      </div>
      <ol className="space-y-3">
        {items.map((item, i) => (
          <li key={i} className="space-y-2">
            <ItemRow
              item={item}
              index={i}
              count={items.length}
              path={String(i)}
              errors={errors}
              allowHeading={menu.allows_groups}
              onChange={(v) => setItem(i, v)}
              onMove={(d) => setItems(moveItem(items, i, d))}
              onRemove={() => setItems(items.filter((_, idx) => idx !== i))}
            />
            {item.link_type === "heading" && (
              <div className="ml-6 space-y-2 border-l-2 border-sage-200 pl-4">
                {(item.children ?? []).map((child, ci) => (
                  <ItemRow
                    key={ci}
                    item={child}
                    index={ci}
                    count={item.children.length}
                    path={`${i}.${ci}`}
                    errors={errors}
                    allowHeading={false}
                    onChange={(v) =>
                      setItem(i, {
                        ...item,
                        children: item.children.map((c, x) => (x === ci ? v : c)),
                      })
                    }
                    onMove={(d) =>
                      setItem(i, { ...item, children: moveItem(item.children, ci, d) })
                    }
                    onRemove={() =>
                      setItem(i, { ...item, children: item.children.filter((_, x) => x !== ci) })
                    }
                  />
                ))}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    setItem(i, { ...item, children: [...(item.children ?? []), blankLink()] })
                  }
                >
                  <Plus aria-hidden />
                  Add link to {item.label || "group"}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ol>
      <Button
        variant="outline"
        size="sm"
        className="mt-3"
        onClick={() =>
          setItems([
            ...items,
            menu.allows_groups ? { ...blankLink(), link_type: "heading", url: "" } : blankLink(),
          ])
        }
      >
        <Plus aria-hidden />
        {menu.allows_groups ? "Add group" : "Add link"}
      </Button>
    </section>
  );
}

export function NavigationPage() {
  const api = useAdminApi();
  const { data, error, reload, setData } = useAdminQuery(() => api.navigation.list(), []);
  return (
    <>
      <AdminPageHeader
        title="Navigation"
        description="Primary header links and footer link groups. Internal links start with /; external links must use https://."
        breadcrumbs={[{ label: "Navigation" }]}
      />
      {error && <ErrorState title="We couldn't load navigation" onRetry={reload} />}
      {!data && !error && <Skeleton className="h-64 w-full" />}
      <div className="space-y-6">
        {data?.map((menu) => (
          <MenuEditor
            key={menu.key}
            menu={menu}
            onSaved={(saved) =>
              setData((list) => list.map((m) => (m.key === saved.key ? saved : m)))
            }
          />
        ))}
      </div>
    </>
  );
}

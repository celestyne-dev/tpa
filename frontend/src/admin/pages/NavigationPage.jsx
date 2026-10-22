import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdminApi } from "../adminApiContext";
import { AdminPageHeader } from "../components/AdminPageHeader";
import { BuilderLookups } from "../components/builder/BuilderLookups";
import { LinkField } from "../components/builder/SectionFields";
import { CheckboxField, SelectField, TextField } from "../components/Fields";
import { useNotify } from "../components/notifyContext";
import { SettingsForm } from "../components/SettingsForm";
import { useAdminQuery } from "../hooks/useAdminQuery";

const blankLink = () => ({
  label: "",
  link_type: "internal",
  url: "/",
  open_in_new_tab: false,
  is_visible: true,
  visibility: "all",
  children: [],
});
// Header menus can target devices; footer links always show everywhere.
const DEVICE_MENUS = new Set(["primary", "mobile"]);

function moveItem(list, index, delta) {
  const next = [...list];
  const [item] = next.splice(index, 1);
  next.splice(index + delta, 0, item);
  return next;
}

function ItemRow({
  item,
  index,
  count,
  path,
  errors,
  onChange,
  onMove,
  onRemove,
  allowHeading,
  allowDevices,
}) {
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
        <LinkField
          label="Link"
          hint={
            item.link_type === "external"
              ? "A full https:// address."
              : "A site path, e.g. /articles"
          }
          value={item.url ?? ""}
          onChange={(url) => onChange({ ...item, url })}
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
        {allowDevices && (
          <label className="flex items-center gap-2 text-sm">
            <span className="font-medium">Show on</span>
            <select
              value={item.visibility ?? "all"}
              onChange={(e) => onChange({ ...item, visibility: e.target.value })}
              className="rounded-lg border border-charcoal/20 bg-white px-2 py-1"
            >
              <option value="all">All devices</option>
              <option value="desktop">Desktop header only</option>
              <option value="mobile">Mobile menu only</option>
            </select>
          </label>
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
          {menu.help && <p className="text-sm text-muted">{menu.help}</p>}
          {menu.is_default && menu.items.length > 0 && (
            <p className="text-sm text-muted">Using built-in defaults until you save.</p>
          )}
        </div>
        <Button size="sm" onClick={save} disabled={busy}>
          <Save aria-hidden />
          {busy ? "Saving…" : "Save and publish"}
        </Button>
      </div>
      {menu.warnings?.length > 0 && (
        <ul className="mb-3 space-y-1 rounded-lg bg-gold-100/70 px-4 py-2 text-sm text-charcoal">
          {menu.warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}
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
              allowDevices={DEVICE_MENUS.has(menu.key)}
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
                    allowDevices={DEVICE_MENUS.has(menu.key)}
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
      <div className="mt-3 flex flex-wrap gap-2">
        {menu.key !== "footer" && (
          <Button variant="outline" size="sm" onClick={() => setItems([...items, blankLink()])}>
            <Plus aria-hidden />
            Add link
          </Button>
        )}
        {menu.allows_groups && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setItems([...items, { ...blankLink(), link_type: "heading", url: "" }])}
          >
            <Plus aria-hidden />
            {menu.key === "footer" ? "Add column" : "Add dropdown group"}
          </Button>
        )}
      </div>
    </section>
  );
}

export function NavigationPage() {
  const api = useAdminApi();
  const { data, error, reload, setData } = useAdminQuery(() => api.navigation.list(), []);
  const [header, setHeader] = useState(false);
  return (
    <BuilderLookups>
      <AdminPageHeader
        title="Navigation"
        description="Header menu (with dropdown groups), mobile menu, footer columns and legal links. Internal links start with /; external links must use https://."
        breadcrumbs={[{ label: "Navigation" }]}
      />
      <details
        className="mb-6 rounded-xl border border-charcoal/10 bg-white p-4"
        open={header}
        onToggle={(e) => setHeader(e.currentTarget.open)}
      >
        <summary className="cursor-pointer font-sans font-semibold">Header button</summary>
        <div className="mt-4">{header && <SettingsForm groups={["Header"]} />}</div>
      </details>
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
    </BuilderLookups>
  );
}

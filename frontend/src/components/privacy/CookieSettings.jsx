import { useEffect, useId, useState, useSyncExternalStore } from "react";
import { Link } from "react-router";
import { Modal } from "@/admin/components/Modal";
import { Button } from "@/components/ui/Button";
import { useSite } from "@/hooks/useContent";
import {
  hasOptionalCategories,
  needsDecision,
  onOpenPrivacySettings,
  openPrivacySettings,
  saveChoice,
  statisticsDecision,
  usePrivacyChoice,
} from "@/privacy/choices";
import { cn } from "@/utils/format";

const noSubscribe = () => () => {};
const isClient = () => true;
const isServer = () => false;

function PolicyLink({ privacy, className }) {
  const href = privacy?.policy_path || "/cookie-policy";
  const label = "Read our Cookie Policy";
  return href.startsWith("/") ? (
    <Link to={href} className={className}>
      {label}
    </Link>
  ) : (
    <a href={href} className={className}>
      {label}
    </a>
  );
}

function Category({ category, checked, onChange }) {
  const id = useId();
  return (
    <li className="flex items-start justify-between gap-4 rounded-xl border border-charcoal/10 bg-white/60 p-4">
      <div>
        <p id={`${id}-label`} className="font-medium text-charcoal">
          {category.label}
        </p>
        <p id={`${id}-desc`} className="mt-1 text-sm text-muted">
          {category.description}
        </p>
      </div>
      {category.required ? (
        <span className="shrink-0 rounded-full bg-sage-100 px-3 py-1 text-xs font-semibold text-sage-800">
          Always on
        </span>
      ) : (
        <label className="relative mt-0.5 inline-flex shrink-0 cursor-pointer items-center">
          <input
            type="checkbox"
            role="switch"
            checked={checked}
            onChange={(e) => onChange(e.target.checked)}
            aria-labelledby={`${id}-label`}
            aria-describedby={`${id}-desc`}
            className="peer sr-only"
          />
          <span
            aria-hidden
            className="h-7 w-12 rounded-full bg-charcoal/25 transition-colors peer-checked:bg-sage-700 peer-focus-visible:ring-2 peer-focus-visible:ring-sage-700 peer-focus-visible:ring-offset-2"
          />
          <span
            aria-hidden
            className="absolute left-1 size-5 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5 motion-reduce:transition-none"
          />
        </label>
      )}
    </li>
  );
}

/**
 * Cookie settings: the panel (opened from the footer link, the notice or a page) and, only
 * where the website must ask first (consent mode), a small non-blocking notice. The
 * categories come from the server, which lists only technologies the site actually uses;
 * the choice controls the usage statistics beacon (analytics/pageViews.js).
 */
export function PrivacyChoices() {
  const { data: site } = useSite();
  const privacy = site?.privacy;
  const choice = usePrivacyChoice();
  const [open, setOpen] = useState(false);
  const [statistics, setStatistics] = useState(false);
  // False while prerendering and hydrating (the stored choice is only known in the
  // browser), so the notice never flashes for a visitor who has already chosen.
  const mounted = useSyncExternalStore(noSubscribe, isClient, isServer);
  const [status, setStatus] = useState("");

  const current = statisticsDecision(privacy, choice).allowed;
  useEffect(
    () =>
      onOpenPrivacySettings(() => {
        setStatistics(current);
        setOpen(true);
      }),
    [current],
  );

  if (!hasOptionalCategories(privacy)) return null;

  const decide = (value) => {
    saveChoice({ version: privacy.version, statistics: value });
    setOpen(false);
    setStatus(value ? "Usage statistics are on." : "Usage statistics are off.");
  };
  const showNotice = mounted && !open && needsDecision(privacy, choice);

  return (
    <>
      <p role="status" className="sr-only">
        {status}
      </p>
      <Modal
        open={open}
        title={privacy.settings_label || "Cookie settings"}
        description={privacy.intro}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => decide(false)}>
              Reject optional
            </Button>
            <Button variant="outline" size="sm" onClick={() => decide(true)}>
              Accept optional
            </Button>
            <Button size="sm" onClick={() => decide(statistics)} data-autofocus>
              Save choices
            </Button>
          </>
        }
      >
        <ul className="space-y-3" aria-label="Categories">
          {privacy.categories.map((category) => (
            <Category
              key={category.key}
              category={category}
              checked={category.key === "statistics" ? statistics : true}
              onChange={setStatistics}
            />
          ))}
        </ul>
        <p className="mt-4 text-sm">
          <PolicyLink
            privacy={privacy}
            className="font-medium text-sage-700 underline underline-offset-4"
          />
        </p>
      </Modal>
      {showNotice && (
        <section
          aria-label="Cookie notice"
          className={cn(
            "fixed inset-x-0 bottom-0 z-50 border-t border-charcoal/10 bg-ivory p-4 shadow-lift",
            "sm:inset-x-auto sm:bottom-4 sm:left-4 sm:max-w-md sm:rounded-2xl sm:border sm:p-5",
          )}
        >
          <p className="text-[0.95rem] text-ink">{privacy.notice}</p>
          <p className="mt-1 text-sm">
            <PolicyLink privacy={privacy} className="text-sage-700 underline underline-offset-4" />
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {/* Accepting and rejecting are equally easy: same style, side by side. */}
            <Button size="sm" variant="secondary" onClick={() => decide(true)}>
              Accept
            </Button>
            <Button size="sm" variant="secondary" onClick={() => decide(false)}>
              Reject
            </Button>
            <Button size="sm" variant="ghost" onClick={openPrivacySettings}>
              Customise
            </Button>
          </div>
        </section>
      )}
    </>
  );
}

/** The footer's "Cookie settings" link (a button: it opens the panel, it isn't a page). */
export function CookieSettingsLink({ className }) {
  const { data: site } = useSite();
  if (!hasOptionalCategories(site?.privacy)) return null;
  return (
    <button type="button" onClick={openPrivacySettings} className={className}>
      {site.privacy.settings_label || "Cookie settings"}
    </button>
  );
}

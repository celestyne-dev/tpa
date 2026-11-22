import { ArrowRight, ArrowUpRight, X } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router";
import { Container } from "@/components/ui/Container";
import { useNow } from "@/hooks/useNow";
import { cn } from "@/utils/format";

const STORAGE_KEY = "tpa:dismissed-announcements";

/**
 * Colours per CMS variant: the bar, the optional label, the call-to-action button and the
 * dismiss button. Dark bars (sage, charcoal) get a cream button with dark text; light bars
 * (gold, cream) get a deep-sage button with light text. Focus rings contrast with each bar.
 */
const VARIANTS = {
  sage: {
    bar: "bg-sage-800 text-ivory",
    label: "bg-ivory/12 text-gold-300",
    cta: "bg-cream text-sage-800 hover:bg-ivory focus-visible:outline-gold-300",
    close: "text-ivory/85 hover:bg-ivory/15 hover:text-ivory focus-visible:outline-gold-300",
  },
  charcoal: {
    bar: "bg-charcoal text-ivory",
    label: "bg-ivory/10 text-gold-300",
    cta: "bg-cream text-charcoal hover:bg-ivory focus-visible:outline-gold-300",
    close: "text-ivory/85 hover:bg-ivory/15 hover:text-ivory focus-visible:outline-gold-300",
  },
  gold: {
    bar: "bg-gold-100 text-charcoal",
    label: "bg-charcoal/[0.08] text-charcoal",
    cta: "bg-sage-800 text-ivory hover:bg-sage-700 focus-visible:outline-sage-800",
    close:
      "text-charcoal/80 hover:bg-charcoal/10 hover:text-charcoal focus-visible:outline-sage-800",
  },
  ivory: {
    bar: "border-b border-charcoal/10 bg-cream text-charcoal",
    label: "bg-sage-100 text-sage-800",
    cta: "bg-sage-800 text-ivory hover:bg-sage-700 focus-visible:outline-sage-800",
    close:
      "text-charcoal/80 hover:bg-charcoal/10 hover:text-charcoal focus-visible:outline-sage-800",
  },
};

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2";
const CTA_CLASS =
  "group inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold whitespace-nowrap shadow-sm transition-colors";

function readDismissed() {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function matchesPage(announcement, pathname) {
  if (announcement.target === "home") return pathname === "/";
  if (announcement.target === "paths") return announcement.paths.includes(pathname);
  return true;
}

function isLive(announcement, now) {
  const starts = announcement.starts_at ? Date.parse(announcement.starts_at) : null;
  const ends = announcement.ends_at ? Date.parse(announcement.ends_at) : null;
  return (starts === null || starts <= now) && (ends === null || now < ends);
}

/** The announcement's button: internal paths use the router; https links open safely. */
function AnnouncementCta({ cta, tone }) {
  const className = cn(CTA_CLASS, FOCUS, tone);
  const arrow = "size-4 transition-transform motion-reduce:transition-none";
  if (cta.href.startsWith("https://")) {
    return (
      <a href={cta.href} target="_blank" rel="noopener noreferrer" className={className}>
        {cta.label}
        <ArrowUpRight
          aria-hidden
          className={cn(
            arrow,
            "group-hover:translate-x-0.5 group-hover:-translate-y-0.5 motion-reduce:group-hover:transform-none",
          )}
        />
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    );
  }
  return (
    <Link to={cta.href} className={className}>
      {cta.label}
      <ArrowRight
        aria-hidden
        className={cn(
          arrow,
          "group-hover:translate-x-0.5 motion-reduce:group-hover:transform-none",
        )}
      />
    </Link>
  );
}

/**
 * One CMS-managed announcement above the header: never a popup, never covering content,
 * and nothing at all when no announcement applies. The optional label ("What's new") comes
 * from Admin › Announcements › Banner label; the message and button are the announcement's
 * own. From tablets up the label, message and button sit in one centred row (a long message
 * wraps beside the button) with the dismiss button at the end; on phones the button moves
 * under the message. Heights are never fixed.
 *
 * During hydration the API's generation time is used as "now" so the markup matches the
 * prerendered HTML; afterwards the real time and the reader's dismissals apply. Dismissals
 * are remembered per announcement *version* (the public id is "<id>-<revision>", and the
 * revision changes whenever an editor changes the announcement), so an updated
 * announcement is shown again to readers who closed an earlier version.
 */
export function AnnouncementBar({ site }) {
  const { pathname } = useLocation();
  const clock = useNow();
  const hydrated = clock !== null;
  const [dismissed, setDismissed] = useState(null);
  const announcements = site?.announcements ?? [];
  if (announcements.length === 0) return null;

  const now = clock ?? (Date.parse(site.generated_at ?? "") || 0);
  const hidden = hydrated ? (dismissed ?? readDismissed()) : [];
  const current = announcements.find(
    (a) => matchesPage(a, pathname) && isLive(a, now) && !hidden.includes(a.id),
  );
  if (!current) return null;

  const dismiss = () => {
    const next = [...hidden, current.id].slice(-20);
    setDismissed(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Storage unavailable (private mode): the banner simply stays hidden for this visit.
    }
  };
  const tone = VARIANTS[current.variant] ?? VARIANTS.sage;
  const label = site?.announcement_label?.trim();
  const cta = current.cta?.href && current.cta?.label ? current.cta : null;

  return (
    <div role="region" aria-label="Announcement" className={tone.bar}>
      <Container size="wide" className="flex items-center gap-2 py-2.5 sm:gap-4 sm:py-3">
        {/* Balances the dismiss button so the content is centred on wide screens. */}
        {current.dismissible && (
          <span aria-hidden className="-ml-2 hidden size-11 shrink-0 md:block" />
        )}
        <div className="flex min-w-0 flex-1 flex-wrap items-center justify-center gap-x-4 gap-y-2 text-center md:flex-nowrap md:gap-x-5">
          <p className="min-w-0 text-[0.9375rem] leading-snug font-medium text-balance sm:text-base">
            {label && (
              <span
                className={cn(
                  "mr-3 inline-block rounded-full px-2.5 py-1 align-[0.15em] text-[0.6875rem] leading-none font-semibold tracking-[0.16em] whitespace-nowrap uppercase",
                  tone.label,
                )}
              >
                {label}
              </span>
            )}
            {current.message}
          </p>
          {cta && <AnnouncementCta cta={cta} tone={tone.cta} />}
        </div>
        {current.dismissible &&
          (hydrated ? (
            <button
              type="button"
              onClick={dismiss}
              aria-label="Dismiss announcement"
              className={cn(
                "-mr-2 grid size-11 shrink-0 place-items-center rounded-full transition-colors",
                FOCUS,
                tone.close,
              )}
            >
              <X aria-hidden className="size-5" />
            </button>
          ) : (
            // Same footprint before hydration, so the bar does not shift when it appears.
            <span aria-hidden className="-mr-2 size-11 shrink-0" />
          ))}
      </Container>
    </div>
  );
}

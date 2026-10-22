import { ArrowRight, X } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router";
import { Container } from "@/components/ui/Container";
import { useNow } from "@/hooks/useNow";
import { cn } from "@/utils/format";

const STORAGE_KEY = "tpa:dismissed-announcements";
const variants = {
  sage: "bg-sage-800 text-ivory",
  gold: "bg-gold-100 text-charcoal",
  charcoal: "bg-charcoal text-ivory",
  ivory: "border-b border-charcoal/10 bg-cream text-charcoal",
};

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

/**
 * One slim, CMS-managed announcement above the header: never a popup, never
 * blocks content. During hydration the API's generation time is used as "now"
 * so the markup matches the prerendered HTML; afterwards the real time and the
 * reader's dismissals apply.
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
  const light = current.variant === "gold" || current.variant === "ivory";
  const cta = current.cta;

  return (
    <div
      role="region"
      aria-label="Announcement"
      className={cn("text-sm", variants[current.variant])}
    >
      <Container size="wide" className="flex items-center gap-4 py-2.5">
        <p className="flex-1 text-center sm:text-left">
          <span>{current.message}</span>
          {cta &&
            (cta.href.startsWith("https://") ? (
              <a
                href={cta.href}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-3 inline-flex items-center gap-1 font-semibold underline underline-offset-4"
              >
                {cta.label}
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            ) : (
              <Link
                to={cta.href}
                className="ml-3 inline-flex items-center gap-1 font-semibold underline underline-offset-4"
              >
                {cta.label}
                <ArrowRight aria-hidden className="size-3.5" />
              </Link>
            ))}
        </p>
        {current.dismissible && hydrated && (
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss announcement"
            className={cn(
              "grid size-8 shrink-0 place-items-center rounded-full transition-colors",
              light ? "hover:bg-charcoal/10" : "hover:bg-ivory/15",
            )}
          >
            <X aria-hidden className="size-4" />
          </button>
        )}
      </Container>
    </div>
  );
}

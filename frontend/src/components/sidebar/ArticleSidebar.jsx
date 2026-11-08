import { Mail } from "lucide-react";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import { ArticleCard } from "@/components/articles/ArticleCard";
import { LeadMagnetForm } from "@/components/newsletter/LeadMagnetForm";
import { NewsletterSignupForm } from "@/components/newsletter/NewsletterSignupForm";
import { SIDEBAR_NEWSLETTER_EMAIL_ID } from "@/components/newsletter/articleNewsletter";
import { useNewsletterStatus } from "@/components/newsletter/useNewsletterStatus";
import { liveOnly } from "@/components/partnerships/partnershipOptions";
import { EmptyPreviewNote } from "@/components/sections/ArticleSections";
import { DisclosureLabel, SponsoredAnchor } from "@/components/sections/PartnershipSections";
import { TopicLinks } from "@/components/topics/TopicLinks";
import { ContentImage } from "@/components/ui/ContentImage";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { useNow } from "@/hooks/useNow";
import { cn } from "@/utils/format";
import { SectionContext, useSectionContext } from "@/components/sections/sectionContext";

const PREVIEW_CONTEXT = { dark: false, design: {}, level: 2, first: false, preview: true };
const SITE_CONTEXT = { ...PREVIEW_CONTEXT, preview: false };

/** True on article pages, where the end-of-article panel carries the form below lg. */
const FormBelowArticle = createContext(false);

/** Sticky offset: the site header (h-20, 80px) plus breathing room; and the bottom gap. */
export const STICKY_OFFSET = 104;
const BOTTOM_GAP = 24;
const WIDE = "(min-width: 1024px)";

/**
 * Where the sidebar sticks, given its visible blocks ({top, height} relative to the
 * sidebar's top) and the viewport height. The sidebar sticks so that the longest run of
 * sections at its end that fits the viewport stays in view below the header:
 * - everything fits: the whole sidebar sticks at the offset;
 * - too tall: the sections before that run scroll away normally, and the run sticks
 *   (a negative top); nothing is ever cut off at the bottom of the screen;
 * - not even the last section fits: no sticking at all (null).
 */
export function stickyTop(blocks, viewportHeight, offset = STICKY_OFFSET) {
  const visible = blocks.filter((b) => b.height > 0);
  if (!visible.length) return null;
  const end = Math.max(...visible.map((b) => b.top + b.height));
  const available = viewportHeight - offset - BOTTOM_GAP;
  const start = visible.find((b) => end - b.top <= available);
  return start ? Math.round(offset - start.top) : null;
}

/**
 * Measures the sidebar (on wide screens only) and returns the sticky top, or null.
 * Re-measures when the sidebar's size changes (images, fonts, a form message) or the
 * window is resized; there is no scroll listener: the browser does the sticking.
 */
function useStickyTop(ref, enabled) {
  const [top, setTop] = useState(null);
  useEffect(() => {
    const el = ref.current;
    if (!enabled || !el || typeof window === "undefined" || !window.matchMedia) return undefined;
    const wide = window.matchMedia(WIDE);
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!wide.matches) return setTop(null);
        const origin = el.getBoundingClientRect().top;
        const blocks = [...el.children].map((child) => {
          const rect = child.getBoundingClientRect();
          return { top: rect.top - origin, height: rect.height };
        });
        setTop(stickyTop(blocks, window.innerHeight));
      });
    };
    measure();
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    observer?.observe(el);
    window.addEventListener("resize", measure);
    wide.addEventListener?.("change", measure);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      wide.removeEventListener?.("change", measure);
    };
  }, [ref, enabled]);
  return top;
}

/** "Desktop only" / "Mobile only" from the section's visibility settings. */
const deviceClass = (section) =>
  section.devices === "desktop"
    ? "hidden lg:block"
    : section.devices === "mobile"
      ? "lg:hidden"
      : undefined;

/** A sidebar block: a small serif heading on a rule, then its content. */
function Block({ section, heading, label, children }) {
  const id = `sidebar-${section.key}-heading`;
  return (
    <section
      aria-labelledby={heading ? id : undefined}
      aria-label={heading ? undefined : label}
      data-sidebar-section={section.type}
      className={deviceClass(section)}
    >
      {heading && (
        <h2 id={id} className="border-b border-charcoal/10 pb-3 text-xl font-medium text-balance">
          {heading}
        </h2>
      )}
      <div className={heading ? "mt-4" : undefined}>{children}</div>
    </section>
  );
}

function StoryList({ section, numbered = false, showImages = true, empty }) {
  const articles = section.data.articles ?? [];
  const { preview } = useSectionContext();
  if (articles.length === 0 && !preview) return null;
  const List = numbered ? "ol" : "ul";
  return (
    <Block section={section} heading={section.data.heading} label="Articles">
      {articles.length === 0 ? (
        <EmptyPreviewNote>{empty}</EmptyPreviewNote>
      ) : (
        <List className="divide-y divide-charcoal/10">
          {articles.map((article, i) => (
            <li key={article.slug} className="flex gap-4 py-4 first:pt-0 last:pb-0">
              {numbered && (
                <span
                  aria-hidden
                  className="w-8 shrink-0 font-serif text-3xl leading-none text-gold-700 tabular-nums"
                >
                  {i + 1}
                </span>
              )}
              <div className="min-w-0 flex-1">
                <ArticleCard
                  article={article}
                  variant="compact"
                  showImage={!numbered && showImages}
                />
              </div>
            </li>
          ))}
        </List>
      )}
    </Block>
  );
}

function SidebarTopics({ section }) {
  const topics = section.data.topics ?? [];
  const { preview } = useSectionContext();
  if (topics.length === 0 && !preview) return null;
  return (
    <Block section={section} heading={section.data.heading} label="Topics">
      {topics.length === 0 ? (
        <EmptyPreviewNote>No topics to show yet.</EmptyPreviewNote>
      ) : (
        <TopicLinks topics={topics} size="sm" label={section.data.heading || "Topics"} />
      )}
    </Block>
  );
}

/**
 * The Positive Reset in the sidebar. Same readiness rule as everywhere: the real double
 * opt-in form only when the backend reports sign-up as open; otherwise a plain sentence
 * (no fields, no invitation to subscribe) and the "What to expect" link.
 */
function SidebarNewsletter({ section }) {
  const { data } = section;
  const { status, isOpen } = useNewsletterStatus();
  const formBelowArticle = useContext(FormBelowArticle);
  const { pathname } = useLocation();
  const name = data.newsletter_name ?? status?.name ?? siteConfig.newsletterName;
  const tagline = status?.tagline ?? siteConfig.newsletterTagline;
  const magnet = data.lead_magnet?.available ? data.lead_magnet : null;
  const id = `sidebar-${section.key}-heading`;
  // On phones and tablets the sidebar sits below the article, right after the article's
  // own newsletter panel: leave this one to wide screens so the form isn't repeated.
  const wideOnly = formBelowArticle && isOpen && !magnet;
  if (wideOnly && section.devices === "mobile") return null;
  return (
    <section
      aria-labelledby={id}
      data-sidebar-section={section.type}
      className={cn(
        "rounded-[var(--radius-card)] bg-sage-800 p-6 text-ivory",
        wideOnly ? "hidden lg:block" : deviceClass(section),
      )}
    >
      <span className="grid size-10 place-items-center rounded-full bg-ivory/10 text-gold-300">
        <Mail aria-hidden className="size-5" />
      </span>
      {data.eyebrow && (
        <p className="mt-4 text-xs font-semibold tracking-[0.16em] text-gold-300 uppercase">
          {data.eyebrow}
        </p>
      )}
      <h2 id={id} className="mt-2 text-2xl font-medium text-ivory">
        {data.heading || name}
      </h2>
      {tagline && <p className="mt-1 font-serif text-gold-300 italic">{tagline}</p>}
      {data.description && <p className="mt-3 text-[0.95rem] text-sage-100">{data.description}</p>}
      {magnet ? (
        <LeadMagnetForm
          leadMagnet={magnet}
          showFirstName={false}
          tone="dark"
          className="mt-5 text-left"
        />
      ) : isOpen ? (
        <NewsletterSignupForm
          compact
          showFirstName={false}
          source="article"
          sourceDetail={pathname}
          tone="dark"
          emailId={formBelowArticle ? SIDEBAR_NEWSLETTER_EMAIL_ID : undefined}
          className="mx-0 mt-5"
        />
      ) : (
        <p className="mt-5 border-t border-ivory/15 pt-4 text-sm text-sage-100">
          Sign-up for {name} isn&apos;t available on the website at the moment.
        </p>
      )}
      {data.show_learn_more !== false && (
        <Link
          to={routes.newsletter}
          className="mt-5 inline-block text-sm font-semibold text-gold-300 underline-offset-4 hover:underline"
        >
          What to expect from {name}
        </Link>
      )}
    </section>
  );
}

/** A live, approved booking on a sidebar placement (nothing at all when none is live). */
function SidebarSponsored({ section }) {
  const { data } = section;
  const [creative] = liveOnly(data.creatives, useNow());
  if (!creative) return null;
  const image = creative.image || creative.logo;
  const id = `sidebar-${section.key}-heading`;
  return (
    <section
      aria-labelledby={id}
      data-sidebar-section={section.type}
      className={cn(
        "rounded-[var(--radius-card)] border border-charcoal/[0.08] bg-white/60 p-5",
        deviceClass(section),
      )}
    >
      <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <DisclosureLabel text={data.label} />
        <span>
          Sponsored by <span className="font-medium text-charcoal">{creative.sponsor}</span>
        </span>
      </p>
      {image && (
        <div className="relative mt-4 aspect-[16/9] overflow-hidden rounded-xl bg-beige">
          <ContentImage image={image} fill sizes="320px" className="object-cover" />
        </div>
      )}
      <h2 id={id} className="mt-4 text-lg leading-snug font-medium">
        {creative.headline || creative.sponsor}
      </h2>
      {creative.body && <p className="mt-2 text-sm text-muted">{creative.body}</p>}
      {creative.link && (
        <SponsoredAnchor
          href={creative.link.href}
          className="mt-4 inline-block text-sm font-semibold text-sage-700 underline underline-offset-4"
        >
          {creative.link.label}
        </SponsoredAnchor>
      )}
    </section>
  );
}

const EMPTY = {
  popular_articles: "There are no reading statistics for this period yet.",
  related_articles: "No related articles for this article.",
};

function SidebarSection({ section }) {
  switch (section.type) {
    case "popular_articles":
      return <StoryList section={section} numbered empty={EMPTY.popular_articles} />;
    case "related_articles":
      return (
        <StoryList
          section={section}
          showImages={section.data.show_images !== false}
          empty={EMPTY.related_articles}
        />
      );
    case "featured_articles":
    case "article_collection":
    case "latest_articles":
      return <StoryList section={section} empty="No published articles to show yet." />;
    case "topics_grid":
      return <SidebarTopics section={section} />;
    case "newsletter_cta":
      return <SidebarNewsletter section={section} />;
    case "sponsored_banner":
    case "brand_spotlight":
      return <SidebarSponsored section={section} />;
    default:
      return null; // types without a sidebar design are never shown here
  }
}

/**
 * The article sidebar (Admin › Article sidebar): CMS sections in the editor's order,
 * rendered compactly. Beside the article on wide screens, where it sticks below the
 * header as the article scrolls (see stickyTop) and stops at the end of the article
 * layout; below the article on phones and tablets (two columns on tablets), scrolling
 * normally. Empty sections are left out, and everything is prerendered with the article,
 * so nothing appears late or pushes the article around.
 *
 * Keyboard users: when focus moves to a sidebar link that the sticking has taken off
 * screen, the sidebar returns to its normal place until focus leaves it, so every link
 * can be reached and seen.
 */
export function ArticleSidebar({
  sections,
  preview = false,
  sticky = true,
  formBelowArticle = false,
  className,
}) {
  const items = sections ?? [];
  const inner = useRef(null);
  const [released, setReleased] = useState(false);
  const top = useStickyTop(inner, sticky && items.length > 0);
  if (items.length === 0) return null;
  const stuck = top !== null && !released;

  const onFocus = (event) => {
    if (!stuck) return;
    const rect = event.target.getBoundingClientRect();
    if (rect.top < STICKY_OFFSET - 8 || rect.bottom > window.innerHeight) {
      setReleased(true);
      requestAnimationFrame(() => event.target.scrollIntoView?.({ block: "nearest" }));
    }
  };
  const onBlur = (event) => {
    if (released && !event.currentTarget.contains(event.relatedTarget)) setReleased(false);
  };

  return (
    <aside aria-label="More to read" className={className}>
      <div
        ref={inner}
        data-sticky={stuck ? "true" : "false"}
        onFocus={onFocus}
        onBlur={onBlur}
        style={stuck ? { top: `${top}px` } : undefined}
        className={cn(
          "grid content-start gap-10 md:grid-cols-2 lg:grid-cols-1",
          stuck && "lg:sticky",
        )}
      >
        <FormBelowArticle.Provider value={formBelowArticle}>
          <SectionContext.Provider value={preview ? PREVIEW_CONTEXT : SITE_CONTEXT}>
            {items.map((section) => (
              <SidebarSection key={section.key} section={section} />
            ))}
          </SectionContext.Provider>
        </FormBelowArticle.Provider>
      </div>
    </aside>
  );
}

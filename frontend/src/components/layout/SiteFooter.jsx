import { ArrowRight, ArrowUpRight, Mail } from "lucide-react";
import { Link } from "react-router";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { cn } from "@/utils/format";
import { useNavigation } from "@/hooks/useNavigation";
import { Logo } from "./Logo";

const DEFAULT_FOOTER_TEXT =
  "Practical encouragement, mindset insights, and thoughtful personal growth resources to help you build confidence and move forward through every season of life.";
/**
 * The newsletter button text shipped as the default of "Newsletter button text" (Admin ›
 * Settings › Footer) before the footer invitation. Only that exact, unedited default (or
 * an empty value) is shown as "Explore the Newsletter"; any text an editor wrote is kept.
 */
export const LEGACY_NEWSLETTER_LABEL = "Learn about The Positive Reset";
const NEWSLETTER_BUTTON = "Explore the Newsletter";

const FOOTER_COLUMNS = {
  1: "sm:grid-cols-1",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "md:grid-cols-4",
};

const DEFAULT_COPYRIGHT = "© {year} {site_name}. All rights reserved.";

function FooterLink({
  item,
  className = "transition-colors hover:text-ivory hover:underline hover:underline-offset-4",
}) {
  if (item.external || item.href?.startsWith("https://")) {
    return (
      <a
        href={item.href}
        className={className}
        {...(item.newTab && { target: "_blank", rel: "noopener noreferrer" })}
      >
        {item.label}
        {item.newTab && <span className="sr-only"> (opens in a new tab)</span>}
      </a>
    );
  }
  return (
    <Link to={item.href} className={className}>
      {item.label}
    </Link>
  );
}

/** Copyright line from Settings ({year} and {site_name} are filled in). */
function Copyright({ template, name, year }) {
  const parts = (template || DEFAULT_COPYRIGHT).split(/(\{year\}|\{site_name\})/);
  return (
    <p>
      {parts.map((part, i) =>
        part === "{year}" ? (
          <span key={i} suppressHydrationWarning>
            {year}
          </span>
        ) : part === "{site_name}" ? (
          name
        ) : (
          part
        ),
      )}
    </p>
  );
}

/**
 * The one site footer, identical on every public page: brand text, a short invitation to
 * The Positive Reset (a link to /newsletter, never a form; the full sign-up lives on that
 * page), the CMS footer columns, and the copyright, legal and social links. Everything
 * editable comes from Admin › Navigation (footer columns, footer legal links) and Admin ›
 * Settings › Footer; nothing here depends on the page being viewed.
 */
export function SiteFooter({ site }) {
  const year = new Date().getFullYear();
  const { footer, legal } = useNavigation();
  const settings = site?.footer ?? {};
  const socialLinks = settings.show_social === false ? [] : (site?.social_links ?? []);
  const name = site?.name ?? siteConfig.name;
  const promo = settings.promo;
  const newsletterName = site?.newsletter?.name || siteConfig.newsletterName;
  const showInvitation = settings.show_newsletter_link !== false;
  const invitationLabel =
    !settings.newsletter_label || settings.newsletter_label === LEGACY_NEWSLETTER_LABEL
      ? NEWSLETTER_BUTTON
      : settings.newsletter_label;
  // The invitation already links to /newsletter; a column link to the same page would
  // repeat it, so it is left out of the columns while the invitation shows (the menu
  // itself is unchanged in the CMS).
  const columns = footer
    .map((group) => ({
      ...group,
      items: showInvitation
        ? group.items.filter((item) => item.href !== routes.newsletter)
        : group.items,
    }))
    .filter((group) => group.items.length > 0);
  // Editorial and corrections policies, only while those pages are published.
  const legalHrefs = new Set(legal.map((item) => item.href));
  const trustLinks = [site?.trust?.editorial_policy, site?.trust?.corrections_policy]
    .filter((page) => page?.path && !legalHrefs.has(page.path))
    .map((page) => ({ label: page.title, href: page.path }));
  const bottomLinks = [...legal, ...trustLinks];
  return (
    <footer className="bg-charcoal text-sand">
      <Container size="wide" className="py-16 sm:py-20">
        {promo?.text && (
          <div className="mb-12 flex flex-col gap-3 rounded-2xl border border-ivory/10 bg-ivory/[0.04] px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-ivory">{promo.text}</p>
            {promo.cta && (
              <FooterLink
                item={{
                  label: promo.cta.label,
                  href: promo.cta.href,
                  newTab: promo.cta.href.startsWith("https://"),
                }}
                className="inline-flex items-center gap-1.5 font-medium text-gold-300 underline-offset-4 hover:underline"
              />
            )}
          </div>
        )}
        <div className="grid gap-12 lg:grid-cols-[1.3fr_2fr]">
          <div className="max-w-sm">
            <Logo invert />
            <p className="mt-6 text-[0.95rem] leading-relaxed">
              {settings.text || DEFAULT_FOOTER_TEXT}
            </p>
            {showInvitation && (
              <div
                data-footer-newsletter
                className="mt-7 rounded-2xl border border-ivory/10 bg-ivory/[0.04] p-5"
              >
                <p className="font-serif text-xl text-ivory">{newsletterName}</p>
                <p className="mt-1 text-[0.95rem]">A little encouragement, every day.</p>
                <Link
                  to={routes.newsletter}
                  className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-gold-300/60 px-4 py-2 text-sm font-medium text-ivory transition-colors hover:border-gold-300 hover:bg-ivory/10"
                >
                  {invitationLabel}
                  <ArrowRight aria-hidden className="size-4" />
                </Link>
              </div>
            )}
            {settings.show_contact && site?.contact?.email && (
              <p className="mt-4">
                <a
                  href={`mailto:${site.contact.email}`}
                  className="inline-flex items-center gap-2 underline-offset-4 hover:text-ivory hover:underline"
                >
                  <Mail aria-hidden className="size-4" />
                  {site.contact.email}
                </a>
              </p>
            )}
          </div>

          <div
            data-footer-columns={columns.length}
            className={cn(
              "grid grid-cols-2 gap-x-8 gap-y-10",
              // As many equal columns as there are link groups, once there is room.
              FOOTER_COLUMNS[Math.min(columns.length, 4)],
            )}
          >
            {columns.map((group) => (
              <nav key={group.title} aria-label={group.title}>
                <h2 className="font-sans text-xs font-semibold tracking-[0.16em] text-ivory uppercase">
                  {group.title}
                </h2>
                <ul className="mt-5 space-y-3 text-[0.95rem]">
                  {group.items.map((item) => (
                    <li key={`${item.href}-${item.label}`}>
                      <FooterLink item={item} />
                    </li>
                  ))}
                </ul>
              </nav>
            ))}
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-6 border-t border-ivory/10 pt-8 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
            <Copyright template={settings.copyright} name={name} year={year} />
            {bottomLinks.length > 0 && (
              <ul aria-label="Legal" className="flex flex-wrap gap-x-5 gap-y-2">
                {bottomLinks.map((item) => (
                  <li key={`${item.href}-${item.label}`}>
                    <FooterLink item={item} />
                  </li>
                ))}
              </ul>
            )}
          </div>
          {socialLinks.length > 0 && (
            <ul aria-label="Social media" className="flex flex-wrap gap-x-6 gap-y-2">
              {socialLinks.map((link) => (
                <li key={link.platform}>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 hover:text-ivory"
                  >
                    {link.label}
                    <span className="sr-only"> (opens in a new tab)</span>
                    <ArrowUpRight aria-hidden className="size-3.5" />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Container>
    </footer>
  );
}

import { ArrowUpRight, Mail } from "lucide-react";
import { Link } from "react-router";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { useNavigation } from "@/hooks/useNavigation";
import { NewsletterSignupForm } from "@/components/newsletter/NewsletterSignupForm";
import { Logo } from "./Logo";

const DEFAULT_FOOTER_TEXT =
  "Practical encouragement, mindset insights, and thoughtful personal growth resources to help you build confidence and move forward through every season of life.";
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

export function SiteFooter({ site }) {
  const year = new Date().getFullYear();
  const { footer, legal } = useNavigation();
  const settings = site?.footer ?? {};
  const socialLinks = settings.show_social === false ? [] : (site?.social_links ?? []);
  const name = site?.name ?? siteConfig.name;
  const promo = settings.promo;
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
            {site?.newsletter?.is_open && (
              <div className="mt-6">
                <p className="font-medium text-ivory">
                  Get {site.newsletter.name ?? siteConfig.newsletterName} by email
                </p>
                <NewsletterSignupForm
                  compact
                  source="footer"
                  showFirstName={false}
                  tone="dark"
                  className="mx-0 mt-3"
                />
              </div>
            )}
            {settings.show_newsletter_link !== false && (
              <Link
                to={routes.newsletter}
                className="mt-6 inline-flex items-center gap-1.5 font-medium text-gold-300 underline-offset-4 hover:underline"
              >
                {settings.newsletter_label || `Learn about ${siteConfig.newsletterName}`}
                <ArrowUpRight aria-hidden className="size-4" />
              </Link>
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

          <div className="grid grid-cols-2 gap-10 sm:grid-cols-4">
            {footer.map((group) => (
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
            {legal.length > 0 && (
              <ul aria-label="Legal" className="flex flex-wrap gap-x-5 gap-y-2">
                {legal.map((item) => (
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

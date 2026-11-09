import { LifeBuoy } from "lucide-react";
import { CompanyHero, ContactCard, NoticePanel } from "@/components/company/CompanyUI";
import { Seo } from "@/components/seo/Seo";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { Container } from "@/components/ui/Container";
import { Skeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { contact } from "@/data/companyPages";
import { useSite } from "@/hooks/useContent";
import { webPageJsonLd } from "@/utils/structuredData";

/**
 * The built-in Contact page: one card per way to get in touch, with addresses from
 * Settings › Contact (no contact form, so nothing is collected here), social links and a
 * clearly separated note that this is not an emergency service. The "Contact page" template
 * builds the same page in the Page Builder.
 */
export function ContactPage() {
  const { data: site, isLoading } = useSite();
  const emails = {
    general: site?.contact?.email || null,
    partnerships: site?.contact?.partnerships_email || site?.contact?.email || null,
  };
  const socialLinks = site?.social_links ?? [];

  return (
    <>
      <Seo
        title={contact.seo_title}
        description={contact.meta_description}
        path={routes.contact}
        jsonLd={webPageJsonLd({ title: contact.seo_title, path: routes.contact })}
      />
      <CompanyHero
        eyebrow={contact.eyebrow}
        title={contact.title}
        intro={contact.intro}
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Contact", href: routes.contact },
        ]}
      />

      <section aria-label="Ways to reach us" className="bg-ivory py-14 sm:py-20">
        <Container size="wide">
          {isLoading ? (
            <div className="grid gap-5 md:grid-cols-3">
              {contact.cards.map((c) => (
                <Skeleton key={c.key} className="h-64 rounded-[var(--radius-card)]" />
              ))}
            </div>
          ) : (
            <ul className="grid gap-5 md:grid-cols-3">
              {contact.cards.map((card) => (
                <ContactCard
                  key={card.key}
                  icon={card.icon}
                  title={card.title}
                  text={card.text}
                  email={emails[card.email]}
                  subject={card.subject || undefined}
                  action={card.action}
                  fallback={contact.fallback}
                />
              ))}
            </ul>
          )}

          {socialLinks.length > 0 && (
            <div className="mt-10 flex flex-col gap-4 rounded-[var(--radius-card)] border border-charcoal/10 bg-cream p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
              <h2 className="text-xl font-medium">{contact.social_heading}</h2>
              <ul className="flex flex-wrap gap-3">
                {socialLinks.map((link) => (
                  <li key={link.platform}>
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={buttonStyles({ variant: "outline", size: "sm" })}
                    >
                      {link.label}
                      <span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-10">
            <NoticePanel id="support-heading" icon={LifeBuoy} title={contact.urgent.heading}>
              <p>{contact.urgent.body}</p>
            </NoticePanel>
          </div>
        </Container>
      </section>
    </>
  );
}

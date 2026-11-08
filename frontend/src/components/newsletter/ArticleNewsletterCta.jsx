import { ArrowRight, Mail } from "lucide-react";
import { useLocation } from "react-router";
import { Button } from "@/components/ui/Button";
import { siteConfig } from "@/config/site";
import { cn } from "@/utils/format";
import { SIDEBAR_NEWSLETTER_EMAIL_ID } from "./articleNewsletter";
import { NewsletterSignupForm } from "./NewsletterSignupForm";
import { useNewsletterStatus } from "./useNewsletterStatus";

/**
 * The Positive Reset at the end of an article, only while sign-ups are open (otherwise
 * nothing at all: no invitation that can't be acted on).
 *
 * One form per screen: on phones and tablets this panel carries the form (the sidebar's
 * newsletter section, below it, is left to wide screens). On wide screens, when the
 * sidebar already shows the form, this panel offers a button that takes the reader to
 * it instead of repeating the fields.
 */
export function ArticleNewsletterCta({ sidebarHasForm = false, className }) {
  const { status, isOpen } = useNewsletterStatus();
  const { pathname } = useLocation();
  if (!isOpen) return null;
  const name = status?.name ?? siteConfig.newsletterName;
  const tagline = status?.tagline ?? siteConfig.newsletterTagline;

  const goToSidebarForm = () => {
    const field = document.getElementById(SIDEBAR_NEWSLETTER_EMAIL_ID);
    if (!field) return;
    field.scrollIntoView?.({ block: "center" });
    field.focus({ preventScroll: true });
  };

  return (
    <section
      aria-labelledby="article-newsletter-heading"
      data-newsletter="article-end"
      className={cn(
        "rounded-[var(--radius-card)] bg-sage-800 px-6 py-8 text-ivory sm:px-10 sm:py-10",
        className,
      )}
    >
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-xl">
          <p className="flex items-center gap-2 text-xs font-semibold tracking-[0.16em] text-gold-300 uppercase">
            <Mail aria-hidden className="size-4" />
            Daily newsletter
          </p>
          <h2 id="article-newsletter-heading" className="mt-3 text-3xl font-medium text-ivory">
            Enjoyed this? Get {name} every day.
          </h2>
          {tagline && <p className="mt-2 font-serif text-lg text-gold-300 italic">{tagline}</p>}
          <p className="mt-3 text-sage-100">
            One thoughtful email each day to help you reset your mindset, find perspective, and keep
            moving forward.
          </p>
        </div>
        {sidebarHasForm && (
          <div data-wide-only className="hidden shrink-0 lg:block">
            <Button type="button" variant="light" onClick={goToSidebarForm}>
              Sign up for {name}
              <ArrowRight aria-hidden />
            </Button>
          </div>
        )}
      </div>
      <div className={cn("mt-6", sidebarHasForm && "lg:hidden")}>
        <NewsletterSignupForm
          source="article"
          sourceDetail={pathname}
          showFirstName
          tone="dark"
          className="mx-0 max-w-xl"
        />
      </div>
    </section>
  );
}

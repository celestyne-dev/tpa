import { ArrowRight, Mail } from "lucide-react";
import { ButtonLink } from "@/components/ui/Button";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { useNewsletterStatus } from "./useNewsletterStatus";
import { cn } from "@/utils/format";
import { LeadMagnetForm } from "./LeadMagnetForm";
import { NewsletterSignupForm } from "./NewsletterSignupForm";

const DEFAULT_DESCRIPTION =
  "One thoughtful email each day to help you reset your mindset, find perspective, and keep moving forward.";

/**
 * Newsletter presentation. It shows the real (double opt-in) signup form only when the
 * API reports that sending and consent wording are configured (the backend's readiness
 * check, read live by useNewsletterStatus). Otherwise it says plainly that sign-up isn't available
 * on the website: no form, no fields and no promise of a date, so nothing is collected
 * and no subscription is ever pretended. With a lead magnet it offers the free resource
 * instead, with subscribing as a separate choice.
 */
export function NewsletterPanel({
  source = "other",
  sourceDetail = "",
  showFirstName = true,
  leadMagnet = null,
  headingLevel: Heading = "h2",
  description = DEFAULT_DESCRIPTION,
  showLearnMore = true,
  title,
  eyebrow = "Daily newsletter",
  className,
}) {
  const { status, isOpen } = useNewsletterStatus();
  const name = status?.name ?? siteConfig.newsletterName;
  const heading = title || name;
  const tagline = status?.tagline ?? siteConfig.newsletterTagline;

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[2rem] bg-sage-800 px-6 py-14 text-center sm:px-12 sm:py-20",
        className,
      )}
    >
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -top-20 left-1/2 size-[28rem] -translate-x-1/2 rounded-full bg-sage-600/40 blur-3xl" />
        <svg viewBox="0 0 400 200" className="absolute inset-x-0 bottom-0 w-full opacity-20">
          <path d="M0 200 Q100 120 200 160 T400 130 V200 Z" className="fill-gold-300" />
        </svg>
      </div>
      <div className="relative mx-auto max-w-2xl">
        <span className="mx-auto grid size-14 place-items-center rounded-full bg-ivory/10 text-gold-300">
          <Mail aria-hidden className="size-6" />
        </span>
        {eyebrow && (
          <p className="mt-6 text-sm font-semibold tracking-[0.16em] text-gold-300 uppercase">
            {eyebrow}
          </p>
        )}
        <Heading className="mt-3 text-4xl font-medium text-ivory sm:text-5xl">{heading}</Heading>
        {tagline && <p className="mt-3 font-serif text-xl text-gold-300 italic">{tagline}</p>}
        {description && <p className="mt-5 text-lg text-sage-100">{description}</p>}

        {leadMagnet?.available ? (
          <LeadMagnetForm
            leadMagnet={leadMagnet}
            showFirstName={showFirstName}
            tone="dark"
            className="mx-auto mt-8 text-left"
          />
        ) : (
          isOpen && (
            <NewsletterSignupForm
              source={source}
              sourceDetail={sourceDetail}
              showFirstName={showFirstName}
              tone="dark"
              className="mt-8"
            />
          )
        )}

        {!isOpen && !leadMagnet?.available && (
          <p className="mx-auto mt-8 max-w-md border-t border-ivory/15 pt-6 text-[0.95rem] text-sage-100">
            Sign-up for {name} isn&apos;t available on the website at the moment.
          </p>
        )}

        {showLearnMore && (
          <ButtonLink to={routes.newsletter} variant="light" className="mt-8">
            What to expect
            <ArrowRight aria-hidden />
          </ButtonLink>
        )}
      </div>
    </div>
  );
}

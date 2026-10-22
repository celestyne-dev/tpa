import { ArrowRight, Mail } from "lucide-react";
import { ButtonLink } from "@/components/ui/Button";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { useSite } from "@/hooks/useContent";
import { cn } from "@/utils/format";

const DEFAULT_DESCRIPTION =
  "One thoughtful email each week to help you reset your mindset, find perspective, and keep moving forward.";

/**
 * Newsletter presentation. Until a real email provider is integrated
 * (site.newsletter.is_open from the API), it shows an honest coming-soon
 * state and never collects addresses.
 */
export function NewsletterPanel({
  headingLevel: Heading = "h2",
  description = DEFAULT_DESCRIPTION,
  showLearnMore = true,
  className,
}) {
  const { data: site } = useSite();
  const name = site?.newsletter?.name ?? siteConfig.newsletterName;
  const isOpen = site?.newsletter?.is_open === true;

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
        <p className="mt-6 text-sm font-semibold tracking-[0.16em] text-gold-300 uppercase">
          Weekly newsletter
        </p>
        <Heading className="mt-3 text-4xl font-medium text-ivory sm:text-5xl">{name}</Heading>
        <p className="mt-5 text-lg text-sage-100">{description}</p>

        {!isOpen && (
          <div className="mx-auto mt-8 max-w-lg rounded-2xl border border-ivory/15 bg-ivory/5 px-6 py-5">
            <p className="font-medium text-ivory">Sign-ups are opening soon.</p>
            <p className="mt-1 text-[0.95rem] text-sage-100">
              We are preparing the first issues of {name}. Please check back shortly. Subscription
              will be available right here once it is live.
            </p>
          </div>
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

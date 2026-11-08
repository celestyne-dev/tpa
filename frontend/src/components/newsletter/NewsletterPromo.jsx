import { ArrowRight } from "lucide-react";
import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";
import { useNewsletterStatus } from "./useNewsletterStatus";

/**
 * A compact invitation to The Positive Reset for discovery pages such as /articles: a short
 * line of copy and one link to /newsletter, where the full sign-up form lives. No fields,
 * no consent and no submission here, so it can't duplicate or bypass the sign-up flow.
 * `className` sets the band around it (background and spacing). Hidden while sign-up is
 * closed, so it never invites people to a form that isn't there.
 */
export function NewsletterPromo({ id = "newsletter-promo", className }) {
  const { isOpen } = useNewsletterStatus();
  if (!isOpen) return null;
  const headingId = `${id}-heading`;
  return (
    <aside aria-labelledby={headingId} className={className}>
      <Container size="wide">
        <div
          data-newsletter-promo
          className={cn(
            "flex flex-col gap-5 rounded-[1.75rem] bg-sage-800 px-6 py-7 sm:px-10 sm:py-8",
            "md:flex-row md:items-center md:justify-between md:gap-10",
          )}
        >
          <div className="min-w-0">
            <p className="text-xs font-semibold tracking-[0.16em] text-gold-300 uppercase">
              The Positive Reset
            </p>
            <h2
              id={headingId}
              className="mt-2 text-2xl font-medium text-balance text-ivory sm:text-3xl"
            >
              A Little Encouragement, Every Day.
            </h2>
            <p className="mt-2 text-sage-100">
              Fresh perspectives and practical inspiration, delivered daily.
            </p>
          </div>
          <ButtonLink
            to={routes.newsletter}
            variant="light"
            className="shrink-0 self-start md:self-auto"
          >
            Join the Newsletter
            <ArrowRight aria-hidden />
          </ButtonLink>
        </div>
      </Container>
    </aside>
  );
}

import { ArrowRight, Check } from "lucide-react";
import { NewsletterSignupForm } from "@/components/newsletter/NewsletterSignupForm";
import { useNewsletterStatus } from "@/components/newsletter/useNewsletterStatus";
import { Seo } from "@/components/seo/Seo";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Container } from "@/components/ui/Container";
import { buttonStyles } from "@/components/ui/buttonStyles";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { dailyResetExample, newsletterReceive } from "@/data/marketing";

const EMAIL_ID = "newsletter-email";

/**
 * The Positive Reset landing page. There is exactly one sign-up form on this page (in the
 * hero; the footer form is hidden here): the shared NewsletterSignupForm, so validation,
 * consent wording and version, bot traps, rate limits and the collection-only mode behave
 * exactly as everywhere else. It renders only while the backend reports sign-ups open;
 * otherwise the page says plainly that sign-up isn't available.
 */
export function NewsletterPage() {
  const { status, isOpen } = useNewsletterStatus();
  const name = status?.name ?? siteConfig.newsletterName;
  const tagline = status?.tagline ?? siteConfig.newsletterTagline;

  return (
    <>
      <Seo
        title="The Positive Reset — Daily Newsletter"
        description="The Positive Reset is Think Positive Always' daily email: one thoughtful message to help you reset your mindset, find perspective, and keep moving forward."
        path={routes.newsletter}
      />
      <Hero name={name} tagline={tagline} isOpen={isOpen} />
      <Receive />
      <Glimpse />
      <Closing name={name} isOpen={isOpen} />
    </>
  );
}

function Hero({ name, tagline, isOpen }) {
  return (
    <header className="border-b border-charcoal/[0.08] bg-cream">
      <Container size="wide" className="py-10 sm:py-14 lg:py-16">
        <Breadcrumbs
          items={[
            { name: "Home", href: routes.home },
            { name: "Newsletter", href: routes.newsletter },
          ]}
          className="mb-8 lg:mb-10"
        />
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center lg:gap-16">
          <div className="min-w-0">
            <p className="mb-3 text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase">
              Daily newsletter
            </p>
            <h1 className="text-4xl leading-[1.1] font-medium text-balance sm:text-5xl lg:text-[3.5rem]">
              {name}
            </h1>
            <div aria-hidden className="mt-5 h-0.5 w-14 rounded-full bg-gold-400" />
            {tagline && <p className="mt-5 font-serif text-2xl text-sage-800 italic">{tagline}</p>}
            <p className="mt-4 max-w-xl text-lg text-muted sm:text-xl">
              One thoughtful email each day to help you reset your mindset, find perspective, and
              keep moving forward. Short enough to read with your morning coffee.
            </p>
            <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-[0.95rem] text-ink">
              {["Daily", "Free", "Unsubscribe at any time"].map((item) => (
                <li key={item} className="inline-flex items-center gap-2">
                  <Check aria-hidden className="size-4 text-sage-700" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div
            id="subscribe"
            className="min-w-0 rounded-[1.75rem] border border-t-4 border-charcoal/10 border-t-sage-700 bg-ivory p-6 shadow-soft sm:p-8"
          >
            <h2 className="text-2xl font-medium">Join {name}</h2>
            <p className="mt-2 text-muted">Add your email below. Your first name is optional.</p>
            {isOpen ? (
              <NewsletterSignupForm
                source="newsletter_page"
                tone="light"
                align="start"
                emailId={EMAIL_ID}
                className="mt-6"
              />
            ) : (
              <p className="mt-6 border-l-2 border-sage-700/40 pl-4 text-[0.95rem] text-muted">
                Sign-up for {name} isn&apos;t available on the website at the moment.
              </p>
            )}
          </div>
        </div>
      </Container>
    </header>
  );
}

function SectionTitle({ id, eyebrow, title, children }) {
  return (
    <div className="max-w-2xl">
      <p className="mb-2 text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase">
        {eyebrow}
      </p>
      <h2 id={id} className="text-3xl font-medium text-balance sm:text-4xl">
        {title}
      </h2>
      <div aria-hidden className="mt-4 h-0.5 w-12 rounded-full bg-gold-400" />
      {children && <p className="mt-4 text-lg text-muted">{children}</p>}
    </div>
  );
}

function Receive() {
  return (
    <section aria-labelledby="receive-heading" className="bg-ivory py-16 sm:py-20">
      <Container size="wide">
        <SectionTitle id="receive-heading" eyebrow="Every day" title="What You'll Receive">
          Each email brings a few minutes of perspective you can carry into the rest of your day.
        </SectionTitle>
        <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {newsletterReceive.map(({ icon: Icon, title, text }) => (
            <li
              key={title}
              className="rounded-[var(--radius-card)] border border-charcoal/10 bg-white/60 p-6"
            >
              <span
                aria-hidden
                className="grid size-11 place-items-center rounded-full bg-sage-800 text-gold-300"
              >
                <Icon className="size-5" />
              </span>
              <h3 className="mt-5 text-xl font-medium">{title}</h3>
              <p className="mt-2 text-muted">{text}</p>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}

function Glimpse() {
  return (
    <section
      aria-labelledby="glimpse-heading"
      className="border-y border-charcoal/[0.08] bg-cream py-16 sm:py-20"
    >
      <Container
        size="wide"
        className="grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-16"
      >
        <SectionTitle
          id="glimpse-heading"
          eyebrow="Inside each email"
          title="A Glimpse Into Your Daily Reset"
        >
          Every email follows a simple, calm rhythm. The example here shows the format; it is
          illustrative, not a past issue.
        </SectionTitle>
        <figure className="min-w-0 rounded-[1.75rem] border border-charcoal/10 bg-ivory shadow-soft">
          <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-charcoal/10 px-6 py-4 sm:px-8">
            <span className="font-serif text-lg text-charcoal">{siteConfig.newsletterName}</span>
            <span className="text-sm text-muted">Example of the format</span>
          </figcaption>
          <dl className="divide-y divide-charcoal/[0.08] px-6 sm:px-8">
            {dailyResetExample.map(({ label, text }) => (
              <div key={label} className="py-5">
                <dt className="text-xs font-semibold tracking-[0.14em] text-gold-700 uppercase">
                  {label}
                </dt>
                <dd className="mt-2 font-serif text-lg leading-relaxed text-charcoal">{text}</dd>
              </div>
            ))}
          </dl>
        </figure>
      </Container>
    </section>
  );
}

function Closing({ name, isOpen }) {
  const toForm = (event) => {
    const email = document.getElementById(EMAIL_ID);
    if (!email) return; // after signing up the form is replaced; just follow the link
    event.preventDefault();
    email.focus({ preventScroll: true });
    email.scrollIntoView({ block: "center" });
  };
  return (
    <section aria-labelledby="closing-heading" className="bg-ivory py-16 sm:py-20">
      <Container size="wide">
        <div className="rounded-[1.75rem] bg-sage-800 px-6 py-10 text-center sm:px-12 sm:py-12">
          <h2
            id="closing-heading"
            className="text-3xl font-medium text-balance text-ivory sm:text-4xl"
          >
            Start your daily reset
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-lg text-sage-100">
            A few calm minutes each day can change how the rest of it feels. We&apos;ll never sell
            your address, and every email has a link to unsubscribe.
          </p>
          {isOpen ? (
            <a
              href="#subscribe"
              onClick={toForm}
              className={buttonStyles({ variant: "light", className: "mt-7" })}
            >
              Subscribe to {name}
              <ArrowRight aria-hidden />
            </a>
          ) : (
            <p className="mt-6 text-[0.95rem] text-sage-100">
              Sign-up isn&apos;t open on the website right now. Please check back soon.
            </p>
          )}
        </div>
      </Container>
    </section>
  );
}

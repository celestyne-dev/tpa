import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router";
import { Container } from "@/components/ui/Container";
import { footerNav, routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { Logo } from "./Logo";

export function SiteFooter({ socialLinks = [] }) {
  const year = new Date().getFullYear();
  return (
    <footer className="bg-charcoal text-sand">
      <Container size="wide" className="py-16 sm:py-20">
        <div className="grid gap-12 lg:grid-cols-[1.3fr_2fr]">
          <div className="max-w-sm">
            <Logo invert />
            <p className="mt-6 text-[0.95rem] leading-relaxed">
              Practical encouragement, mindset insights, and thoughtful personal growth resources to
              help you build confidence and move forward through every season of life.
            </p>
            <Link
              to={routes.newsletter}
              className="mt-6 inline-flex items-center gap-1.5 font-medium text-gold-300 underline-offset-4 hover:underline"
            >
              Learn about {siteConfig.newsletterName}
              <ArrowUpRight aria-hidden className="size-4" />
            </Link>
          </div>

          <div className="grid grid-cols-2 gap-10 sm:grid-cols-4">
            {footerNav.map((group) => (
              <nav key={group.title} aria-label={group.title}>
                <h2 className="font-sans text-xs font-semibold tracking-[0.16em] text-ivory uppercase">
                  {group.title}
                </h2>
                <ul className="mt-5 space-y-3 text-[0.95rem]">
                  {group.items.map((item) => (
                    <li key={item.href}>
                      <Link
                        to={item.href}
                        className="transition-colors hover:text-ivory hover:underline hover:underline-offset-4"
                      >
                        {item.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </nav>
            ))}
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-6 border-t border-ivory/10 pt-8 text-sm sm:flex-row sm:items-center sm:justify-between">
          <p>
            © <span suppressHydrationWarning>{year}</span> {siteConfig.name}. All rights reserved.
          </p>
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

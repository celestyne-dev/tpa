import { mainNav, routes } from "@/config/navigation";
import { ButtonLink } from "@/components/ui/button";
import { Container } from "@/components/ui/container";
import { Logo } from "./logo";
import { MobileNav } from "./mobile-nav";
import { NavLink } from "./nav-link";

export function SiteHeader() {
  // "Newsletter" gets a dedicated CTA on desktop; the remaining links form the main nav.
  const desktopItems = mainNav.filter((item) => item.href !== routes.newsletter);
  return (
    <header className="sticky top-0 z-40 border-b border-charcoal/[0.07] bg-ivory/90 backdrop-blur-md supports-[backdrop-filter]:bg-ivory/80">
      <Container size="wide" className="flex h-20 items-center justify-between gap-6">
        <Logo />
        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex items-center gap-6 xl:gap-8">
            {desktopItems.map((item) => (
              <li key={item.href}>
                <NavLink href={item.href}>{item.label}</NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex items-center gap-2">
          <ButtonLink href={routes.newsletter} size="sm" className="hidden lg:inline-flex">
            Newsletter
          </ButtonLink>
          <MobileNav />
        </div>
      </Container>
    </header>
  );
}

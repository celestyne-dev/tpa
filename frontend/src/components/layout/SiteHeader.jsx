import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { useNavigation } from "@/hooks/useNavigation";
import { Logo } from "./Logo";
import { MobileNav } from "./MobileNav";
import { NavItem } from "./NavItem";

export function SiteHeader() {
  // "Newsletter" gets a dedicated CTA on desktop; the rest form the main nav.
  const { primary } = useNavigation();
  const desktopItems = primary.filter((item) => item.href !== routes.newsletter);
  return (
    <header className="sticky top-0 z-40 border-b border-charcoal/[0.07] bg-ivory/90 backdrop-blur-md supports-[backdrop-filter]:bg-ivory/80">
      <Container size="wide" className="flex h-20 items-center justify-between gap-6">
        <Logo />
        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex items-center gap-6 xl:gap-8">
            {desktopItems.map((item) => (
              <li key={item.href}>
                <NavItem href={item.href} external={item.external} newTab={item.newTab}>
                  {item.label}
                </NavItem>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex items-center gap-2">
          <ButtonLink to={routes.newsletter} size="sm" className="hidden lg:inline-flex">
            Newsletter
          </ButtonLink>
          <MobileNav />
        </div>
      </Container>
    </header>
  );
}

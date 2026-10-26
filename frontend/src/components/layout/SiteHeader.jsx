import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { HeaderShopLinks } from "./HeaderShopLinks";
import { useHeaderCta } from "@/hooks/useHeaderCta";
import { useNavigation } from "@/hooks/useNavigation";
import { Logo } from "./Logo";
import { MobileNav } from "./MobileNav";
import { NavDropdown } from "./NavDropdown";
import { NavItem } from "./NavItem";

export function SiteHeader() {
  const { primary } = useNavigation();
  const cta = useHeaderCta();
  // The header button replaces a menu link to the same page on desktop.
  const desktopItems = primary.filter(
    (item) => item.visibility !== "mobile" && (!cta || item.href !== cta.href),
  );
  return (
    <header className="sticky top-0 z-40 border-b border-charcoal/[0.07] bg-ivory/90 backdrop-blur-md supports-[backdrop-filter]:bg-ivory/80">
      <Container size="wide" className="flex h-20 items-center justify-between gap-6">
        <Logo />
        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex items-center gap-6 xl:gap-8">
            {desktopItems.map((item) => (
              <li key={`${item.label}-${item.href}`}>
                {item.children ? (
                  <NavDropdown item={item} />
                ) : (
                  <NavItem href={item.href} external={item.external} newTab={item.newTab}>
                    {item.label}
                  </NavItem>
                )}
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex items-center gap-1 sm:gap-2">
          <HeaderShopLinks />
          {cta && (
            // Visibility lives on a wrapper: on the button itself "hidden" lost to the
            // button's own "inline-flex", so it showed on phones and pushed the menu off-screen.
            <span className="hidden lg:inline-flex">
              <ButtonLink to={cta.href} size="sm">
                {cta.label}
              </ButtonLink>
            </span>
          )}
          <MobileNav />
        </div>
      </Container>
    </header>
  );
}

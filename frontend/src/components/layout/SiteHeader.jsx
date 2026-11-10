import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
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
  // The header button replaces a menu link to the same page on desktop, and the logo is
  // the link home, so a "Home" menu link is left to the mobile menu.
  const desktopItems = primary.filter(
    (item) =>
      item.visibility !== "mobile" && item.href !== routes.home && (!cta || item.href !== cta.href),
  );
  return (
    <header className="sticky top-0 z-40 border-b border-charcoal/[0.07] bg-ivory/90 backdrop-blur-md supports-[backdrop-filter]:bg-ivory/80">
      <Container size="wide" className="flex h-20 items-center justify-between gap-6">
        <Logo />
        {/* Full menu from 1280px; narrower screens use the menu button, so the topic groups,
            search, account and newsletter button never crowd or wrap. */}
        <nav aria-label="Main" className="hidden xl:block">
          <ul className="flex items-center gap-5 2xl:gap-7">
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
            <span className="hidden xl:inline-flex">
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

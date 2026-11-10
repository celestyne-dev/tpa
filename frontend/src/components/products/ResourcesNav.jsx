import { NavLink } from "react-router";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { useNavigation } from "@/hooks/useNavigation";

const FALLBACK = [
  { label: "All Resources", href: routes.resources },
  { label: "Free Downloads", href: routes.freeResources },
  { label: "My Library", href: routes.accountLibrary },
];

const RESOURCE_PATHS = new Set([routes.resources, routes.freeResources]);

/**
 * The links of the header's Resources menu (Admin › Navigation), so the strip always matches
 * the menu: the server has already left out the shop while it is switched off and the
 * Recommended Books & Tools page until it is published.
 */
export function resourceLinks(primary) {
  const group = primary.find((item) =>
    item.children?.some((child) => RESOURCE_PATHS.has(child.href)),
  );
  return (group?.children ?? FALLBACK).filter((child) => !child.external);
}

/** Tabs between the Resources pages: All, Free, Premium, Recommended and My Library. */
export function ResourcesNav() {
  const { primary } = useNavigation();
  const links = resourceLinks(primary);
  if (links.length < 2) return null;
  return (
    <nav aria-label="Resource pages" className="border-b border-charcoal/[0.07] bg-ivory">
      <Container size="wide">
        <ul className="-mx-1 flex gap-1 overflow-x-auto py-2">
          {links.map((link) => (
            <li key={`${link.href}-${link.label}`} className="shrink-0">
              <NavLink
                to={link.href}
                end
                className="inline-flex min-h-11 items-center rounded-full px-4 text-sm font-medium text-ink transition-colors hover:bg-cream hover:text-sage-800 aria-[current=page]:bg-sage-700 aria-[current=page]:text-ivory"
              >
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </Container>
    </nav>
  );
}

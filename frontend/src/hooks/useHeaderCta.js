import { routes } from "@/config/navigation";
import { useSite } from "./useContent";

const DEFAULT_CTA = { label: "Newsletter", href: routes.newsletter };

/** Header button from Admin › Navigation (null when switched off). */
export function useHeaderCta() {
  const { data: site } = useSite();
  if (!site) return DEFAULT_CTA;
  return site.header ? site.header.cta : DEFAULT_CTA;
}

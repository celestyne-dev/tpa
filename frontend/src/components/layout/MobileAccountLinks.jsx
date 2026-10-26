import { useLocation, useNavigate } from "react-router";
import { routes } from "@/config/navigation";
import { useAccountStatus, useSignOut } from "@/hooks/useAccountStatus";
import { accountLinks, signInHref } from "./accountLinks";
import { NavItem } from "./NavItem";

/** Account options in the mobile menu, matching the confirmed sign-in state. */
export function MobileAccountLinks({ onNavigate }) {
  const { status, customer } = useAccountStatus();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const signOut = useSignOut();
  if (status === "unknown") return null;
  return (
    <nav aria-label="Account" className="border-t border-charcoal/[0.08] px-3 py-4 sm:px-6">
      <p className="px-4 pb-1 text-xs font-semibold tracking-[0.16em] text-sage-700 uppercase">
        {status === "signed_in"
          ? `Account · ${customer.display_name || customer.email}`
          : "Account"}
      </p>
      <ul>
        {status === "signed_in" ? (
          <>
            {accountLinks.map((l) => (
              <li key={l.to}>
                <NavItem href={l.to} variant="mobileChild" onClick={onNavigate}>
                  {l.label}
                </NavItem>
              </li>
            ))}
            <li>
              <button
                type="button"
                className="block w-full rounded-xl px-4 py-2.5 text-left text-base text-charcoal hover:bg-beige"
                onClick={() =>
                  signOut(() => {
                    onNavigate();
                    navigate(routes.home);
                  })
                }
              >
                Log out
              </button>
            </li>
          </>
        ) : (
          <>
            <li>
              <NavItem
                href={signInHref(pathname + search)}
                variant="mobileChild"
                onClick={onNavigate}
              >
                Log in
              </NavItem>
            </li>
            <li>
              <NavItem href={routes.register} variant="mobileChild" onClick={onNavigate}>
                Create account
              </NavItem>
            </li>
          </>
        )}
      </ul>
    </nav>
  );
}

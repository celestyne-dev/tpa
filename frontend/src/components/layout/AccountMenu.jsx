import { UserRound } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { routes } from "@/config/navigation";
import { useAccountStatus, useSignOut } from "@/hooks/useAccountStatus";
import { accountLinks, signInHref } from "./accountLinks";

const iconClass =
  "relative grid size-10 place-items-center rounded-full text-charcoal transition-colors hover:bg-sage-100";
const itemClass =
  "block w-full rounded-xl px-3 py-2 text-left text-[0.95rem] text-charcoal hover:bg-sage-50";

/**
 * Header account control. Before sign-in state is confirmed (prerendered HTML) it is a
 * plain link to the account area; afterwards it opens a menu with the right options.
 */
export function AccountMenu() {
  const { status, customer } = useAccountStatus();
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const ref = useRef(null);
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const signOut = useSignOut();

  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    setLastPath(pathname);
    if (open) setOpen(false);
  }

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (status === "unknown") {
    return (
      <Link to={routes.account} className={iconClass} aria-label="Your account">
        <UserRound aria-hidden className="size-5" />
      </Link>
    );
  }
  const signedIn = status === "signed_in";
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        className={iconClass}
        aria-label={signedIn ? "Account menu" : "Log in or create an account"}
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        <UserRound aria-hidden className="size-5" />
        {signedIn && (
          <span
            aria-hidden
            className="absolute right-1.5 bottom-1.5 size-2 rounded-full bg-sage-600"
          />
        )}
      </button>
      {open && (
        <div
          id={menuId}
          className="absolute right-0 z-50 mt-2 w-64 rounded-2xl border border-charcoal/10 bg-white p-2 shadow-soft"
        >
          {signedIn ? (
            <>
              <p className="px-3 pt-2 pb-1 text-sm text-muted">
                Signed in as
                <span className="block truncate font-medium text-charcoal">
                  {customer.display_name || customer.email}
                </span>
              </p>
              <ul>
                {accountLinks.map((l) => (
                  <li key={l.to}>
                    <Link to={l.to} className={itemClass}>
                      {l.label}
                    </Link>
                  </li>
                ))}
                <li className="mt-1 border-t border-charcoal/10 pt-1">
                  <button
                    type="button"
                    className={itemClass}
                    onClick={() => signOut(() => navigate(routes.home))}
                  >
                    Log out
                  </button>
                </li>
              </ul>
            </>
          ) : (
            <ul>
              <li>
                <Link to={signInHref(pathname + search)} className={itemClass}>
                  Log in
                </Link>
              </li>
              <li>
                <Link to={routes.register} className={itemClass}>
                  Create account
                </Link>
              </li>
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

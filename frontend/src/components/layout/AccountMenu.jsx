import { UserRound } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { routes } from "@/config/navigation";
import { useAccountStatus, useSignOut } from "@/hooks/useAccountStatus";
import { accountLinks, signInHref } from "./accountLinks";
import { HeaderIconLabel, headerIconClass as iconClass } from "./HeaderIconLabel";
const itemClass =
  "block w-full rounded-xl px-3 py-2 text-left text-[0.95rem] text-charcoal hover:bg-sage-50";

/**
 * Header account control: a labelled "Log in" link to /login until a customer session is
 * confirmed, then a menu with the account options.
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

  if (status !== "signed_in") {
    // One clearly labelled way in for everyone; staff switch to their own sign-in from
    // the login page. Prerendered pages show it too (signed-in visitors are sent on).
    return (
      <Link
        to={signInHref(pathname + search)}
        className="inline-flex h-10 items-center gap-1.5 rounded-full px-3 text-[0.95rem] font-medium text-charcoal transition-colors hover:bg-sage-100"
      >
        <UserRound aria-hidden className="hidden size-5 sm:block" />
        Log in
      </Link>
    );
  }
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        className={iconClass}
        aria-label="Account menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="relative">
          <UserRound aria-hidden className="size-5" />
          <span
            aria-hidden
            className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full bg-sage-600 ring-2 ring-ivory"
          />
        </span>
        <HeaderIconLabel>Account</HeaderIconLabel>
      </button>
      {open && (
        <div
          id={menuId}
          className="absolute right-0 z-50 mt-2 w-64 rounded-2xl border border-charcoal/10 bg-white p-2 shadow-soft"
        >
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
        </div>
      )}
    </div>
  );
}

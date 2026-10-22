import { Menu, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router";
import { ButtonLink } from "@/components/ui/Button";
import { routes } from "@/config/navigation";
import { useNavigation } from "@/hooks/useNavigation";
import { NavItem } from "./NavItem";

/** Accessible mobile navigation dialog: focus trap, Escape to close, focus restore, scroll lock. */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const { primary } = useNavigation();
  const { pathname } = useLocation();
  const panelId = useId();
  const triggerRef = useRef(null);
  const panelRef = useRef(null);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  // Close when the route changes (render-phase state adjustment).
  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    setLastPath(pathname);
    if (open) setOpen(false);
  }

  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel?.querySelector("a, button")?.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const focusable = panel.querySelectorAll("a[href], button:not([disabled])");
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const onResize = () => {
      if (window.matchMedia?.("(min-width: 1024px)").matches) setOpen(false);
    };

    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", onResize);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", onResize);
    };
  }, [open, close]);

  return (
    <div className="lg:hidden">
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((value) => !value)}
        className="grid size-11 place-items-center rounded-full text-charcoal transition-colors hover:bg-beige"
      >
        <Menu aria-hidden className="size-6" />
      </button>

      {open &&
        createPortal(
          <div
            ref={panelRef}
            id={panelId}
            role="dialog"
            aria-modal="true"
            aria-label="Site navigation"
            className="fixed inset-0 z-50 flex flex-col bg-ivory"
          >
            <div className="flex h-20 items-center justify-between border-b border-charcoal/[0.08] px-5 sm:px-8">
              <span className="font-serif text-xl text-charcoal">Menu</span>
              <button
                type="button"
                onClick={close}
                aria-label="Close menu"
                className="grid size-11 place-items-center rounded-full text-charcoal transition-colors hover:bg-beige"
              >
                <X aria-hidden className="size-6" />
              </button>
            </div>
            <nav aria-label="Mobile" className="flex-1 overflow-y-auto px-3 py-6 sm:px-6">
              <ul className="space-y-1">
                {primary.map((item) => (
                  <li key={item.href}>
                    <NavItem
                      href={item.href}
                      external={item.external}
                      newTab={item.newTab}
                      variant="mobile"
                      onClick={() => setOpen(false)}
                    >
                      {item.label}
                    </NavItem>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="border-t border-charcoal/[0.08] p-5 sm:px-8">
              <ButtonLink to={routes.newsletter} className="w-full" onClick={() => setOpen(false)}>
                The Positive Reset Newsletter
              </ButtonLink>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

import { ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useLocation } from "react-router";
import { cn } from "@/utils/format";
import { NavItem } from "./NavItem";

/** Disclosure-style header dropdown: button + list of links (Escape and outside click close it). */
export function NavDropdown({ item }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef(null);
  const buttonRef = useRef(null);
  const { pathname } = useLocation();
  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    setLastPath(pathname);
    if (open) setOpen(false);
  }

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onClick = (event) => {
      if (!ref.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const active = item.children.some((c) => c.href === pathname);
  return (
    <div
      ref={ref}
      className="relative"
      onBlur={(event) => {
        if (!ref.current?.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-1 py-2 text-[0.95rem] font-medium text-ink transition-colors hover:text-sage-700",
          active && "text-sage-800",
        )}
      >
        {item.label}
        <ChevronDown
          aria-hidden
          className={cn("size-4 transition-transform", open && "rotate-180")}
        />
      </button>
      <ul
        id={id}
        hidden={!open}
        className="absolute top-full left-1/2 z-50 mt-3 min-w-56 -translate-x-1/2 rounded-2xl border border-charcoal/[0.08] bg-ivory p-2 shadow-lift"
      >
        {item.children.map((child) => (
          <li key={`${child.href}-${child.label}`}>
            <NavItem
              href={child.href}
              external={child.external}
              newTab={child.newTab}
              variant="dropdown"
              onClick={() => setOpen(false)}
            >
              {child.label}
            </NavItem>
          </li>
        ))}
      </ul>
    </div>
  );
}

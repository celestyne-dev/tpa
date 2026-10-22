import { ChevronDown, ExternalLink, KeyRound, LogOut, Menu, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { LogoMark } from "@/components/layout/Logo";
import { logout, selectAuth } from "@/store/slices/authSlice";
import { cn } from "@/utils/format";
import { usePermissions } from "../hooks/usePermissions";
import { adminSections, plannedModules } from "../navigation";

function SidebarNav({ onNavigate }) {
  const { allows } = usePermissions();
  const [plannedOpen, setPlannedOpen] = useState(false);
  const [collapsed, setCollapsed] = useState({});
  return (
    <nav aria-label="Admin" className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
      {adminSections.map((section) => {
        const items = section.items.filter((item) => allows(item));
        if (!items.length) return null;
        const id = `admin-nav-${section.title.toLowerCase()}`;
        const isCollapsed = collapsed[section.title];
        return (
          <div key={section.title}>
            <button
              type="button"
              aria-expanded={!isCollapsed}
              aria-controls={id}
              onClick={() => setCollapsed((c) => ({ ...c, [section.title]: !c[section.title] }))}
              className="flex w-full items-center justify-between rounded px-2 py-1 text-[0.7rem] font-semibold tracking-[0.14em] text-sand/80 uppercase hover:text-ivory"
            >
              {section.title}
              <ChevronDown
                aria-hidden
                className={cn("size-3.5 transition-transform", isCollapsed && "-rotate-90")}
              />
            </button>
            {!isCollapsed && (
              <ul id={id} className="mt-1 space-y-0.5">
                {items.map(({ label, to, icon: Icon, end }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      end={end}
                      onClick={onNavigate}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                          isActive
                            ? "bg-ivory/10 font-medium text-ivory"
                            : "text-sand hover:bg-ivory/5 hover:text-ivory",
                        )
                      }
                    >
                      <Icon aria-hidden className="size-4" />
                      {label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
      <div>
        <button
          type="button"
          aria-expanded={plannedOpen}
          aria-controls="admin-nav-planned"
          onClick={() => setPlannedOpen((v) => !v)}
          className="flex w-full items-center justify-between rounded px-2 py-1 text-[0.7rem] font-semibold tracking-[0.14em] text-sand/80 uppercase hover:text-ivory"
        >
          Planned modules
          <ChevronDown
            aria-hidden
            className={cn("size-3.5 transition-transform", !plannedOpen && "-rotate-90")}
          />
        </button>
        {plannedOpen && (
          <ul
            id="admin-nav-planned"
            className="mt-1 space-y-0.5"
            aria-label="Planned modules (not yet available)"
          >
            {plannedModules.map(({ label, icon: Icon }) => (
              <li key={label} className="flex items-center gap-3 px-3 py-1.5 text-sm text-sand/50">
                <Icon aria-hidden className="size-4" />
                <span className="flex-1">{label}</span>
                <span className="rounded-full border border-sand/30 px-1.5 text-[0.65rem] tracking-wide uppercase">
                  Planned
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}

function SidebarBrand() {
  return (
    <Link to="/admin" className="flex items-center gap-3 px-5 py-5">
      <LogoMark className="size-8" />
      <span className="leading-tight">
        <span className="block font-serif text-ivory">Think Positive Always</span>
        <span className="text-[0.65rem] font-semibold tracking-[0.2em] text-gold-300 uppercase">
          Admin
        </span>
      </span>
    </Link>
  );
}

function MobileDrawer({ open, onClose }) {
  const panelRef = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    panel?.querySelector("a, button")?.focus();
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab" || !panel) return;
      const items = panel.querySelectorAll("a[href], button:not([disabled])");
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div aria-hidden className="absolute inset-0 bg-charcoal/50" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Admin navigation"
        className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-charcoal"
      >
        <div className="flex items-center justify-between pr-3">
          <SidebarBrand />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="rounded-full p-2 text-sand hover:text-ivory"
          >
            <X aria-hidden className="size-5" />
          </button>
        </div>
        <SidebarNav onNavigate={onClose} />
      </div>
    </div>
  );
}

function UserMenu() {
  const { user } = useSelector(selectAuth);
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const onLogout = async () => {
    await dispatch(logout());
    navigate("/admin/login", { replace: true });
  };
  return (
    <div className="flex items-center gap-2">
      <div className="hidden text-right sm:block">
        <p className="text-sm font-medium text-charcoal">{user?.display_name}</p>
        <p className="text-xs text-muted">
          {user?.roles?.map((r) => r.replace("_", " ")).join(", ")}
        </p>
      </div>
      <Link
        to="/admin/account"
        className="rounded-full p-2 text-muted hover:bg-beige hover:text-charcoal"
        aria-label="Account and password"
        title="Account"
      >
        <KeyRound aria-hidden className="size-4" />
      </Link>
      <button
        type="button"
        onClick={onLogout}
        className="inline-flex items-center gap-2 rounded-full border border-charcoal/15 px-3 py-1.5 text-sm text-charcoal hover:bg-beige"
      >
        <LogOut aria-hidden className="size-4" />
        Sign out
      </button>
    </div>
  );
}

export function AdminLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { pathname } = useLocation();
  const mainRef = useRef(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo?.(0, 0);
  }, [pathname]);

  return (
    <div className="flex min-h-dvh bg-ivory">
      <a
        href="#admin-main"
        className="sr-only z-[60] rounded-full bg-charcoal px-5 py-3 text-ivory focus:not-sr-only focus:fixed focus:top-4 focus:left-4"
      >
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col bg-charcoal lg:flex">
        <SidebarBrand />
        <SidebarNav />
        <a
          href="/"
          target="_blank"
          rel="noopener noreferrer"
          className="m-3 flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-sand hover:bg-ivory/5 hover:text-ivory"
        >
          <ExternalLink aria-hidden className="size-4" />
          View website<span className="sr-only"> (opens in a new tab)</span>
        </a>
      </aside>
      <MobileDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b border-charcoal/10 bg-ivory/95 px-4 backdrop-blur sm:px-6">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open admin navigation"
            aria-expanded={drawerOpen}
            className="rounded-full p-2 text-charcoal hover:bg-beige lg:hidden"
          >
            <Menu aria-hidden className="size-5" />
          </button>
          <span className="font-serif text-lg text-charcoal lg:hidden">TPA Admin</span>
          <div className="ml-auto">
            <UserMenu />
          </div>
        </header>
        <main
          ref={mainRef}
          id="admin-main"
          tabIndex={-1}
          className="flex-1 px-4 py-6 focus:outline-none sm:px-6 lg:px-10 lg:py-8"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}

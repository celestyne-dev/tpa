import { NavLink, useNavigate } from "react-router";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { useSignOut } from "@/hooks/useAccountStatus";
import { cn } from "@/utils/format";

const tabs = [
  { to: routes.account, label: "Overview", end: true },
  { to: routes.accountLibrary, label: "My library" },
  { to: routes.accountOrders, label: "Orders" },
  { to: routes.accountSettings, label: "Settings" },
];

/** Shared layout for the signed-in customer area (never indexed). */
export function AccountShell({ title, path, children }) {
  const navigate = useNavigate();
  const logOut = useSignOut();
  const signOut = () => logOut(() => navigate(routes.home));
  return (
    <>
      <Seo title={title} path={path} noIndex />
      <div className="bg-cream">
        <Container size="wide" className="pt-10 pb-6 sm:pt-14">
          <p className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
            Your account
          </p>
          <h1 className="mt-3 text-4xl font-medium">{title}</h1>
          <nav aria-label="Account" className="mt-8 -mb-px flex flex-wrap gap-1">
            {tabs.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                end={tab.end}
                className={({ isActive }) =>
                  cn(
                    "rounded-t-xl px-4 py-2.5 text-sm font-medium",
                    isActive ? "bg-ivory text-charcoal" : "text-muted hover:text-charcoal",
                  )
                }
              >
                {tab.label}
              </NavLink>
            ))}
            <button
              type="button"
              onClick={signOut}
              className="ml-auto rounded-t-xl px-4 py-2.5 text-sm font-medium text-muted hover:text-charcoal"
            >
              Log out
            </button>
          </nav>
        </Container>
      </div>
      <Container size="wide" className="py-12">
        {children}
      </Container>
    </>
  );
}

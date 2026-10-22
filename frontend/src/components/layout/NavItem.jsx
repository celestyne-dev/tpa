import { NavLink } from "react-router";
import { cn } from "@/utils/format";

const styles = {
  desktop:
    "relative rounded-md px-1 py-2 text-[0.95rem] font-medium text-ink transition-colors hover:text-sage-700 after:absolute after:inset-x-1 after:-bottom-0.5 after:h-0.5 after:origin-left after:scale-x-0 after:rounded-full after:bg-gold-400 after:transition-transform aria-[current=page]:text-sage-800 aria-[current=page]:after:scale-x-100",
  mobile:
    "flex items-center justify-between rounded-xl px-4 py-3.5 font-serif text-2xl text-charcoal transition-colors hover:bg-cream aria-[current=page]:bg-sage-50 aria-[current=page]:text-sage-800",
};

/** Navigation link; React Router sets aria-current="page" on the active route. */
export function NavItem({ href, variant = "desktop", className, children, ...props }) {
  return (
    <NavLink to={href} end={href === "/"} className={cn(styles[variant], className)} {...props}>
      {children}
    </NavLink>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/utils";

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

type NavLinkProps = ComponentPropsWithoutRef<typeof Link> & {
  href: string;
  variant?: "desktop" | "mobile";
};

/** Navigation link with accessible active state (aria-current + visual indicator). */
export function NavLink({
  href,
  variant = "desktop",
  className,
  children,
  ...props
}: NavLinkProps) {
  const pathname = usePathname();
  const active = isActivePath(pathname, href);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        variant === "desktop" &&
          "relative rounded-md px-1 py-2 text-[0.95rem] font-medium text-ink transition-colors after:absolute after:inset-x-1 after:-bottom-0.5 after:h-0.5 after:origin-left after:scale-x-0 after:rounded-full after:bg-gold-400 after:transition-transform hover:text-sage-700 aria-[current=page]:text-sage-800 aria-[current=page]:after:scale-x-100",
        variant === "mobile" &&
          "flex items-center justify-between rounded-xl px-4 py-3.5 font-serif text-2xl text-charcoal transition-colors hover:bg-cream aria-[current=page]:bg-sage-50 aria-[current=page]:text-sage-800",
        className,
      )}
      {...props}
    >
      {children}
    </Link>
  );
}

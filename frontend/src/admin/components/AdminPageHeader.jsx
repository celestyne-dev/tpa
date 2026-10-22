import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { Seo } from "@/components/seo/Seo";

/** Page title, breadcrumbs and actions for admin screens (also sets a noindex title). */
export function AdminPageHeader({ title, description, breadcrumbs = [], actions }) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <Seo title={`${title} · Admin`} path="/admin" noIndex />
      <div>
        <nav aria-label="Breadcrumb" className="mb-2 text-xs text-muted">
          <ol className="flex flex-wrap items-center gap-1">
            <li>
              <Link to="/admin" className="hover:text-sage-700 hover:underline">
                Admin
              </Link>
            </li>
            {breadcrumbs.map((crumb) => (
              <li key={crumb.label} className="flex items-center gap-1">
                <ChevronRight aria-hidden className="size-3" />
                {crumb.to ? (
                  <Link to={crumb.to} className="hover:text-sage-700 hover:underline">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current="page">{crumb.label}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
        <h1 className="text-3xl font-medium">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

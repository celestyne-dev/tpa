import { ArrowRight, Compass } from "lucide-react";
import { useContext, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { Seo } from "@/components/seo/Seo";
import { HeadContext } from "@/components/seo/headContext";
import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { mainNav, routes } from "@/config/navigation";
import { createContentApi } from "@/services/contentApi";

/**
 * Old links reached through client-side navigation: follow a CMS redirect if one
 * exists. (Direct visits get a real 301/308 from the server; this is a fallback.)
 */
function useRedirectFallback() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (pathname === "/404") return undefined;
    let cancelled = false;
    createContentApi()
      .resolveRedirect(pathname)
      .then(({ data }) => {
        if (cancelled) return;
        if (data.destination.startsWith("/")) navigate(data.destination, { replace: true });
        else window.location.replace(data.destination);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [pathname, navigate]);
}

export function NotFoundPage() {
  const collector = useContext(HeadContext);
  collector?.setStatus(404);
  useRedirectFallback();
  const suggestions = mainNav.filter((item) => item.href !== routes.home);

  return (
    <>
      <Seo title="Page not found" path="/404" noIndex />
      <Container size="narrow" className="py-20 text-center sm:py-28">
        <span className="mx-auto grid size-16 place-items-center rounded-full bg-sage-100 text-sage-700">
          <Compass aria-hidden className="size-7" />
        </span>
        <p className="mt-8 text-sm font-semibold tracking-[0.16em] text-sage-700 uppercase">
          Error 404
        </p>
        <h1 className="mt-3 text-4xl font-medium sm:text-5xl">This page took a different path</h1>
        <p className="mx-auto mt-5 max-w-lg text-lg text-muted">
          The page you are looking for may have moved or no longer exists. Every detour can lead
          somewhere good. Here are a few places to continue.
        </p>
        <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
          <ButtonLink to={routes.home}>Back to the homepage</ButtonLink>
          <ButtonLink to={routes.articles} variant="outline">
            Browse articles
          </ButtonLink>
        </div>
        <nav aria-label="Helpful links" className="mt-14 border-t border-charcoal/10 pt-10">
          <ul className="flex flex-wrap justify-center gap-x-8 gap-y-3">
            {suggestions.map((item) => (
              <li key={item.href}>
                <Link
                  to={item.href}
                  className="inline-flex items-center gap-1.5 font-medium text-sage-700 hover:underline hover:underline-offset-4"
                >
                  {item.label}
                  <ArrowRight aria-hidden className="size-4" />
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </Container>
    </>
  );
}

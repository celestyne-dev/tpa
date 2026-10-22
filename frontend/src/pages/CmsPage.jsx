import { useLocation } from "react-router";
import { SectionList } from "@/components/sections/SectionList";
import { cmsSeoProps } from "@/components/seo/pageSeo";
import { Seo } from "@/components/seo/Seo";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { usePage } from "@/hooks/useContent";
import { normalisePath } from "@/utils/pagePath";
import { NotFoundPage } from "./NotFoundPage";

function PageSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading page"
      className="mx-auto max-w-6xl space-y-6 px-5 py-20 sm:px-8"
    >
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-14 w-3/4" />
      <Skeleton className="h-5 w-2/3" />
      <Skeleton className="mt-10 h-64 w-full" />
    </div>
  );
}

/** A published CMS page (drafts are never served by the public API). */
export function CmsPage({ path }) {
  const { data: page, isLoading, isNotFound, isError, retry } = usePage(path);
  if (isNotFound) return <NotFoundPage />;
  if (isError) {
    return (
      <div className="py-20">
        <ErrorState onRetry={retry} title="We couldn't load this page" />
      </div>
    );
  }
  if (isLoading || !page) return <PageSkeleton />;
  return (
    <>
      <Seo {...cmsSeoProps(page)} />
      <SectionList page={page} />
    </>
  );
}

/** Catch-all route: a CMS page at this path, otherwise a real 404. */
export function CmsRoute() {
  const { pathname } = useLocation();
  const path = normalisePath(pathname);
  if (!path || path === "/") return <NotFoundPage />;
  return <CmsPage path={path} />;
}

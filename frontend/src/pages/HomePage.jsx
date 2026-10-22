import { SectionList } from "@/components/sections/SectionList";
import { cmsSeoProps } from "@/components/seo/pageSeo";
import { Seo } from "@/components/seo/Seo";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { usePage } from "@/hooks/useContent";

/** The homepage is a CMS page managed in Admin › Homepage (published sections only). */
export function HomePage() {
  const { data: page, isLoading, isError, retry } = usePage("/");
  return (
    <>
      <Seo {...cmsSeoProps(page, { isHome: true })} />
      {isError && (
        <div className="py-20">
          <ErrorState onRetry={retry} title="We couldn't load the homepage" />
        </div>
      )}
      {isLoading && !page && (
        <div
          role="status"
          aria-label="Loading page"
          className="mx-auto max-w-7xl space-y-6 px-5 py-24 sm:px-8"
        >
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-16 w-2/3" />
          <Skeleton className="h-16 w-1/2" />
          <Skeleton className="h-6 w-1/2" />
        </div>
      )}
      {page && <SectionList page={page} />}
    </>
  );
}

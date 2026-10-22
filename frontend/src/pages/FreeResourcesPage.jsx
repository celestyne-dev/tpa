import { ArticleGrid } from "@/components/articles/ArticleGrid";
import { Seo } from "@/components/seo/Seo";
import { Badge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { plannedFreeResources } from "@/data/marketing";
import { LATEST_QUERY } from "@/data/queries";
import { useArticles } from "@/hooks/useContent";

export function FreeResourcesPage() {
  const { data: articles, isLoading, isError, retry } = useArticles(LATEST_QUERY);
  return (
    <>
      <Seo
        title="Free Personal Growth Resources"
        description="Discover the free reflection sheets, mindset exercises, and downloadable guides Think Positive Always is preparing, plus free articles you can read today."
        path={routes.freeResources}
      />
      <PageHeader
        eyebrow="Free resources"
        title="Free Tools to Support Your Growth"
        description="Practical, encouraging resources you can use at your own pace. Our free resource library is being prepared, and you can start with our free articles today."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Free Resources", href: routes.freeResources },
        ]}
      />

      <Section aria-labelledby="planned-heading">
        <SectionHeading
          id="planned-heading"
          eyebrow="In preparation"
          title="What our free library will include"
          description="We are creating these resources now. They will appear here, ready to download, as soon as each one is complete."
        />
        <ul className="mt-12 grid gap-6 sm:grid-cols-2">
          {plannedFreeResources.map(({ icon: Icon, title, text }) => (
            <li key={title}>
              <Card className="flex h-full gap-5 p-7">
                <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-sage-100 text-sage-700">
                  <Icon aria-hidden className="size-5" />
                </span>
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="text-xl font-medium">{title}</h3>
                    <Badge tone="gold">Coming soon</Badge>
                  </div>
                  <p className="mt-2 text-muted">{text}</p>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      <Section tone="cream" aria-labelledby="read-now-heading">
        <SectionHeading
          id="read-now-heading"
          eyebrow="Available now"
          title="Start with our free articles"
          description="Every article on Think Positive Always is free to read."
          action={
            <ButtonLink to={routes.articles} variant="outline">
              All articles
            </ButtonLink>
          }
        />
        <div className="mt-10">
          {isLoading && <CardGridSkeleton count={3} />}
          {isError && <ErrorState onRetry={retry} />}
          {articles && <ArticleGrid articles={articles} />}
        </div>
      </Section>
    </>
  );
}

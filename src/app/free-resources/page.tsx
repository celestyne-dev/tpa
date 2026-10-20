import { ClipboardList, Compass, FileText, NotebookPen } from "lucide-react";
import type { Metadata } from "next";
import { ArticleGrid } from "@/components/articles/article-grid";
import { toCardData } from "@/components/articles/to-card-data";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import { routes } from "@/config/navigation";
import { getArticles } from "@/lib/content";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Free Personal Growth Resources",
  description:
    "Discover the free reflection sheets, mindset exercises, and downloadable guides Think Positive Always is preparing, plus free articles you can read today.",
  path: routes.freeResources,
});

const planned = [
  {
    icon: NotebookPen,
    title: "Reflection sheets",
    text: "Printable prompts to help you pause, process your week, and notice patterns in your thoughts and habits.",
  },
  {
    icon: Compass,
    title: "Mindset exercises",
    text: "Short, practical exercises for reframing negative thoughts, practising gratitude, and building realistic optimism.",
  },
  {
    icon: FileText,
    title: "Downloadable guides",
    text: "Concise guides on topics like starting over, setting boundaries, and building quiet confidence.",
  },
  {
    icon: ClipboardList,
    title: "Habit and goal planners",
    text: "Simple templates to help you plan intentional routines and track small steps toward meaningful goals.",
  },
];

export default async function FreeResourcesPage() {
  const articles = await getArticles({ limit: 3 });
  return (
    <>
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
          {planned.map(({ icon: Icon, title, text }) => (
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
            <ButtonLink href={routes.articles} variant="outline">
              All articles
            </ButtonLink>
          }
        />
        <ArticleGrid articles={articles.map(toCardData)} className="mt-10" />
      </Section>
    </>
  );
}

"use client";

import { SearchX } from "lucide-react";
import { useMemo, useState } from "react";
import { routes } from "@/config/navigation";
import { Button, ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";
import type { ArticleCardData } from "./article-card";
import { ArticleGrid } from "./article-grid";

interface TopicOption {
  slug: string;
  name: string;
}

/** Client-side topic filter for the article listing. */
export function ArticleFilter({
  articles,
  topics,
}: {
  articles: ArticleCardData[];
  topics: TopicOption[];
}) {
  const [active, setActive] = useState<string | null>(null);
  const filtered = useMemo(
    () => (active ? articles.filter((a) => a.topicSlug === active) : articles),
    [active, articles],
  );
  const activeTopic = topics.find((t) => t.slug === active);

  const chip = (slug: string | null, label: string) => {
    const pressed = active === slug;
    return (
      <button
        key={slug ?? "all"}
        type="button"
        aria-pressed={pressed}
        onClick={() => setActive(slug)}
        className={cn(
          "rounded-full border px-4 py-2 text-sm font-medium transition-colors",
          pressed
            ? "border-sage-700 bg-sage-700 text-ivory"
            : "border-charcoal/15 bg-white/60 text-ink hover:border-sage-600 hover:text-sage-800",
        )}
      >
        {label}
      </button>
    );
  };

  return (
    <div>
      <div role="group" aria-label="Filter articles by topic" className="flex flex-wrap gap-2.5">
        {chip(null, "All topics")}
        {topics.map((t) => chip(t.slug, t.name))}
      </div>
      <p aria-live="polite" className="mt-6 text-sm text-muted">
        {activeTopic
          ? `Showing ${filtered.length} ${filtered.length === 1 ? "article" : "articles"} in ${activeTopic.name}`
          : `Showing all ${filtered.length} articles`}
      </p>
      <div className="mt-8">
        {filtered.length > 0 ? (
          <ArticleGrid articles={filtered} />
        ) : (
          <EmptyState
            icon={SearchX}
            title="No articles in this topic yet"
            description={
              <>
                We are still writing for {activeTopic?.name ?? "this topic"}. In the meantime,
                explore our other articles or learn more about the topic.
              </>
            }
            action={
              <div className="flex flex-wrap justify-center gap-3">
                <Button onClick={() => setActive(null)}>Show all articles</Button>
                {activeTopic && (
                  <ButtonLink href={routes.topic(activeTopic.slug)} variant="outline">
                    About {activeTopic.name}
                  </ButtonLink>
                )}
              </div>
            }
          />
        )}
      </div>
    </div>
  );
}

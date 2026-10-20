import Link from "next/link";
import { routes } from "@/config/navigation";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ContentImage } from "@/components/ui/content-image";
import { cn } from "@/lib/utils";
import type { ArticleSource, ImageAsset } from "@/types";
import { ArticleMeta } from "./article-meta";

/** Minimal shape needed to render a card (safe to pass to client components). */
export interface ArticleCardData {
  slug: string;
  title: string;
  excerpt: string;
  publishedAt: string;
  readingTimeMinutes: number;
  image: ImageAsset;
  topicSlug: string;
  topicName: string;
  source: ArticleSource;
}

interface ArticleCardProps {
  article: ArticleCardData;
  variant?: "default" | "feature";
  headingLevel?: "h2" | "h3";
  priority?: boolean;
}

export function ArticleCard({
  article,
  variant = "default",
  headingLevel: Heading = "h3",
  priority = false,
}: ArticleCardProps) {
  const feature = variant === "feature";
  return (
    <Card
      interactive
      className={cn(
        "group flex h-full flex-col overflow-hidden",
        feature && "md:grid md:grid-cols-[1.15fr_1fr]",
      )}
    >
      <div
        className={cn(
          "relative overflow-hidden bg-beige",
          feature ? "aspect-[16/10] md:aspect-auto md:min-h-full" : "aspect-[16/10]",
        )}
      >
        <ContentImage
          image={article.image}
          fill
          priority={priority}
          sizes={
            feature
              ? "(min-width: 768px) 55vw, 100vw"
              : "(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
          }
          className="object-cover transition-transform duration-500 group-hover:scale-[1.03] motion-reduce:group-hover:scale-100"
        />
        {article.source === "sample" && (
          <Badge tone="dark" className="absolute top-4 left-4">
            Sample article
          </Badge>
        )}
      </div>
      <div
        className={cn("flex flex-1 flex-col p-6 sm:p-7", feature && "md:justify-center md:p-10")}
      >
        <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
          {article.topicName}
        </p>
        <Heading
          className={cn(
            "mt-3 font-medium",
            feature ? "text-2xl sm:text-3xl lg:text-4xl" : "text-xl sm:text-2xl",
          )}
        >
          <Link
            href={routes.article(article.slug)}
            className="group-hover:text-sage-800 after:absolute after:inset-0 after:rounded-[var(--radius-card)] focus-visible:outline-none focus-visible:after:outline-3 focus-visible:after:outline-offset-2 focus-visible:after:outline-sage-600"
          >
            {article.title}
          </Link>
        </Heading>
        <p className={cn("mt-3 flex-1 text-muted", feature ? "text-lg" : "line-clamp-3")}>
          {article.excerpt}
        </p>
        <ArticleMeta
          publishedAt={article.publishedAt}
          readingTimeMinutes={article.readingTimeMinutes}
          className="mt-6"
        />
      </div>
    </Card>
  );
}

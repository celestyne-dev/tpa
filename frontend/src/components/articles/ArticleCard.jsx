import { Link } from "react-router";
import { Badge } from "@/components/ui/Badge";
import { SponsoredLabel } from "./SponsoredLabel";
import { Card } from "@/components/ui/Card";
import { ContentImage, IMAGE_SIZES } from "@/components/ui/ContentImage";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";
import { ArticleMeta } from "./ArticleMeta";

const TITLE_LINK =
  "after:absolute after:inset-0 after:rounded-[var(--radius-card)] focus-visible:outline-none focus-visible:after:outline-3 focus-visible:after:outline-offset-2 focus-visible:after:outline-sage-600";

/**
 * A small horizontal story: thumbnail, topic, title and date. Used beside a lead story
 * and in topic groups. The whole row is one link (the title), so it stays one tab stop.
 */
function CompactArticleCard({ article, headingLevel: Heading = "h3", showImage = true }) {
  return (
    <article className="group relative flex gap-4">
      {showImage && (
        <div className="relative aspect-[4/3] w-28 shrink-0 overflow-hidden rounded-xl bg-beige sm:w-32">
          <ContentImage
            image={article.image}
            fill
            sizes="128px"
            className="object-cover transition-transform duration-500 group-hover:scale-[1.04] motion-reduce:group-hover:scale-100"
          />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
          {article.topic?.name ?? "Articles"}
        </p>
        <SponsoredLabel sponsorship={article.sponsorship} compact className="mt-1" />
        <Heading className="mt-1.5 text-lg leading-snug font-medium text-balance">
          <Link
            to={routes.article(article.slug)}
            className={cn("group-hover:text-sage-800", TITLE_LINK, "after:rounded-xl")}
          >
            {article.title}
          </Link>
        </Heading>
        <ArticleMeta
          publishedAt={article.published_at}
          readingTimeMinutes={article.reading_time_minutes}
          className="mt-2 text-xs"
        />
      </div>
    </article>
  );
}

/**
 * Article card.
 * - `default`: image above the text (grids).
 * - `feature`: image beside the text on wider screens.
 * - `lead`: the large lead story of an editorial front page.
 * - `compact`: a small horizontal story (beside a lead, in topic groups).
 */
export function ArticleCard({
  article,
  variant = "default",
  headingLevel: Heading = "h3",
  priority = false,
  tone = "white",
  showImage = true,
}) {
  if (variant === "compact") {
    return <CompactArticleCard article={article} headingLevel={Heading} showImage={showImage} />;
  }
  const feature = variant === "feature";
  const lead = variant === "lead";
  return (
    <Card
      interactive
      tone={tone}
      className={cn(
        "group flex h-full flex-col overflow-hidden",
        feature && "md:grid md:grid-cols-[1.15fr_1fr]",
      )}
    >
      <div
        className={cn(
          "relative overflow-hidden bg-beige",
          feature
            ? "aspect-[16/10] md:aspect-auto md:min-h-full"
            : lead
              ? "aspect-[16/10] lg:aspect-[3/2]"
              : "aspect-[16/10]",
        )}
      >
        <ContentImage
          image={article.image}
          fill
          priority={priority}
          sizes={
            feature
              ? "(min-width: 768px) 55vw, 100vw"
              : lead
                ? "(min-width: 1280px) 760px, (min-width: 1024px) 60vw, 100vw"
                : IMAGE_SIZES.card
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
        className={cn(
          "flex flex-1 flex-col p-6 sm:p-7",
          feature && "md:justify-center md:p-10",
          lead && "sm:p-8 lg:p-10",
        )}
      >
        <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
          {article.topic?.name ?? "Articles"}
        </p>
        <SponsoredLabel sponsorship={article.sponsorship} compact className="mt-2" />
        <Heading
          className={cn(
            "mt-3 font-medium text-balance",
            feature && "text-2xl sm:text-3xl lg:text-4xl",
            lead && "text-3xl leading-tight sm:text-4xl lg:text-[2.75rem]",
            !feature && !lead && "text-xl sm:text-2xl",
          )}
        >
          <Link
            to={routes.article(article.slug)}
            className={cn("group-hover:text-sage-800", TITLE_LINK)}
          >
            {article.title}
          </Link>
        </Heading>
        <p
          className={cn(
            "mt-3 flex-1 text-muted",
            feature && "text-lg",
            lead && "line-clamp-3 text-lg sm:text-xl",
            !feature && !lead && "line-clamp-3",
          )}
        >
          {article.excerpt}
        </p>
        <ArticleMeta
          publishedAt={article.published_at}
          readingTimeMinutes={article.reading_time_minutes}
          className="mt-6"
        />
      </div>
    </Card>
  );
}

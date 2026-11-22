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
            to={routes.content(article)}
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

/** The writer's name for a card; the site-name fallback for unattributed articles is left out. */
export function byline(article) {
  const author = article.author;
  return author?.name && author.slug !== "tpa" ? author.name : null;
}

/**
 * A horizontal story with its excerpt: archives, search results and author pages. The
 * thumbnail sits on the left (above on very small screens it stays a small square), and
 * the title is the one link. `title`/`excerpt` may be given as nodes (search highlights).
 */
function RowArticleCard({ article, headingLevel: Heading = "h3", title, excerpt, priority }) {
  return (
    <article className="group relative flex gap-4 sm:gap-6">
      <div className="relative aspect-square w-24 shrink-0 overflow-hidden rounded-xl bg-beige sm:aspect-[4/3] sm:w-48 lg:w-56">
        <ContentImage
          image={article.image}
          fill
          priority={priority}
          sizes="(min-width: 1024px) 224px, (min-width: 640px) 192px, 96px"
          className="object-cover transition-transform duration-500 group-hover:scale-[1.04] motion-reduce:group-hover:scale-100"
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
          {article.topic?.name ?? "Articles"}
        </p>
        <SponsoredLabel sponsorship={article.sponsorship} compact className="mt-1" />
        <Heading className="mt-1.5 text-xl leading-snug font-medium text-balance sm:text-2xl">
          <Link
            to={routes.content(article)}
            className={cn("group-hover:text-sage-800", TITLE_LINK, "after:rounded-xl")}
          >
            {title ?? article.title}
          </Link>
        </Heading>
        {article.excerpt && (
          <p className="mt-2 hidden text-muted sm:line-clamp-2">{excerpt ?? article.excerpt}</p>
        )}
        <ArticleMeta
          author={byline(article)}
          publishedAt={article.published_at}
          updatedAt={article.content_modified_at}
          readingTimeMinutes={article.reading_time_minutes}
          className="mt-3 text-xs sm:text-sm"
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
 * - `compact`: a small horizontal story (beside a lead, in topic groups, the sidebar).
 * - `row`: a horizontal story with its excerpt (archives, search, author pages).
 * - `secondary`: a picture story beside a lead (16:9 image, title, date; no excerpt).
 *
 * `density="compact"` (the homepage) keeps the picture cards short: 16:10 images, less
 * padding, titles of at most three lines, excerpts of two and the author, date and reading
 * time in a small line at the foot, so the cards in a row line up. Heights are never fixed.
 */
export function ArticleCard({
  article,
  variant = "default",
  headingLevel: Heading = "h3",
  priority = false,
  tone = "white",
  showImage = true,
  title,
  excerpt,
  density = "regular",
}) {
  if (variant === "row") {
    return (
      <RowArticleCard
        article={article}
        headingLevel={Heading}
        title={title}
        excerpt={excerpt}
        priority={priority}
      />
    );
  }
  if (variant === "compact") {
    return <CompactArticleCard article={article} headingLevel={Heading} showImage={showImage} />;
  }
  const feature = variant === "feature";
  const lead = variant === "lead";
  const secondary = variant === "secondary";
  const plain = !feature && !lead && !secondary;
  if (density === "compact") {
    return (
      <CompactDensityCard
        article={article}
        Heading={Heading}
        priority={priority}
        tone={tone}
        feature={feature}
        lead={lead}
        secondary={secondary}
        plain={plain}
      />
    );
  }
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
              : secondary
                ? "aspect-[16/9]"
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
                : secondary
                  ? "(min-width: 1280px) 440px, (min-width: 1024px) 36vw, (min-width: 640px) 50vw, 100vw"
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
          secondary && "p-5 sm:p-6",
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
            secondary && "text-xl leading-snug sm:text-[1.4rem]",
            !feature && !lead && !secondary && "text-xl sm:text-2xl",
          )}
        >
          <Link
            to={routes.content(article)}
            className={cn("group-hover:text-sage-800", TITLE_LINK)}
          >
            {article.title}
          </Link>
        </Heading>
        <p
          className={cn(
            "mt-3 flex-1 text-muted",
            secondary && "line-clamp-2 lg:hidden",
            feature && "text-lg",
            lead && "line-clamp-3 text-lg sm:text-xl",
            !feature && !lead && "line-clamp-3",
          )}
        >
          {article.excerpt}
        </p>
        <ArticleMeta
          author={byline(article)}
          publishedAt={article.published_at}
          readingTimeMinutes={article.reading_time_minutes}
          className="mt-6"
        />
      </div>
    </Card>
  );
}

/**
 * The homepage's shorter picture cards (see `density` above). On phones, grid cards and the
 * stories beside a lead turn into rows (a small square picture beside the title), so a
 * grid of six does not become a long column of large pictures; from tablets up they are
 * picture cards again.
 */
function CompactDensityCard({ article, Heading, priority, tone, feature, lead, secondary, plain }) {
  const row = plain || secondary;
  return (
    <Card
      interactive
      tone={tone}
      className={cn(
        "group flex h-full overflow-hidden",
        row ? "flex-row sm:flex-col" : "flex-col",
        feature && "md:grid md:grid-cols-[1.15fr_1fr]",
      )}
    >
      <div
        className={cn(
          "relative shrink-0 overflow-hidden bg-beige",
          row && "w-24 self-start max-sm:m-3 max-sm:rounded-xl sm:w-full",
          // Beside a lead story the picture crops are wider (16:9 lead, 2:1 stories), so the
          // two columns end at about the same height; on tablets the lead is 2:1.
          feature
            ? "aspect-[16/10] md:aspect-auto md:min-h-full"
            : secondary
              ? "aspect-square sm:aspect-[16/9] lg:aspect-[2/1]"
              : lead
                ? "aspect-[16/10] sm:aspect-[2/1] lg:aspect-[16/9]"
                : "aspect-square sm:aspect-[16/10]",
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
                ? "(min-width: 1280px) 720px, (min-width: 1024px) 60vw, 100vw"
                : secondary
                  ? "(min-width: 1280px) 440px, (min-width: 1024px) 36vw, (min-width: 640px) 50vw, 96px"
                  : `(max-width: 639px) 96px, ${IMAGE_SIZES.card}`
          }
          className="object-cover transition-transform duration-500 group-hover:scale-[1.03] motion-reduce:group-hover:scale-100"
        />
        {article.source === "sample" && (
          <Badge tone="dark" className={cn("absolute top-3 left-3", row && "max-sm:hidden")}>
            Sample article
          </Badge>
        )}
      </div>
      <div
        className={cn(
          "flex min-w-0 flex-1 flex-col",
          row ? "py-3 pr-4 sm:p-5" : "p-5",
          lead && "sm:p-6 lg:p-7",
          feature && "md:justify-center md:p-8",
        )}
      >
        <p className="text-xs font-semibold tracking-[0.14em] text-sage-700 uppercase">
          {article.topic?.name ?? "Articles"}
        </p>
        <SponsoredLabel sponsorship={article.sponsorship} compact className="mt-2" />
        <Heading
          className={cn(
            "mt-2 line-clamp-3 font-medium text-balance",
            lead && "text-2xl leading-tight sm:text-[1.75rem] lg:text-[2rem]",
            feature && "text-2xl leading-tight lg:text-3xl",
            secondary && "text-[1.0625rem] leading-snug sm:text-lg lg:text-xl",
            plain && "text-[1.0625rem] leading-snug sm:text-xl lg:text-[1.3125rem]",
          )}
        >
          <Link
            to={routes.content(article)}
            className={cn("group-hover:text-sage-800", TITLE_LINK)}
          >
            {article.title}
          </Link>
        </Heading>
        {article.excerpt && (
          <p
            className={cn(
              "mt-2 text-muted",
              lead
                ? "line-clamp-2 text-base sm:line-clamp-3 sm:text-[1.0625rem]"
                : secondary
                  ? "hidden text-[0.9375rem] leading-relaxed sm:line-clamp-2 lg:hidden"
                  : "hidden text-[0.9375rem] leading-relaxed sm:line-clamp-2",
            )}
          >
            {article.excerpt}
          </p>
        )}
        <ArticleMeta
          author={byline(article)}
          publishedAt={article.published_at}
          readingTimeMinutes={article.reading_time_minutes}
          size="card"
          className={cn("mt-auto", row ? "pt-2 sm:pt-4" : "pt-4")}
        />
      </div>
    </Card>
  );
}

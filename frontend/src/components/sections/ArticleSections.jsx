import { ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { ArticleCard } from "@/components/articles/ArticleCard";
import { ArticleMeta } from "@/components/articles/ArticleMeta";
import { TopicCard } from "@/components/topics/TopicCard";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";
import { CtaButton, Eyebrow, Heading, SectionShell } from "./primitives";
import { useSectionContext } from "./sectionContext";

const CARD_TONE = { soft: "white", outline: "outline", flat: "flat" };

/**
 * Shown only in the admin preview: on the website an empty section is left out (no
 * "coming soon" placeholders), so editors need to be told why it isn't visible.
 */
export function EmptyPreviewNote({ children }) {
  const { preview, dark } = useSectionContext();
  if (!preview) return null;
  return (
    <p
      role="note"
      className={cn(
        "rounded-2xl border border-dashed p-6 text-center text-sm",
        dark ? "border-ivory/20 text-sand" : "border-charcoal/15 text-muted",
      )}
    >
      {children} This section is hidden on the website until it has something to show.
    </p>
  );
}

/**
 * Editorial section header: serif heading on a thin rule, with an optional "view all"
 * link on the right and a short description underneath.
 */
export function EditorialHeader({ id, data, className }) {
  const { dark } = useSectionContext();
  if (!data.heading && !data.eyebrow && !data.description) return null;
  return (
    <div
      className={cn("border-b pb-4", dark ? "border-ivory/15" : "border-charcoal/10", className)}
    >
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <Eyebrow className="mb-2">{data.eyebrow}</Eyebrow>
          {data.heading && (
            <Heading id={id} size="small">
              {data.heading}
            </Heading>
          )}
        </div>
        {data.cta && <CtaButton cta={data.cta} fallback="ghost" arrow size="sm" />}
      </div>
      {data.description && (
        <p className={cn("mt-2 max-w-2xl", dark ? "text-sand" : "text-muted")}>
          {data.description}
        </p>
      )}
    </div>
  );
}

function ArticleList({ articles }) {
  const { dark } = useSectionContext();
  return (
    <ul className={cn("divide-y", dark ? "divide-ivory/10" : "divide-charcoal/10")}>
      {articles.map((a) => (
        <li key={a.slug} className="py-6">
          <p
            className={cn(
              "text-xs font-semibold tracking-[0.14em] uppercase",
              dark ? "text-gold-300" : "text-sage-700",
            )}
          >
            {a.topic?.name ?? "Articles"}
          </p>
          <h3 className="mt-2 text-2xl font-medium">
            <Link
              to={routes.article(a.slug)}
              className={cn(
                "hover:underline hover:underline-offset-4",
                dark ? "text-ivory" : "hover:text-sage-800",
              )}
            >
              {a.title}
            </Link>
          </h3>
          <p className={cn("mt-2 line-clamp-2", dark ? "text-sand" : "text-muted")}>{a.excerpt}</p>
          <ArticleMeta
            publishedAt={a.published_at}
            readingTimeMinutes={a.reading_time_minutes}
            className="mt-3"
          />
        </li>
      ))}
    </ul>
  );
}

/** One large lead story with smaller stories alongside (stacked below on phones). */
function LeadWithSide({ articles, tone }) {
  const { first, dark } = useSectionContext();
  const [lead, ...rest] = articles;
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] lg:gap-12">
      <ArticleCard article={lead} variant="lead" tone={tone} priority={first} />
      {rest.length > 0 && (
        <ul
          className={cn(
            "divide-y lg:border-l lg:pl-10",
            dark
              ? "divide-ivory/10 lg:border-ivory/10"
              : "divide-charcoal/10 lg:border-charcoal/10",
          )}
        >
          {rest.map((article) => (
            <li key={article.slug} className="py-5 first:pt-0 last:pb-0">
              <ArticleCard article={article} variant="compact" />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ArticleCollection({ articles, layout, cardStyle }) {
  const { first } = useSectionContext();
  const tone = CARD_TONE[cardStyle ?? "soft"];
  if (layout === "list") return <ArticleList articles={articles} />;
  if (layout === "lead_with_side") return <LeadWithSide articles={articles} tone={tone} />;
  if (layout === "lead_and_grid") {
    const [lead, ...rest] = articles;
    return (
      <div className="space-y-8">
        <ArticleCard article={lead} variant="feature" tone={tone} priority={first} />
        {rest.length > 0 && (
          <ul className="grid gap-8 sm:grid-cols-2">
            {rest.map((article) => (
              <li key={article.slug}>
                <ArticleCard article={article} tone={tone} />
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }
  if (layout === "carousel") {
    return (
      <ul
        className="-mx-5 flex snap-x snap-mandatory gap-6 overflow-x-auto px-5 pb-4 sm:-mx-8 sm:px-8"
        aria-label="Articles (scroll sideways for more)"
        tabIndex={0}
      >
        {articles.map((article) => (
          <li key={article.slug} className="w-[80%] shrink-0 snap-start sm:w-[45%] lg:w-[31%]">
            <ArticleCard article={article} tone={tone} />
          </li>
        ))}
      </ul>
    );
  }
  const columns =
    {
      grid_2: "sm:grid-cols-2",
      grid_3: "sm:grid-cols-2 lg:grid-cols-3",
      grid_4: "sm:grid-cols-2 lg:grid-cols-4",
    }[layout] ?? "sm:grid-cols-2 lg:grid-cols-3";
  return (
    <ul className={cn("grid gap-8", columns)}>
      {articles.map((article) => (
        <li key={article.slug}>
          <ArticleCard article={article} tone={tone} />
        </li>
      ))}
    </ul>
  );
}

function ArticleSectionBase({ section }) {
  const { data, variant, key } = section;
  const { preview } = useSectionContext();
  const articles = data.articles ?? [];
  if (articles.length === 0 && !preview) return null;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Articles">
      <EditorialHeader id={id} data={data} />
      <div className="mt-8">
        {articles.length === 0 ? (
          <EmptyPreviewNote>No published articles to show yet.</EmptyPreviewNote>
        ) : (
          <ArticleCollection
            articles={articles}
            layout={variant}
            cardStyle={section.design?.card_style}
          />
        )}
      </div>
    </SectionShell>
  );
}

export const FeaturedArticlesSection = ArticleSectionBase;
export const LatestArticlesSection = ArticleSectionBase;
export const ArticleCollectionSection = ArticleSectionBase;

/** Most-read articles: a numbered list (numbers are decorative; the list is ordered). */
function NumberedArticles({ articles }) {
  const { dark } = useSectionContext();
  return (
    <ol className="grid gap-x-12 gap-y-2 md:grid-cols-2">
      {articles.map((a, i) => (
        <li
          key={a.slug}
          className={cn(
            "flex gap-5 border-b py-5",
            dark ? "border-ivory/10" : "border-charcoal/10",
          )}
        >
          <span
            aria-hidden
            className={cn(
              "w-12 shrink-0 font-serif text-4xl leading-none tabular-nums",
              dark ? "text-gold-300" : "text-gold-700",
            )}
          >
            {String(i + 1).padStart(2, "0")}
          </span>
          <div className="min-w-0">
            <p
              className={cn(
                "text-xs font-semibold tracking-[0.14em] uppercase",
                dark ? "text-gold-300" : "text-sage-700",
              )}
            >
              {a.topic?.name ?? "Articles"}
            </p>
            <h3 className="mt-1.5 text-xl leading-snug font-medium text-balance">
              <Link
                to={routes.article(a.slug)}
                className={cn(
                  "hover:underline hover:underline-offset-4",
                  dark ? "text-ivory" : "hover:text-sage-800",
                )}
              >
                {a.title}
              </Link>
            </h3>
            <ArticleMeta
              publishedAt={a.published_at}
              readingTimeMinutes={a.reading_time_minutes}
              className="mt-2 text-xs"
            />
          </div>
        </li>
      ))}
    </ol>
  );
}

export function PopularArticlesSection({ section }) {
  const { data, variant, key } = section;
  const { preview } = useSectionContext();
  const articles = data.articles ?? [];
  if (articles.length === 0 && !preview) return null;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Popular">
      <EditorialHeader id={id} data={data} />
      <div className="mt-6">
        {articles.length === 0 ? (
          <EmptyPreviewNote>There are no reading statistics for this period yet.</EmptyPreviewNote>
        ) : variant === "grid_4" ? (
          <ArticleCollection
            articles={articles}
            layout="grid_4"
            cardStyle={section.design?.card_style}
          />
        ) : (
          <NumberedArticles articles={articles} />
        )}
      </div>
    </SectionShell>
  );
}

/** The latest articles of several topics, each under its topic's name. */
export function TopicArticlesSection({ section }) {
  const { data, variant, key, design } = section;
  const { preview, dark } = useSectionContext();
  const groups = data.groups ?? [];
  if (groups.length === 0 && !preview) return null;
  const id = `${key}-heading`;
  const tone = CARD_TONE[design?.card_style ?? "soft"];
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="By topic">
      <EditorialHeader id={id} data={data} />
      {groups.length === 0 ? (
        <div className="mt-8">
          <EmptyPreviewNote>None of these topics has published articles yet.</EmptyPreviewNote>
        </div>
      ) : (
        <div
          className={cn(
            "mt-8 grid gap-12",
            variant === "rows"
              ? ""
              : groups.length > 1 && "md:grid-cols-2 lg:grid-cols-3 lg:gap-10",
          )}
        >
          {groups.map(({ topic, articles }) => (
            <section key={topic.slug} aria-labelledby={`${key}-${topic.slug}`}>
              <div className="flex items-baseline justify-between gap-4">
                <h3 id={`${key}-${topic.slug}`} className="text-xl font-medium">
                  {topic.name}
                </h3>
                <Link
                  to={routes.topic(topic.slug)}
                  aria-label={`More in ${topic.name}`}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1 text-sm font-medium underline-offset-4 hover:underline",
                    dark ? "text-gold-300" : "text-sage-700",
                  )}
                >
                  More
                  <ArrowRight aria-hidden className="size-4" />
                </Link>
              </div>
              {variant === "rows" ? (
                <ul className="mt-5 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
                  {articles.map((article) => (
                    <li key={article.slug}>
                      <ArticleCard article={article} tone={tone} headingLevel="h4" />
                    </li>
                  ))}
                </ul>
              ) : (
                <ul
                  className={cn(
                    "mt-4 border-t",
                    dark ? "border-ivory/10" : "border-charcoal/10",
                    // A single topic spreads its stories across the row instead of one
                    // narrow column stretched over the full width.
                    groups.length === 1
                      ? "grid gap-x-10 sm:grid-cols-2 lg:grid-cols-3"
                      : cn("divide-y", dark ? "divide-ivory/10" : "divide-charcoal/10"),
                  )}
                >
                  {articles.map((article) => (
                    <li key={article.slug} className="py-4">
                      <ArticleCard article={article} variant="compact" headingLevel="h4" />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}
    </SectionShell>
  );
}

export function TopicsSection({ section }) {
  const { data, variant, key } = section;
  const { preview } = useSectionContext();
  const topics = data.topics ?? [];
  if (topics.length === 0 && !preview) return null;
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Topics">
      <EditorialHeader id={id} data={data} />
      <div className="mt-8">
        {topics.length === 0 ? (
          <EmptyPreviewNote>No topics to show yet.</EmptyPreviewNote>
        ) : (
          <ul
            className={cn(
              "grid gap-6 sm:grid-cols-2",
              variant === "cards_4" ? "lg:grid-cols-4" : "lg:grid-cols-3",
            )}
          >
            {topics.map((topic) => (
              <li key={topic.slug}>
                <TopicCard topic={topic} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </SectionShell>
  );
}

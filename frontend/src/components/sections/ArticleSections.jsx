import { Link } from "react-router";
import { ArticleCard } from "@/components/articles/ArticleCard";
import { ArticleMeta } from "@/components/articles/ArticleMeta";
import { TopicCard } from "@/components/topics/TopicCard";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";
import { CtaButton, SectionHeader, SectionShell } from "./primitives";
import { useSectionContext } from "./sectionContext";

const CARD_TONE = { soft: "white", outline: "outline", flat: "flat" };

function EmptyCollection({ children }) {
  const { dark } = useSectionContext();
  return (
    <p
      className={cn(
        "rounded-2xl border border-dashed p-8 text-center",
        dark ? "border-ivory/20 text-sand" : "border-charcoal/15 text-muted",
      )}
    >
      {children}
    </p>
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

function ArticleCollection({ articles, layout, cardStyle }) {
  const tone = CARD_TONE[cardStyle ?? "soft"];
  if (articles.length === 0) {
    return (
      <EmptyCollection>New articles are on their way. Please check back soon.</EmptyCollection>
    );
  }
  if (layout === "list") return <ArticleList articles={articles} />;
  if (layout === "lead_and_grid") {
    const [lead, ...rest] = articles;
    return (
      <div className="space-y-8">
        <ArticleCard article={lead} variant="feature" tone={tone} />
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
  const id = `${key}-heading`;
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Articles">
      <SectionHeader
        id={id}
        data={data}
        action={data.cta && <CtaButton cta={data.cta} fallback="outline" arrow />}
      />
      <div className="mt-12">
        <ArticleCollection
          articles={data.articles ?? []}
          layout={variant}
          cardStyle={section.design?.card_style}
        />
      </div>
    </SectionShell>
  );
}

export const FeaturedArticlesSection = ArticleSectionBase;
export const LatestArticlesSection = ArticleSectionBase;
export const ArticleCollectionSection = ArticleSectionBase;

export function TopicsSection({ section }) {
  const { data, variant, key } = section;
  const id = `${key}-heading`;
  const topics = data.topics ?? [];
  return (
    <SectionShell section={section} labelledBy={data.heading ? id : undefined} label="Topics">
      <SectionHeader
        id={id}
        data={data}
        action={data.cta && <CtaButton cta={data.cta} fallback="outline" arrow />}
      />
      <div className="mt-12">
        {topics.length === 0 ? (
          <EmptyCollection>Topics will appear here soon.</EmptyCollection>
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

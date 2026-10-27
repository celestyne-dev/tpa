import { GraduationCap, Search } from "lucide-react";
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { CourseCard } from "@/components/courses/CourseCard";
import { LEVEL_LABELS } from "@/components/courses/courseFormat";
import { CurrencySwitcher } from "@/components/products/CurrencySwitcher";
import { Seo } from "@/components/seo/Seo";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useCourses } from "@/hooks/useContent";
import { useDisplayCurrency } from "@/hooks/useShop";
import { breadcrumbJsonLd } from "@/utils/structuredData";

const SORTS = [
  ["featured", "Featured"],
  ["newest", "Newest"],
  ["title", "Title (A–Z)"],
  ["shortest", "Shortest first"],
];
const selectClass =
  "h-11 w-full rounded-xl border border-charcoal/15 bg-white px-3 text-[0.95rem] focus-visible:border-sage-600";

function sortCourses(list, sort) {
  const items = [...list];
  const published = (c) => c.published_at ?? "";
  if (sort === "newest") items.sort((a, b) => published(b).localeCompare(published(a)));
  else if (sort === "title") items.sort((a, b) => a.title.localeCompare(b.title));
  else if (sort === "shortest") items.sort((a, b) => a.total_minutes - b.total_minutes);
  else items.sort((a, b) => Number(b.featured) - Number(a.featured));
  return items;
}

/**
 * The public course catalogue (prerendered). Every course is written, self-paced learning;
 * filters run in the browser over the published list and are kept in the address.
 */
export function CoursesPage() {
  const { data: courses, meta, isLoading, isError, retry } = useCourses();
  const { currency, setCurrency, currencies } = useDisplayCurrency();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const topic = params.get("topic") ?? "";
  const access = ["free", "premium"].includes(params.get("access")) ? params.get("access") : "";
  const level = params.get("level") ?? "";
  const sort = params.get("sort") ?? "featured";
  const update = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true, preventScrollReset: true });
  };
  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const filtered = (courses ?? []).filter(
      (c) =>
        (!needle ||
          [c.title, c.subtitle, c.summary].some((t) => t?.toLowerCase().includes(needle))) &&
        (!category || c.category?.slug === category) &&
        (!topic || c.topics?.some((t) => t.slug === topic)) &&
        (!access || c.access_type === access) &&
        (!level || c.level === level),
    );
    return sortCourses(filtered, sort);
  }, [courses, q, category, topic, access, level, sort]);
  const filtering = Boolean(q || category || topic || access || level);
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Courses", href: routes.courses },
  ];

  return (
    <>
      <Seo
        title="Courses — Self-Paced Written Courses for Personal Growth"
        description="Self-paced, text-based Think Positive Always courses: practical lessons, exercises, reflections and worksheets you can read on any device. Free and premium courses."
        path={routes.courses}
        jsonLd={[breadcrumbJsonLd(crumbs)]}
      />
      <PageHeader
        eyebrow="Courses"
        title="Learn at your own pace"
        description="Written lessons, exercises and worksheets you can read anywhere — no videos, no schedules."
        breadcrumbs={crumbs}
      />
      <Section aria-labelledby="courses-heading">
        <h2 id="courses-heading" className="sr-only">
          Courses
        </h2>
        <form
          role="search"
          onSubmit={(e) => e.preventDefault()}
          className="grid gap-3 rounded-2xl border border-charcoal/10 bg-white p-4 sm:grid-cols-2 lg:grid-cols-6"
        >
          <label className="relative block sm:col-span-2">
            <span className="sr-only">Search courses</span>
            <Search
              aria-hidden
              className="pointer-events-none absolute top-3 left-3 size-5 text-muted"
            />
            <input
              type="search"
              value={q}
              onChange={(e) => update("q", e.target.value)}
              placeholder="Search courses"
              className={`${selectClass} pl-10`}
            />
          </label>
          {(meta.categories?.length ?? 0) > 0 && (
            <label>
              <span className="sr-only">Category</span>
              <select
                className={selectClass}
                value={category}
                onChange={(e) => update("category", e.target.value)}
              >
                <option value="">All categories</option>
                {meta.categories.map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {(meta.topics?.length ?? 0) > 0 && (
            <label>
              <span className="sr-only">Topic</span>
              <select
                className={selectClass}
                value={topic}
                onChange={(e) => update("topic", e.target.value)}
              >
                <option value="">All topics</option>
                {meta.topics.map((t) => (
                  <option key={t.slug} value={t.slug}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            <span className="sr-only">Free or premium</span>
            <select
              className={selectClass}
              value={access}
              onChange={(e) => update("access", e.target.value)}
            >
              <option value="">Free and premium</option>
              <option value="free">Free</option>
              <option value="premium">Premium</option>
            </select>
          </label>
          <label>
            <span className="sr-only">Level</span>
            <select
              className={selectClass}
              value={level}
              onChange={(e) => update("level", e.target.value)}
            >
              <option value="">Any level</option>
              {Object.entries(LEVEL_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </form>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          <p className="text-sm text-muted" aria-live="polite">
            {isLoading
              ? "Loading courses…"
              : `${visible.length} ${visible.length === 1 ? "course" : "courses"}`}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <span>Sort</span>
              <select
                className="h-10 rounded-xl border border-charcoal/15 bg-white px-3"
                value={sort}
                onChange={(e) => update("sort", e.target.value)}
              >
                {SORTS.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <CurrencySwitcher currency={currency} currencies={currencies} onChange={setCurrency} />
          </div>
        </div>
        <div className="mt-8">
          {isLoading ? (
            <CardGridSkeleton count={3} className="lg:grid-cols-3" />
          ) : isError ? (
            <ErrorState onRetry={retry} title="We couldn't load the courses" />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={GraduationCap}
              title={filtering ? "No courses match" : "No courses yet"}
              description={
                filtering
                  ? "Try a different search or clear the filters."
                  : "Our first courses are being written. Please check back soon."
              }
            />
          ) : (
            <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {visible.map((course) => (
                <li key={course.slug}>
                  <CourseCard course={course} currency={currency} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </Section>
    </>
  );
}

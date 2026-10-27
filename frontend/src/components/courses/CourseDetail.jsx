import { Award, BookOpen, Check, Clock, Eye, GraduationCap, ListChecks } from "lucide-react";
import { Link } from "react-router";
import { ArticleBody } from "@/components/articles/ArticleBody";
import { CurrencySwitcher } from "@/components/products/CurrencySwitcher";
import { PriceTag } from "@/components/products/PriceTag";
import { Seo } from "@/components/seo/Seo";
import { Badge } from "@/components/ui/Badge";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Container } from "@/components/ui/Container";
import { ContentImage } from "@/components/ui/ContentImage";
import { routes } from "@/config/navigation";
import { breadcrumbJsonLd, courseJsonLd } from "@/utils/structuredData";
import { CourseCard } from "./CourseCard";
import { CourseEnrollCta } from "./CourseEnrollCta";
import { LEVEL_LABELS, formatMinutes, isoDuration, priceable } from "./courseFormat";

function ListSection({ title, items, icon: Icon = Check }) {
  if (!items?.length) return null;
  return (
    <section aria-labelledby={`${title}-heading`} className="mt-12">
      <h2 id={`${title}-heading`} className="text-2xl font-medium">
        {title}
      </h2>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2">
        {items.map((item) => (
          <li key={item} className="flex gap-3">
            <Icon aria-hidden className="mt-1 size-5 shrink-0 text-sage-700" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A course page: marketing content and syllabus titles only (never lesson content). */
export function CourseDetail({ course, currency, currencies, onCurrency, preview = false }) {
  const crumbs = [
    { name: "Home", href: routes.home },
    { name: "Courses", href: routes.courses },
    { name: course.title, href: routes.course(course.slug) },
  ];
  const facts = [
    {
      icon: BookOpen,
      text: `${course.lesson_count} ${course.lesson_count === 1 ? "lesson" : "lessons"}`,
    },
    { icon: Clock, text: `About ${formatMinutes(course.total_minutes)} of reading` },
    { icon: GraduationCap, text: LEVEL_LABELS[course.level] ?? "All levels" },
    course.quiz_count > 0 && {
      icon: ListChecks,
      text: `${course.quiz_count} ${course.quiz_count === 1 ? "quiz" : "quizzes"}`,
    },
    course.certificate && { icon: Award, text: "Certificate of completion" },
  ].filter(Boolean);

  return (
    <>
      {!preview && (
        <Seo
          title={course.seo?.title ?? course.title}
          description={course.seo?.description ?? course.summary}
          path={routes.course(course.slug)}
          image={course.seo?.image ?? undefined}
          noIndex={course.seo?.noindex}
          jsonLd={[courseJsonLd(course, { isoDuration }), breadcrumbJsonLd(crumbs)]}
        />
      )}
      <div className="border-b border-charcoal/[0.06] bg-cream">
        <Container size="wide" className="py-10 sm:py-14">
          <Breadcrumbs items={crumbs} />
          <div className="mt-6 grid gap-10 lg:grid-cols-[1fr_22rem] lg:items-start">
            <div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={course.is_free ? "sage" : "gold"}>
                  {course.is_free ? "Free course" : "Premium course"}
                </Badge>
                {course.availability === "coming_soon" && <Badge tone="outline">Coming soon</Badge>}
                {course.category && <Badge tone="outline">{course.category.name}</Badge>}
              </div>
              <h1 className="mt-4 text-4xl font-medium sm:text-5xl">{course.title}</h1>
              {course.subtitle && <p className="mt-3 text-xl text-sage-800">{course.subtitle}</p>}
              <p className="mt-5 max-w-2xl text-lg text-muted">{course.summary}</p>
              <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-[0.95rem]">
                {facts.map(({ icon: Icon, text }) => (
                  <li key={text} className="inline-flex items-center gap-2">
                    <Icon aria-hidden className="size-5 text-sage-700" /> {text}
                  </li>
                ))}
              </ul>
              {course.author && (
                <p className="mt-6 text-sm text-muted">
                  Written by <span className="font-medium text-charcoal">{course.author.name}</span>
                </p>
              )}
            </div>
            <aside
              aria-label="Enrolment"
              className="rounded-[var(--radius-card)] border border-charcoal/10 bg-white p-6 shadow-soft"
            >
              {course.cover && (
                <div className="relative mb-5 aspect-[16/9] overflow-hidden rounded-xl">
                  <ContentImage
                    image={course.cover}
                    fill
                    priority
                    sizes="22rem"
                    className="object-cover"
                  />
                </div>
              )}
              {course.is_free ? (
                <p className="text-2xl font-semibold text-sage-800">Free</p>
              ) : (
                course.availability === "available" && (
                  <>
                    <PriceTag product={priceable(course)} currency={currency} size="lg" />
                    {currencies?.length > 1 && (
                      <div className="mt-3">
                        <CurrencySwitcher
                          currency={currency}
                          currencies={currencies}
                          onChange={onCurrency}
                        />
                      </div>
                    )}
                  </>
                )
              )}
              {course.access_days && (
                <p className="mt-2 text-sm text-muted">
                  Access for {course.access_days} days after enrolling.
                </p>
              )}
              {course.access?.label && !course.is_free && (
                <p className="mt-2 text-sm text-muted">{course.access.label}</p>
              )}
              <div className="mt-5">
                {preview ? (
                  <p className="text-sm text-muted">Preview: enrolment actions appear here.</p>
                ) : (
                  <CourseEnrollCta course={course} currency={currency} />
                )}
              </div>
            </aside>
          </div>
        </Container>
      </div>

      <Container size="wide" className="py-12">
        <div className="max-w-3xl">
          <ListSection title="What you'll learn" items={course.outcomes} />
          <ListSection title="Who this course is for" items={course.audience} />
          <ListSection title="Before you start" items={course.prerequisites} />
          {course.description?.length > 0 && (
            <section aria-labelledby="about-heading" className="mt-12">
              <h2 id="about-heading" className="text-2xl font-medium">
                About this course
              </h2>
              <div className="mt-4">
                <ArticleBody blocks={course.description} />
              </div>
            </section>
          )}
          <section aria-labelledby="syllabus-heading" className="mt-12">
            <h2 id="syllabus-heading" className="text-2xl font-medium">
              Course outline
            </h2>
            <ol className="mt-5 space-y-4">
              {course.syllabus.map((module, m) => (
                <li
                  key={`${module.title}-${m}`}
                  className="rounded-2xl border border-charcoal/10 bg-white p-5"
                >
                  <h3 className="text-lg font-medium">
                    <span className="text-sage-700">Module {m + 1}.</span> {module.title}
                  </h3>
                  {module.description && <p className="mt-1 text-muted">{module.description}</p>}
                  <ol className="mt-3 divide-y divide-charcoal/[0.06]">
                    {module.lessons.map((lesson, l) => (
                      <li
                        key={`${lesson.title}-${l}`}
                        className="flex flex-wrap items-center justify-between gap-2 py-2.5"
                      >
                        <span>
                          {lesson.title}
                          {preview && lesson.status === "draft" && (
                            <span className="ml-2 text-xs font-semibold text-gold-700 uppercase">
                              Draft
                            </span>
                          )}
                        </span>
                        <span className="flex items-center gap-3 text-sm text-muted">
                          {lesson.preview && lesson.slug && !preview && (
                            <Link
                              to={routes.learn(course.slug, lesson.slug)}
                              className="inline-flex items-center gap-1 font-medium text-sage-800 underline underline-offset-4"
                            >
                              <Eye aria-hidden className="size-4" /> Free preview
                            </Link>
                          )}
                          {formatMinutes(lesson.minutes)}
                        </span>
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
            </ol>
          </section>
          {course.certificate && (
            <section
              aria-labelledby="certificate-heading"
              className="mt-12 rounded-2xl bg-sage-50 p-6"
            >
              <h2 id="certificate-heading" className="flex items-center gap-2 text-xl font-medium">
                <Award aria-hidden className="size-5 text-sage-700" /> Certificate of completion
              </h2>
              <p className="mt-2 text-muted">
                Finish the required lessons and assessments to receive a certificate with a code
                anyone can verify. It is a Think Positive Always certificate of completion, not an
                accredited qualification.
              </p>
            </section>
          )}
          {course.author?.bio && (
            <section aria-labelledby="author-heading" className="mt-12">
              <h2 id="author-heading" className="text-2xl font-medium">
                About the author
              </h2>
              <p className="mt-3 text-muted">{course.author.bio}</p>
            </section>
          )}
        </div>
        {course.related?.length > 0 && (
          <section aria-labelledby="related-heading" className="mt-16">
            <h2 id="related-heading" className="text-2xl font-medium">
              Related courses
            </h2>
            <ul className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {course.related.map((item) => (
                <li key={item.slug}>
                  <CourseCard course={item} currency={currency} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </Container>
    </>
  );
}

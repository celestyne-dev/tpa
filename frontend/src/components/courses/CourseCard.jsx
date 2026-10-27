import { Award, BookOpen, Clock } from "lucide-react";
import { Link } from "react-router";
import { PriceTag } from "@/components/products/PriceTag";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ContentImage } from "@/components/ui/ContentImage";
import { routes } from "@/config/navigation";
import { LEVEL_LABELS, formatMinutes, priceable } from "./courseFormat";

/** Catalogue card for a published course (no lesson content, honest pricing). */
export function CourseCard({ course, currency, headingLevel: Heading = "h3" }) {
  return (
    <Card tone="white" className="group relative flex h-full flex-col overflow-hidden">
      <div className="relative aspect-[16/9] bg-cream">
        {course.cover ? (
          <ContentImage
            image={course.cover}
            fill
            sizes="(min-width: 1024px) 30vw, (min-width: 640px) 45vw, 100vw"
            className="object-cover"
          />
        ) : (
          <div className="grid size-full place-items-center bg-gradient-to-br from-sage-100 to-cream">
            <BookOpen aria-hidden className="size-10 text-sage-700" />
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col p-6">
        <div className="flex flex-wrap gap-2">
          <Badge tone={course.is_free ? "sage" : "gold"}>
            {course.is_free ? "Free" : "Premium"}
          </Badge>
          {course.availability === "coming_soon" && <Badge tone="outline">Coming soon</Badge>}
          {course.level && <Badge tone="outline">{LEVEL_LABELS[course.level]}</Badge>}
        </div>
        <Heading className="mt-4 text-xl font-medium">
          <Link
            to={routes.course(course.slug)}
            className="after:absolute after:inset-0 hover:text-sage-800 focus-visible:outline-none"
          >
            {course.title}
          </Link>
        </Heading>
        {course.subtitle && (
          <p className="mt-1 text-sm font-medium text-sage-700">{course.subtitle}</p>
        )}
        <p className="mt-3 flex-1 text-muted">{course.summary}</p>
        <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
          <span className="inline-flex items-center gap-1.5">
            <BookOpen aria-hidden className="size-4" /> {course.lesson_count}{" "}
            {course.lesson_count === 1 ? "lesson" : "lessons"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Clock aria-hidden className="size-4" /> {formatMinutes(course.total_minutes)} of
            reading
          </span>
          {course.certificate && (
            <span className="inline-flex items-center gap-1.5">
              <Award aria-hidden className="size-4" /> Certificate
            </span>
          )}
        </p>
        {!course.is_free && course.availability === "available" && (
          <PriceTag product={priceable(course)} currency={currency} className="mt-3" />
        )}
      </div>
    </Card>
  );
}

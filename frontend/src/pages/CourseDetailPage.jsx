import { useParams } from "react-router";
import { CourseDetail } from "@/components/courses/CourseDetail";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { ErrorState } from "@/components/ui/ErrorState";
import { ArticleSkeleton } from "@/components/ui/Skeleton";
import { routes } from "@/config/navigation";
import { useCourse } from "@/hooks/useContent";
import { useDisplayCurrency } from "@/hooks/useShop";
import { NotFoundPage } from "./NotFoundPage";

export function CourseDetailPage() {
  const { slug } = useParams();
  const { data: course, isLoading, isNotFound, isError, retry } = useCourse(slug);
  const { currency, setCurrency, currencies } = useDisplayCurrency();

  if (isNotFound) return <NotFoundPage />;
  if (isError)
    return (
      <Container className="py-20">
        <Seo title="Course unavailable" path={routes.course(slug)} noIndex />
        <ErrorState title="We couldn't load this course" onRetry={retry} />
      </Container>
    );
  if (isLoading || !course) return <ArticleSkeleton />;
  return (
    <CourseDetail
      course={course}
      currency={currency}
      currencies={currencies}
      onCurrency={setCurrency}
    />
  );
}

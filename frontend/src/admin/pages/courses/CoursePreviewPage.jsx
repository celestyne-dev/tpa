import { useState } from "react";
import { useParams } from "react-router";
import { CourseDetail } from "@/components/courses/CourseDetail";
import { LessonBody } from "@/components/courses/LessonBody";
import { ErrorState } from "@/components/ui/ErrorState";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { SelectField } from "../../components/Fields";
import { useAdminQuery } from "../../hooks/useAdminQuery";

/** Private preview of the course page and its lessons, drafts included (staff only). */
export function CoursePreviewPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const course = useAdminQuery(() => api.courses.get(id), [id]);
  const page = useAdminQuery(() => api.courses.preview(id), [id]);
  const [lessonId, setLessonId] = useState("");
  const lesson = useAdminQuery(
    () => (lessonId ? api.courses.lesson(id, lessonId) : Promise.resolve({ data: null })),
    [lessonId],
  );
  if (page.error || course.error) return <ErrorState title="We couldn't load the preview" />;
  if (!page.data || !course.data) return <p role="status">Loading preview…</p>;
  const lessons = course.data.modules.flatMap((m) =>
    m.lessons.map((l) => ({ value: String(l.id), label: `${m.title} → ${l.title} (${l.status})` })),
  );
  return (
    <>
      <AdminPageHeader
        title={`Preview: ${course.data.title}`}
        description="Not public. Drafts are included so you can check them before publishing."
        breadcrumbs={[
          { label: "Courses", to: "/admin/courses" },
          { label: course.data.title, to: `/admin/courses/${id}` },
          { label: "Preview" },
        ]}
      />
      <div className="overflow-hidden rounded-2xl border border-charcoal/10 bg-ivory">
        <CourseDetail
          course={page.data}
          currency="USD"
          currencies={[]}
          onCurrency={() => {}}
          preview
        />
      </div>
      <section aria-labelledby="lesson-preview" className="mt-8">
        <h2 id="lesson-preview" className="text-xl font-medium">
          Lesson preview
        </h2>
        <div className="mt-3 max-w-md">
          <SelectField
            label="Lesson"
            value={lessonId}
            onChange={(e) => setLessonId(e.target.value)}
            options={[{ value: "", label: "Choose a lesson…" }, ...lessons]}
          />
        </div>
        {lesson.data && (
          <article className="mx-auto mt-6 max-w-[68ch] rounded-2xl bg-white p-6 text-lg">
            <h3 className="text-3xl font-medium">{lesson.data.title}</h3>
            <p className="mt-1 text-sm text-muted">
              {lesson.data.reading_minutes} min read · {lesson.data.status}
            </p>
            <div className="mt-6">
              <LessonBody blocks={lesson.data.preview_body.filter((b) => b.type !== "download")} />
            </div>
            {lesson.data.body.some((b) => b.type === "download") && (
              <p className="mt-6 text-sm text-muted">
                Worksheet downloads are shown to enrolled learners only.
              </p>
            )}
          </article>
        )}
      </section>
    </>
  );
}

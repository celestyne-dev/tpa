import {
  ArrowLeft,
  ArrowRight,
  Award,
  BadgeCheck,
  BookOpen,
  CheckCircle2,
  Circle,
  Download,
  GraduationCap,
  Minus,
  Plus,
  ShieldAlert,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router";
import { AssessmentForm } from "@/components/courses/AssessmentForm";
import { formatMinutes } from "@/components/courses/courseFormat";
import { LessonBody } from "@/components/courses/LessonBody";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { routes } from "@/config/navigation";
import { useCustomer } from "@/hooks/useShop";
import { AccountShell } from "../AccountShell";
import { redirectTo } from "../hooks";
import { RequireCustomer } from "../RequireCustomer";

const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
    : "";

function ProgressBar({ percent, label = "Course progress" }) {
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="font-medium">{percent}%</span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-charcoal/10"
      >
        <div className="h-full rounded-full bg-sage-600" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

/**
 * Loads learner data (like ``useLoad``) and keeps it patchable, so saving an exercise or an
 * attempt updates the page without a reload. ``key`` names what is loaded.
 */
function useLearnerData(load, key) {
  const [state, setState] = useState({ status: "loading", data: null, error: null, version: 0 });
  const reload = useCallback(() => setState((s) => ({ ...s, version: s.version + 1 })), []);
  useEffect(() => {
    let live = true;
    Promise.resolve()
      .then(() => live && setState((s) => ({ ...s, status: "loading" })))
      .then(load)
      .then(
        (res) => live && setState((s) => ({ ...s, status: "ready", data: res.data, error: null })),
        (error) => live && setState((s) => ({ ...s, status: "error", data: null, error })),
      );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, state.version]);
  return [state, setState, reload];
}

function AccessProblem({ error, courseSlug }) {
  const code = error?.code;
  if (code === "email_verification_required") {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Confirm your email to start learning"
        description="We need to know this account's email address is yours before saving progress or opening purchased courses. Check your inbox for the confirmation link."
        action={
          <ButtonLink to={routes.accountSettings} variant="outline">
            Resend the confirmation email
          </ButtonLink>
        }
      />
    );
  }
  if (code === "not_enrolled") {
    return (
      <EmptyState
        icon={GraduationCap}
        title="You're not enrolled in this course yet"
        description="Enrol for free or buy the course on its page. Bought it as a guest? Sign in with the purchase email and confirm it — the course appears here automatically."
        action={<ButtonLink to={routes.course(courseSlug)}>See the course</ButtonLink>}
      />
    );
  }
  if (code === "course_access_ended") {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Your access to this course has ended"
        description={error.message}
        action={
          <ButtonLink to={routes.course(courseSlug)} variant="outline">
            Back to the course page
          </ButtonLink>
        }
      />
    );
  }
  if (error?.status === 404) {
    return (
      <EmptyState
        icon={BookOpen}
        title="We couldn't find that"
        description="This lesson or course isn't available."
        action={<ButtonLink to={routes.accountLearning}>My learning</ButtonLink>}
      />
    );
  }
  return <ErrorState title="We couldn't load this" />;
}

// ---- My learning (account area) ---------------------------------------------------------

function CertificateLinks({ certificate, shopApi }) {
  if (!certificate) return null;
  if (certificate.revoked) return <p className="text-sm text-muted">Certificate revoked.</p>;
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
      <a
        href={shopApi.certificatePdfUrl(certificate.code)}
        className="inline-flex items-center gap-1 font-medium text-sage-800 underline underline-offset-4"
      >
        <Download aria-hidden className="size-4" /> Download certificate (PDF)
      </a>
      <Link to={routes.certificate(certificate.code)} className="underline underline-offset-4">
        Verification page
      </Link>
    </p>
  );
}

export function AccountLearningPage() {
  return (
    <RequireCustomer>
      <AccountShell title="My learning" path={routes.accountLearning}>
        <LearningList />
      </AccountShell>
    </RequireCustomer>
  );
}

function LearningList() {
  const shopApi = useShopApi();
  const [state] = useLearnerData(() => shopApi.learning(), "learning");
  if (state.status === "loading") return <p role="status">Loading your courses…</p>;
  if (state.status === "error") return <AccessProblem error={state.error} />;
  const items = state.data.enrollments;
  if (!items.length) {
    return (
      <EmptyState
        icon={GraduationCap}
        title="No courses yet"
        description="Courses you enrol in or buy appear here, with your progress."
        action={<ButtonLink to={routes.courses}>Browse courses</ButtonLink>}
      />
    );
  }
  return (
    <ul className="grid gap-5 md:grid-cols-2">
      {items.map((item) => (
        <li
          key={item.course.slug}
          className="flex flex-col rounded-2xl border border-charcoal/10 bg-white p-6"
        >
          <h2 className="text-xl font-medium">{item.course.title}</h2>
          <p className="mt-1 text-sm text-muted">{item.course.summary}</p>
          <div className="mt-4">
            <ProgressBar
              percent={item.progress.percent}
              label={`Progress in ${item.course.title}`}
            />
          </div>
          <p className="mt-3 text-sm text-muted">
            {item.completed_at
              ? `Completed ${formatDate(item.completed_at)}`
              : item.last_activity_at
                ? `Last read ${formatDate(item.last_activity_at)}`
                : `Enrolled ${formatDate(item.enrolled_at)}`}
          </p>
          <div className="mt-4 flex flex-1 flex-col justify-end gap-3">
            {item.access === "active" ? (
              <ButtonLink
                to={
                  item.resume
                    ? routes.learn(item.course.slug, item.resume.slug)
                    : routes.learn(item.course.slug)
                }
                size="sm"
              >
                {item.completed_at ? "Review" : item.last_activity_at ? "Continue" : "Start"}
                <ArrowRight aria-hidden className="size-4" />
              </ButtonLink>
            ) : (
              <p className="rounded-xl bg-cream p-3 text-sm">
                {item.access === "expired"
                  ? "Your access period ended. "
                  : item.access === "revoked"
                    ? "This enrolment was ended. "
                    : "Your access ended (refunded or removed). "}
                <Link to={routes.course(item.course.slug)} className="underline underline-offset-4">
                  Course page
                </Link>
              </p>
            )}
            <CertificateLinks certificate={item.certificate} shopApi={shopApi} />
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---- course outline ---------------------------------------------------------------------

function LearnShell({ title, children, back }) {
  return (
    <>
      <Seo title={title} path={routes.accountLearning} noIndex />
      <div className="border-b border-charcoal/[0.06] bg-cream">
        <Container size="wide" className="py-4">
          <Link
            to={back?.to ?? routes.accountLearning}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-sage-800 underline-offset-4 hover:underline"
          >
            <ArrowLeft aria-hidden className="size-4" /> {back?.label ?? "My learning"}
          </Link>
        </Container>
      </div>
      {children}
    </>
  );
}

function CertificatePanel({ course, data, onIssued }) {
  const shopApi = useShopApi();
  const [name, setName] = useState("");
  const [state, setState] = useState({ busy: false, error: "" });
  if (!course.certificate_enabled) return null;
  if (data.certificate) {
    return (
      <section className="rounded-2xl bg-sage-50 p-6" aria-labelledby="certificate-heading">
        <h2 id="certificate-heading" className="flex items-center gap-2 text-xl font-medium">
          <Award aria-hidden className="size-6 text-sage-700" /> Your certificate
        </h2>
        <p className="mt-2 text-sm text-muted">
          Issued to {data.certificate.recipient_name} on {formatDate(data.certificate.issued_at)}.
          Certificate ID {data.certificate.code}.
        </p>
        <div className="mt-3">
          <CertificateLinks certificate={data.certificate} shopApi={shopApi} />
        </div>
      </section>
    );
  }
  if (!data.certificate_available) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <Award aria-hidden className="size-5" /> Complete the required lessons and assessments to
        receive a certificate of completion.
      </p>
    );
  }
  const request = async (event) => {
    event.preventDefault();
    setState({ busy: true, error: "" });
    try {
      await shopApi.requestCertificate(course.slug, name);
      onIssued();
    } catch (error) {
      setState({ busy: false, error: error.details?.name?.[0] ?? error.message });
    }
  };
  return (
    <form onSubmit={request} className="rounded-2xl bg-sage-50 p-6">
      <h2 className="text-xl font-medium">You've completed the course</h2>
      <label htmlFor="certificate-name" className="mt-3 block text-sm font-medium">
        Name to show on your certificate
      </label>
      <input
        id="certificate-name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="mt-1 w-full max-w-sm rounded-xl border border-charcoal/15 bg-white p-2.5"
        autoComplete="name"
      />
      {state.error && (
        <p role="alert" className="mt-2 text-sm text-red-800">
          {state.error}
        </p>
      )}
      <Button type="submit" className="mt-3" disabled={state.busy}>
        Issue my certificate
      </Button>
    </form>
  );
}

export function LearnCoursePage() {
  return (
    <RequireCustomer>
      <CourseOutline />
    </RequireCustomer>
  );
}

function CourseOutline() {
  const { courseSlug } = useParams();
  const shopApi = useShopApi();
  const [state, , reload] = useLearnerData(
    () => shopApi.learningCourse(courseSlug),
    `course:${courseSlug}`,
  );
  if (state.status === "loading")
    return (
      <Container className="py-20 text-center text-muted" role="status">
        Loading your course…
      </Container>
    );
  if (state.status === "error")
    return (
      <LearnShell title="Course">
        <Container className="py-16">
          <AccessProblem error={state.error} courseSlug={courseSlug} />
        </Container>
      </LearnShell>
    );
  const data = state.data;
  const { course } = data;
  return (
    <LearnShell title={course.title}>
      <Container size="wide" className="py-10">
        <div className="grid gap-10 lg:grid-cols-[1fr_20rem]">
          <div>
            <h1 className="text-3xl font-medium sm:text-4xl">{course.title}</h1>
            <p className="mt-2 text-muted">{course.summary}</p>
            <div className="mt-6 max-w-md">
              <ProgressBar percent={data.progress.percent} />
              <p className="mt-2 text-sm text-muted">
                {data.progress.completed_lessons} of {data.progress.required_lessons} required
                lessons
                {data.progress.required_assessments
                  ? ` · ${data.progress.completed_assessments} of ${data.progress.required_assessments} assessments`
                  : ""}
              </p>
            </div>
            {data.resume && (
              <ButtonLink to={routes.learn(course.slug, data.resume.slug)} className="mt-6">
                {data.progress.percent ? "Continue" : "Start"}: {data.resume.title}
                <ArrowRight aria-hidden className="size-4" />
              </ButtonLink>
            )}
            <nav aria-label="Course contents" className="mt-10 space-y-6">
              {data.modules.map((module, m) => (
                <section key={module.id} aria-labelledby={`module-${module.id}`}>
                  <h2
                    id={`module-${module.id}`}
                    className="flex items-center gap-2 text-xl font-medium"
                  >
                    <span className="text-sage-700">Module {m + 1}.</span> {module.title}
                    {module.completed && (
                      <CheckCircle2 aria-label="Module complete" className="size-5 text-sage-700" />
                    )}
                  </h2>
                  {module.description && <p className="mt-1 text-muted">{module.description}</p>}
                  <ol className="mt-3 divide-y divide-charcoal/[0.06] rounded-2xl border border-charcoal/10 bg-white">
                    {module.lessons.map((lesson) => (
                      <li key={lesson.slug}>
                        <Link
                          to={routes.learn(course.slug, lesson.slug)}
                          className="flex items-center gap-3 px-4 py-3 hover:bg-cream focus-visible:bg-cream"
                        >
                          {lesson.completed ? (
                            <CheckCircle2 aria-hidden className="size-5 shrink-0 text-sage-700" />
                          ) : (
                            <Circle aria-hidden className="size-5 shrink-0 text-charcoal/30" />
                          )}
                          <span className="flex-1">
                            {lesson.title}
                            <span className="sr-only">
                              {lesson.completed ? " (completed)" : ""}
                            </span>
                          </span>
                          <span className="text-sm text-muted">
                            {formatMinutes(lesson.minutes)}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ol>
                </section>
              ))}
            </nav>
          </div>
          <aside className="space-y-6">
            {data.assessments.some((a) => a.lesson_id === null) && (
              <section
                aria-labelledby="assessments-heading"
                className="rounded-2xl border border-charcoal/10 bg-white p-5"
              >
                <h2 id="assessments-heading" className="font-medium">
                  Assessments
                </h2>
                <ul className="mt-3 space-y-2">
                  {data.assessments
                    .filter((a) => a.lesson_id === null)
                    .map((a) => (
                      <li key={a.id}>
                        <Link
                          to={`/learn/${course.slug}/assessments/${a.id}`}
                          className="underline underline-offset-4"
                        >
                          {a.title}
                        </Link>{" "}
                        <span className="text-sm text-muted">
                          {a.status === "passed"
                            ? "· Passed"
                            : a.status === "failed"
                              ? "· Not passed yet"
                              : a.status === "submitted"
                                ? "· Done"
                                : a.required
                                  ? "· Required"
                                  : ""}
                        </span>
                      </li>
                    ))}
                </ul>
              </section>
            )}
            <CertificatePanel course={course} data={data} onIssued={reload} />
          </aside>
        </div>
      </Container>
    </LearnShell>
  );
}

// ---- lesson reader ----------------------------------------------------------------------

const TEXT_SIZES = ["text-base", "text-lg", "text-xl"];
const SIZE_KEY = "tpa-lesson-text-size";

function useTextSize() {
  const [size, setSize] = useState(() => {
    try {
      return Math.min(2, Math.max(0, Number(window.localStorage.getItem(SIZE_KEY)) || 1));
    } catch {
      return 1;
    }
  });
  const change = (delta) =>
    setSize((s) => {
      const next = Math.min(2, Math.max(0, s + delta));
      try {
        window.localStorage.setItem(SIZE_KEY, String(next));
      } catch {
        // Private browsing: the choice just isn't remembered.
      }
      return next;
    });
  return [size, change];
}

function TextSizeControl({ size, onChange }) {
  return (
    <div role="group" aria-label="Text size" className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => onChange(-1)}
        disabled={size === 0}
        aria-label="Smaller text"
        className="grid size-10 place-items-center rounded-full border border-charcoal/15 bg-white disabled:opacity-40"
      >
        <Minus aria-hidden className="size-4" />
      </button>
      <span className="px-1 text-sm text-muted" aria-live="polite">
        Text {["S", "M", "L"][size]}
      </span>
      <button
        type="button"
        onClick={() => onChange(1)}
        disabled={size === 2}
        aria-label="Larger text"
        className="grid size-10 place-items-center rounded-full border border-charcoal/15 bg-white disabled:opacity-40"
      >
        <Plus aria-hidden className="size-4" />
      </button>
    </div>
  );
}

export function LearnLessonPage() {
  const { customer, isLoading } = useCustomer();
  const { courseSlug, lessonSlug } = useParams();
  if (isLoading)
    return (
      <Container className="py-20 text-center text-muted" role="status">
        Loading…
      </Container>
    );
  // Visitors may read lessons the course offers as free previews.
  if (!customer) return <PreviewLesson courseSlug={courseSlug} lessonSlug={lessonSlug} />;
  return <LessonReader courseSlug={courseSlug} lessonSlug={lessonSlug} />;
}

function PreviewLesson({ courseSlug, lessonSlug, enrolledError }) {
  const shopApi = useShopApi();
  const location = useLocation();
  const [state] = useLearnerData(
    () => shopApi.previewLesson(courseSlug, lessonSlug),
    `preview:${courseSlug}/${lessonSlug}`,
  );
  const [size, changeSize] = useTextSize();
  if (state.status === "loading")
    return (
      <Container className="py-20 text-center text-muted" role="status">
        Loading…
      </Container>
    );
  if (state.status === "error") {
    if (enrolledError) {
      return (
        <LearnShell title="Lesson" back={{ to: routes.course(courseSlug), label: "Course page" }}>
          <Container className="py-16">
            <AccessProblem error={enrolledError} courseSlug={courseSlug} />
          </Container>
        </LearnShell>
      );
    }
    return (
      <Navigate to={`${routes.signIn}?next=${encodeURIComponent(location.pathname)}`} replace />
    );
  }
  const { course, lesson } = state.data;
  return (
    <LearnShell title={lesson.title} back={{ to: routes.course(course.slug), label: course.title }}>
      <Container className="py-10">
        <article className={`mx-auto max-w-[68ch] ${TEXT_SIZES[size]}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
              Free preview
            </p>
            <TextSizeControl size={size} onChange={changeSize} />
          </div>
          <h1 className="mt-3 text-3xl font-medium sm:text-4xl">{lesson.title}</h1>
          <p className="mt-2 text-sm text-muted">{formatMinutes(lesson.minutes)} read</p>
          <div className="mt-8">
            <LessonBody blocks={lesson.body} />
          </div>
          <div className="mt-12 rounded-2xl bg-sage-50 p-6 text-base">
            <p className="font-medium">Enjoying this lesson?</p>
            <p className="mt-1 text-muted">
              Enrol to read every lesson, track your progress and receive a certificate.
            </p>
            <ButtonLink to={routes.course(course.slug)} className="mt-4">
              See the course
            </ButtonLink>
          </div>
        </article>
      </Container>
    </LearnShell>
  );
}

function LessonReader({ courseSlug, lessonSlug }) {
  const shopApi = useShopApi();
  const navigate = useNavigate();
  const [state, setState] = useLearnerData(
    () => shopApi.learningLesson(courseSlug, lessonSlug),
    `lesson:${courseSlug}/${lessonSlug}`,
  );
  const [size, changeSize] = useTextSize();
  const [complete, setComplete] = useState({ busy: false, error: "" });

  useEffect(() => {
    window.scrollTo?.(0, 0);
  }, [lessonSlug]);

  if (state.status === "loading")
    return (
      <Container className="py-20 text-center text-muted" role="status">
        Loading the lesson…
      </Container>
    );
  if (state.status === "error") {
    if (state.error?.code === "not_enrolled") {
      return (
        <PreviewLesson
          courseSlug={courseSlug}
          lessonSlug={lessonSlug}
          enrolledError={state.error}
        />
      );
    }
    return (
      <LearnShell title="Lesson" back={{ to: routes.learn(courseSlug), label: "Course outline" }}>
        <Container className="py-16">
          <AccessProblem error={state.error} courseSlug={courseSlug} />
        </Container>
      </LearnShell>
    );
  }
  const data = state.data;
  const { lesson } = data;
  const lessonState = data.state;
  const missing = lessonState.required_exercises.filter(
    (id) => !lessonState.acknowledged.includes(id),
  );

  const saveExercise = async (exerciseId, patch) => {
    const res = await shopApi.saveExercise(courseSlug, lessonSlug, exerciseId, patch);
    setState((s) => {
      const acknowledged = new Set(s.data.state.acknowledged);
      if (res.data.done) acknowledged.add(exerciseId);
      else acknowledged.delete(exerciseId);
      return {
        ...s,
        data: {
          ...s.data,
          state: {
            ...s.data.state,
            acknowledged: [...acknowledged],
            responses: { ...s.data.state.responses, [exerciseId]: res.data.response },
          },
        },
      };
    });
  };
  const download = async (file) => {
    const res = await shopApi.authorizeDownload(file.entitlement_id, file.version_id);
    redirectTo.go(res.data.url);
  };
  const markComplete = async () => {
    setComplete({ busy: true, error: "" });
    try {
      const res = await shopApi.completeLesson(courseSlug, lessonSlug);
      setState((s) => ({
        ...s,
        data: {
          ...s.data,
          state: { ...s.data.state, completed: true },
          progress: res.data.progress,
        },
      }));
      setComplete({ busy: false, error: "" });
      if (data.next) navigate(routes.learn(courseSlug, data.next.slug));
    } catch (error) {
      setComplete({ busy: false, error: error.message });
    }
  };
  const submitAttempt = (assessmentId) => async (answers) => {
    const res = await shopApi.submitAttempt(courseSlug, assessmentId, answers);
    setState((s) => ({
      ...s,
      data: {
        ...s.data,
        progress: res.data.progress,
        assessments: s.data.assessments.map((a) =>
          a.id === assessmentId ? res.data.assessment : a,
        ),
      },
    }));
    return res.data.attempt;
  };

  return (
    <LearnShell
      title={lesson.title}
      back={{ to: routes.learn(courseSlug), label: data.course.title }}
    >
      <Container className="py-10">
        <article className={`mx-auto max-w-[68ch] ${TEXT_SIZES[size]}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted">
              {data.module.title} · Lesson {lesson.position} of {lesson.count}
            </p>
            <TextSizeControl size={size} onChange={changeSize} />
          </div>
          <h1 className="mt-3 text-3xl font-medium sm:text-4xl">{lesson.title}</h1>
          <p className="mt-2 text-sm text-muted">
            {formatMinutes(lesson.minutes)} read
            {lessonState.completed && (
              <span className="ml-2 inline-flex items-center gap-1 font-medium text-sage-800">
                <BadgeCheck aria-hidden className="size-4" /> Completed
              </span>
            )}
          </p>
          <div className="mt-8">
            <LessonBody
              blocks={lesson.body}
              state={lessonState}
              onSaveExercise={saveExercise}
              onDownload={download}
            />
          </div>
          {data.assessments.map((assessment) => (
            <div key={assessment.id} className="mt-10 text-base">
              <AssessmentForm assessment={assessment} onSubmit={submitAttempt(assessment.id)} />
            </div>
          ))}
          <div className="mt-12 border-t border-charcoal/10 pt-8 text-base">
            <ProgressBar percent={data.progress.percent} />
            {!lessonState.completed ? (
              <div className="mt-5">
                {missing.length > 0 && (
                  <p className="mb-3 text-sm text-muted">
                    Mark the required exercise{missing.length > 1 ? "s" : ""} as done to complete
                    this lesson.
                  </p>
                )}
                <Button onClick={markComplete} disabled={complete.busy || missing.length > 0}>
                  <CheckCircle2 aria-hidden className="size-5" />
                  {complete.busy
                    ? "Saving…"
                    : data.next
                      ? "Complete and continue"
                      : "Mark as complete"}
                </Button>
                {complete.error && (
                  <p role="alert" className="mt-2 text-sm text-red-800">
                    {complete.error}
                  </p>
                )}
              </div>
            ) : data.progress.complete ? (
              <p role="status" className="mt-5 rounded-xl bg-sage-50 p-4">
                You've completed this course.{" "}
                <Link to={routes.learn(courseSlug)} className="underline underline-offset-4">
                  See your certificate
                </Link>
              </p>
            ) : null}
            <nav aria-label="Lessons" className="mt-8 flex flex-wrap justify-between gap-3">
              {data.previous ? (
                <ButtonLink
                  to={routes.learn(courseSlug, data.previous.slug)}
                  variant="outline"
                  size="sm"
                >
                  <ArrowLeft aria-hidden className="size-4" /> {data.previous.title}
                </ButtonLink>
              ) : (
                <span />
              )}
              {data.next && (
                <ButtonLink
                  to={routes.learn(courseSlug, data.next.slug)}
                  variant="outline"
                  size="sm"
                >
                  {data.next.title} <ArrowRight aria-hidden className="size-4" />
                </ButtonLink>
              )}
            </nav>
          </div>
        </article>
      </Container>
    </LearnShell>
  );
}

// ---- course-level assessment ------------------------------------------------------------

export function LearnAssessmentPage() {
  return (
    <RequireCustomer>
      <AssessmentPage />
    </RequireCustomer>
  );
}

function AssessmentPage() {
  const { courseSlug, assessmentId } = useParams();
  const shopApi = useShopApi();
  const [state, setState] = useLearnerData(
    () => shopApi.learningAssessment(courseSlug, Number(assessmentId)),
    `assessment:${courseSlug}/${assessmentId}`,
  );
  if (state.status === "loading")
    return (
      <Container className="py-20 text-center text-muted" role="status">
        Loading…
      </Container>
    );
  if (state.status === "error")
    return (
      <LearnShell
        title="Assessment"
        back={{ to: routes.learn(courseSlug), label: "Course outline" }}
      >
        <Container className="py-16">
          <AccessProblem error={state.error} courseSlug={courseSlug} />
        </Container>
      </LearnShell>
    );
  const data = state.data;
  const submit = async (answers) => {
    const res = await shopApi.submitAttempt(courseSlug, Number(assessmentId), answers);
    setState((s) => ({
      ...s,
      data: { ...s.data, assessment: res.data.assessment, progress: res.data.progress },
    }));
    return res.data.attempt;
  };
  return (
    <LearnShell
      title={data.assessment.title}
      back={{ to: routes.learn(courseSlug), label: data.course.title }}
    >
      <Container className="py-10">
        <div className="mx-auto max-w-[68ch]">
          <AssessmentForm assessment={data.assessment} onSubmit={submit} />
          <div className="mt-8">
            <ProgressBar percent={data.progress.percent} />
          </div>
        </div>
      </Container>
    </LearnShell>
  );
}

// ---- certificate verification (public) --------------------------------------------------

export function CertificatePage() {
  const { code } = useParams();
  const shopApi = useShopApi();
  const [state] = useLearnerData(() => shopApi.verifyCertificate(code), `certificate:${code}`);
  return (
    <>
      <Seo title="Certificate verification" path={routes.courses} noIndex />
      <Container size="narrow" className="py-16">
        <h1 className="text-3xl font-medium">Certificate verification</h1>
        <p className="mt-2 text-muted">Certificate ID {code}</p>
        <div className="mt-8" aria-live="polite">
          {state.status === "loading" ? (
            <p role="status">Checking…</p>
          ) : state.status === "error" ? (
            <p role="alert" className="rounded-2xl bg-red-50 p-5">
              No certificate matches this ID. Check that it was typed exactly as printed.
            </p>
          ) : (
            <div
              className={`rounded-2xl p-6 ${state.data.status === "valid" ? "bg-sage-50" : "bg-red-50"}`}
            >
              <p className="flex items-center gap-2 text-lg font-medium">
                {state.data.status === "valid" ? (
                  <>
                    <BadgeCheck aria-hidden className="size-6 text-sage-700" /> Valid certificate
                  </>
                ) : (
                  <>
                    <ShieldAlert aria-hidden className="size-6 text-red-800" /> This certificate has
                    been revoked
                  </>
                )}
              </p>
              <dl className="mt-4 grid gap-2 sm:grid-cols-[10rem_1fr]">
                <dt className="text-muted">Awarded to</dt>
                <dd className="font-medium">{state.data.recipient_name}</dd>
                <dt className="text-muted">Course</dt>
                <dd className="font-medium">{state.data.course_title}</dd>
                <dt className="text-muted">Issued</dt>
                <dd>{formatDate(state.data.issued_at)}</dd>
                <dt className="text-muted">Issued by</dt>
                <dd>{state.data.issuer}</dd>
              </dl>
              <p className="mt-4 text-sm text-muted">{state.data.statement}</p>
            </div>
          )}
        </div>
      </Container>
    </>
  );
}

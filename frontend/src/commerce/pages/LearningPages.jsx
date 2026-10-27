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
  NotebookPen,
  Search,
  ShieldAlert,
} from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { AssessmentForm } from "@/components/courses/AssessmentForm";
import { formatMinutes } from "@/components/courses/courseFormat";
import { LessonBody } from "@/components/courses/LessonBody";
import {
  BookmarkButton,
  ReaderOutline,
  ReaderSettings,
  SelectionToolbar,
  StudyPanel,
  TableOfContents,
} from "@/components/courses/reader/ReaderParts";
import { scrollBehavior, useReadingPosition } from "@/components/courses/reader/readerHooks";
import { readerStyle, useReadingPreferences } from "@/components/courses/reader/readerPrefs";
import {
  anchorFromSelection,
  blockElement,
  COLOR_LABELS,
  paintHighlights,
  rangeForAnchor,
  supportsHighlights,
} from "@/components/courses/reader/textAnchors";
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

export function LearningSearchForm({ initial = "", compact = false }) {
  const navigate = useNavigate();
  const [q, setQ] = useState(initial);
  const id = useId();
  return (
    <form
      role="search"
      className={compact ? "flex gap-2" : "flex flex-col gap-2 sm:flex-row"}
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) navigate(`${routes.learnSearch}?q=${encodeURIComponent(q.trim())}`);
      }}
    >
      <label htmlFor={id} className="sr-only">
        Search your courses
      </label>
      <input
        id={id}
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search lessons and courses"
        maxLength={120}
        className="min-w-0 flex-1 rounded-full border border-charcoal/15 bg-white px-4 py-2.5"
      />
      <Button type="submit" size="sm" variant="outline">
        <Search aria-hidden className="size-4" /> Search
      </Button>
    </form>
  );
}

function LearningList() {
  const shopApi = useShopApi();
  const [state] = useLearnerData(() => shopApi.learning(), "learning");
  if (state.status === "loading") return <p role="status">Loading your courses…</p>;
  if (state.status === "error") return <AccessProblem error={state.error} />;
  const items = state.data.enrollments;
  const tools = (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="sm:w-96">
        <LearningSearchForm compact />
      </div>
      <Link
        to={routes.notebook}
        className="inline-flex items-center gap-2 font-medium text-sage-800 underline underline-offset-4"
      >
        <NotebookPen aria-hidden className="size-4" /> Study notebook
      </Link>
    </div>
  );
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
    <>
      {tools}
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
              ) : null}
              {item.access === "active" &&
              item.resume &&
              !item.completed_at &&
              item.last_activity_at ? (
                <p className="text-sm text-muted">
                  Next: {item.resume.title}
                  {item.resume.percent ? ` · about ${Math.round(item.resume.percent)}% read` : ""}
                </p>
              ) : null}
              {item.access === "active" ? null : (
                <p className="rounded-xl bg-cream p-3 text-sm">
                  {item.access === "expired"
                    ? "Your access period ended. "
                    : item.access === "revoked"
                      ? "This enrolment was ended. "
                      : "Your access ended (refunded or removed). "}
                  <Link
                    to={routes.course(item.course.slug)}
                    className="underline underline-offset-4"
                  >
                    Course page
                  </Link>
                </p>
              )}
              <CertificateLinks certificate={item.certificate} shopApi={shopApi} />
            </div>
          </li>
        ))}
      </ul>
    </>
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

function ReaderFrame({ prefs, children }) {
  return (
    <div
      className="tpa-reader min-h-[60vh]"
      data-reader-theme={prefs.theme}
      style={readerStyle(prefs)}
    >
      {children}
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
  const [prefs, setPrefs, prefsStatus] = useReadingPreferences(shopApi, false);
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
      <ReaderFrame prefs={prefs}>
        <Container className="py-10">
          <article className="reader-column mx-auto">
            <div className="flex flex-wrap items-center justify-between gap-3 text-base">
              <p className="text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
                Free preview
              </p>
              <ReaderSettings prefs={prefs} onChange={setPrefs} status={prefsStatus} />
            </div>
            <h1 className="mt-3 text-3xl font-medium sm:text-4xl">{lesson.title}</h1>
            <p className="mt-2 text-sm text-muted">{formatMinutes(lesson.minutes)} read</p>
            <div className="mt-8">
              <LessonBody blocks={lesson.body} />
            </div>
            <div className="mt-12 rounded-2xl bg-sage-50 p-6 text-base">
              <p className="font-medium">Enjoying this lesson?</p>
              <p className="mt-1 text-muted">
                Enrol to read every lesson, save notes and highlights, track your progress and
                receive a certificate.
              </p>
              <ButtonLink to={routes.course(course.slug)} className="mt-4">
                See the course
              </ButtonLink>
            </div>
          </article>
        </Container>
      </ReaderFrame>
    </LearnShell>
  );
}

function jumpTo(root, uid) {
  const target = blockElement(root, uid);
  if (!target) return;
  target.scrollIntoView?.({ block: "start", behavior: scrollBehavior() });
  if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
  target.focus?.({ preventScroll: true });
}

function LessonReader({ courseSlug, lessonSlug }) {
  const shopApi = useShopApi();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [state, setState] = useLearnerData(
    () => shopApi.learningLesson(courseSlug, lessonSlug),
    `lesson:${courseSlug}/${lessonSlug}`,
  );
  const [prefs, setPrefs, prefsStatus] = useReadingPreferences(shopApi, true);
  const [complete, setComplete] = useState({ busy: false, error: "" });
  const [panelOpen, setPanelOpen] = useState(false);
  const [draftAnchor, setDraftAnchor] = useState(null);
  const [selection, setSelection] = useState(null);
  const [focusId, setFocusId] = useState(params.get("highlight"));
  const [notice, setNotice] = useState("");
  const [bookmarkBusy, setBookmarkBusy] = useState(false);
  const articleRef = useRef(null);
  const toggleRef = useRef(null);
  const panelId = useId();
  const ready = state.status === "ready";
  const study = ready ? state.data.study : null;

  useEffect(() => {
    if (!params.get("highlight")) window.scrollTo?.(0, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonSlug]);

  const patchStudy = useCallback(
    (fn) => setState((s) => ({ ...s, data: { ...s.data, study: fn(s.data.study) } })),
    [setState],
  );

  const position = useReadingPosition({
    articleRef,
    enabled: ready && !params.get("highlight"),
    initial: study?.position,
    save: (pos) => shopApi.savePosition(courseSlug, lessonSlug, pos),
    saveOnExit: (pos) => shopApi.savePositionOnExit?.(courseSlug, lessonSlug, pos),
  });

  // Paint saved highlights (CSS Custom Highlight API: the lesson DOM is never changed).
  useEffect(() => {
    if (!ready) return undefined;
    return paintHighlights(articleRef.current, study.highlights, focusId);
  }, [ready, study?.highlights, focusId]);

  // Opened from the notebook: show that highlight.
  useEffect(() => {
    if (!ready || !focusId) return;
    const item = study.highlights.find((h) => h.id === focusId);
    const range = item && rangeForAnchor(articleRef.current, item.anchor);
    if (range) {
      const rect = range.getBoundingClientRect?.();
      if (rect) window.scrollTo?.({ top: window.scrollY + rect.top - 160, behavior: "auto" });
      setNotice("Showing your highlight.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  // Text selection → highlight / note toolbar.
  useEffect(() => {
    if (!ready) return undefined;
    let frame = null;
    const check = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const result = anchorFromSelection(window.getSelection?.(), articleRef.current);
        setSelection(result);
      });
    };
    document.addEventListener("selectionchange", check);
    return () => {
      document.removeEventListener("selectionchange", check);
      cancelAnimationFrame(frame);
    };
  }, [ready]);

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
  const unticked = (lessonState.required_checklist ?? []).filter(
    (id) => !study.checklist.includes(id),
  );
  const blocked = missing.length > 0 || unticked.length > 0;

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
  const toggleChecklist = async (itemId, checked) => {
    const res = await shopApi.setChecklistItem(courseSlug, lessonSlug, itemId, checked);
    patchStudy((st) => ({ ...st, checklist: res.data.checklist }));
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

  const openPanel = () => setPanelOpen(true);
  const closePanel = () => {
    setPanelOpen(false);
    toggleRef.current?.focus();
  };
  const highlight = async (color) => {
    if (!selection?.anchor) return;
    try {
      const res = await shopApi.createHighlight(courseSlug, lessonSlug, {
        anchor: selection.anchor,
        color,
      });
      patchStudy((st) => ({
        ...st,
        highlights: [...st.highlights.filter((h) => h.id !== res.data.id), res.data],
      }));
      window.getSelection?.()?.removeAllRanges?.();
      setSelection(null);
      setNotice(`Highlighted in ${COLOR_LABELS[color].toLowerCase()}.`);
    } catch (error) {
      setSelection({ error: error.details?.anchor?.[0] ?? error.message });
    }
  };
  const noteOnSelection = () => {
    if (!selection?.anchor) return;
    setDraftAnchor(selection.anchor);
    window.getSelection?.()?.removeAllRanges?.();
    setSelection(null);
    setPanelOpen(true);
  };
  const createNote = async (body, anchor) => {
    const res = await shopApi.createNote(courseSlug, lessonSlug, {
      body,
      ...(anchor && { anchor }),
    });
    patchStudy((st) => ({ ...st, notes: [...st.notes, res.data] }));
    return res.data;
  };
  const saveNote = async (id, body) => {
    const res = await shopApi.updateNote(id, { body });
    patchStudy((st) => ({ ...st, notes: st.notes.map((n) => (n.id === id ? res.data : n)) }));
  };
  const deleteNote = async (id) => {
    await shopApi.deleteNote(id);
    patchStudy((st) => ({ ...st, notes: st.notes.filter((n) => n.id !== id) }));
    setNotice("Note deleted.");
  };
  const recolor = async (id, color) => {
    const res = await shopApi.updateHighlight(id, color);
    patchStudy((st) => ({
      ...st,
      highlights: st.highlights.map((h) => (h.id === id ? res.data : h)),
    }));
  };
  const removeHighlight = async (id) => {
    await shopApi.deleteHighlight(id);
    patchStudy((st) => ({ ...st, highlights: st.highlights.filter((h) => h.id !== id) }));
    setNotice("Highlight removed.");
  };
  const showAnchor = (anchor, id) => {
    const range = rangeForAnchor(articleRef.current, anchor);
    if (id) setFocusId(id);
    if (window.innerWidth < 1280) setPanelOpen(false);
    if (range?.getBoundingClientRect) {
      const rect = range.getBoundingClientRect();
      window.scrollTo?.({ top: window.scrollY + rect.top - 160, behavior: scrollBehavior() });
    } else jumpTo(articleRef.current, anchor.block);
  };
  const toggleBookmark = async () => {
    setBookmarkBusy(true);
    try {
      const res = await shopApi.setBookmark(courseSlug, lessonSlug, !study.bookmarked);
      patchStudy((st) => ({ ...st, bookmarked: res.data.bookmarked }));
      setNotice(res.data.bookmarked ? "Lesson saved to your bookmarks." : "Bookmark removed.");
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBookmarkBusy(false);
    }
  };
  const moduleNumber = data.outline.findIndex((m) => m.current) + 1;

  return (
    <LearnShell
      title={lesson.title}
      back={{ to: routes.learn(courseSlug), label: data.course.title }}
    >
      <ReaderFrame prefs={prefs}>
        <Container size="wide" className="py-6 lg:py-10">
          <div className="lg:grid lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-10 xl:grid-cols-[16rem_minmax(0,1fr)_14rem]">
            <aside className="hidden lg:block">
              <ReaderOutline courseSlug={courseSlug} outline={data.outline} variant="sidebar" />
            </aside>
            <div className="min-w-0">
              <div className="reader-column mx-auto space-y-4 text-base">
                <ReaderOutline courseSlug={courseSlug} outline={data.outline} />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm text-muted">
                    {moduleNumber ? `Module ${moduleNumber} · ` : ""}
                    {data.module.title} · Lesson {lesson.position} of {lesson.count}
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <BookmarkButton
                      bookmarked={study.bookmarked}
                      busy={bookmarkBusy}
                      onToggle={toggleBookmark}
                    />
                    <Button
                      ref={toggleRef}
                      variant="outline"
                      size="sm"
                      aria-expanded={panelOpen}
                      aria-controls={panelId}
                      onClick={panelOpen ? closePanel : openPanel}
                    >
                      <NotebookPen aria-hidden className="size-4" /> Notes
                      {study.notes.length + study.highlights.length > 0 &&
                        ` (${study.notes.length + study.highlights.length})`}
                    </Button>
                    <ReaderSettings prefs={prefs} onChange={setPrefs} status={prefsStatus} />
                  </div>
                </div>
              </div>
              <article ref={articleRef} className="reader-column mx-auto mt-6">
                <h1 className="text-3xl font-medium sm:text-4xl">{lesson.title}</h1>
                <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
                  <span>{formatMinutes(lesson.minutes)} read</span>
                  <span>
                    Module progress: {data.module.completed} of {data.module.total} lessons
                  </span>
                  {lessonState.completed && (
                    <span className="inline-flex items-center gap-1 font-medium text-sage-800">
                      <BadgeCheck aria-hidden className="size-4" /> Completed
                    </span>
                  )}
                </p>
                {position.restored && (
                  <div
                    role="status"
                    className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-sage-50 px-4 py-3 text-sm"
                  >
                    We've taken you back to where you left off.
                    <button
                      type="button"
                      className="font-medium underline underline-offset-4"
                      onClick={() => {
                        position.dismiss();
                        window.scrollTo?.({ top: 0, behavior: scrollBehavior() });
                      }}
                    >
                      Start from the top
                    </button>
                  </div>
                )}
                {data.toc?.length >= 2 && (
                  <div className="mt-6 rounded-2xl border border-charcoal/10 bg-white p-4 xl:hidden">
                    <TableOfContents
                      toc={data.toc}
                      onJump={(uid) => jumpTo(articleRef.current, uid)}
                    />
                  </div>
                )}
                <div className="mt-8">
                  <LessonBody
                    blocks={lesson.body}
                    state={lessonState}
                    checklist={study.checklist}
                    onSaveExercise={saveExercise}
                    onDownload={download}
                    onToggleChecklist={toggleChecklist}
                  />
                </div>
              </article>
              <div className="reader-column mx-auto text-base">
                {data.assessments.map((assessment) => (
                  <div key={assessment.id} className="mt-10">
                    <AssessmentForm
                      assessment={assessment}
                      onSubmit={submitAttempt(assessment.id)}
                    />
                  </div>
                ))}
                <div className="mt-12 border-t border-charcoal/10 pt-8">
                  <ProgressBar percent={data.progress.percent} />
                  {!lessonState.completed ? (
                    <div className="mt-5">
                      {missing.length > 0 && (
                        <p className="mb-3 text-sm text-muted">
                          Mark the required exercise{missing.length > 1 ? "s" : ""} as done to
                          complete this lesson.
                        </p>
                      )}
                      {unticked.length > 0 && (
                        <p className="mb-3 text-sm text-muted">
                          Tick every item in the required checklist to complete this lesson.
                        </p>
                      )}
                      <Button onClick={markComplete} disabled={complete.busy || blocked}>
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
                        aria-label={`Previous lesson: ${data.previous.title}`}
                      >
                        <ArrowLeft aria-hidden className="size-4" />
                        {data.previous.title}
                      </ButtonLink>
                    ) : (
                      <span />
                    )}
                    {data.next && (
                      <ButtonLink
                        to={routes.learn(courseSlug, data.next.slug)}
                        variant="outline"
                        size="sm"
                        aria-label={`Next lesson: ${data.next.title}`}
                      >
                        {data.next.title} <ArrowRight aria-hidden className="size-4" />
                      </ButtonLink>
                    )}
                  </nav>
                </div>
              </div>
            </div>
            <aside className="hidden xl:block">
              <div className="sticky top-24 space-y-6">
                <TableOfContents toc={data.toc} onJump={(uid) => jumpTo(articleRef.current, uid)} />
                <p className="text-sm text-muted">
                  Tip: select any text to highlight it or add a note.
                </p>
              </div>
            </aside>
          </div>
        </Container>
        <p role="status" aria-live="polite" className="sr-only">
          {notice}
        </p>
        <SelectionToolbar
          selection={panelOpen ? null : selection}
          onHighlight={highlight}
          onNote={noteOnSelection}
          onDismiss={() => setSelection(null)}
        />
        <StudyPanel
          open={panelOpen}
          onClose={closePanel}
          study={study}
          draftAnchor={draftAnchor}
          onClearAnchor={() => setDraftAnchor(null)}
          onCreateNote={createNote}
          onSaveNote={saveNote}
          onDeleteNote={deleteNote}
          onRecolor={recolor}
          onRemoveHighlight={removeHighlight}
          onJump={showAnchor}
          highlightsSupported={supportsHighlights()}
          panelId={panelId}
        />
      </ReaderFrame>
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

import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

export const COURSE_PERMS = [
  "courses.view",
  "courses.create",
  "courses.edit",
  "courses.publish",
  "courses.archive",
  "courses.manage_curriculum",
  "courses.manage_assessments",
  "courses.view_enrollments",
  "courses.manage_enrollments",
  "courses.view_reports",
];

const fail = (status, code, message, details) =>
  Promise.reject(new ApiError({ status, code, message, details }));
const ok = (data, meta) => Promise.resolve(meta ? { data, meta } : { data });

const usd = (amount_minor) => ({
  currency: "USD",
  amount_minor,
  amount: (amount_minor / 100).toFixed(2),
  formatted: `USD ${(amount_minor / 100).toFixed(2)}`,
});

export const courseCards = [
  {
    slug: "calm-foundations",
    title: "Calm Foundations",
    subtitle: "Two weeks to a calmer start",
    summary: "Short written lessons for calmer mornings.",
    cover: null,
    access_type: "free",
    availability: "available",
    level: "beginner",
    total_minutes: 45,
    lesson_count: 3,
    category: { slug: "mindset", name: "Mindset" },
    topics: [{ slug: "positive-mindset", name: "Positive Mindset" }],
    featured: true,
    certificate: true,
    published_at: "2026-10-20T09:00:00.000Z",
    is_free: true,
    product: null,
    prices: [],
    purchasable: false,
  },
  {
    slug: "resilience-course",
    title: "Resilience Course",
    subtitle: "",
    summary: "Bounce back from setbacks with practical exercises.",
    cover: null,
    access_type: "premium",
    availability: "available",
    level: "intermediate",
    total_minutes: 150,
    lesson_count: 8,
    category: null,
    topics: [],
    featured: false,
    certificate: true,
    published_at: "2026-10-25T09:00:00.000Z",
    is_free: false,
    product: {
      id: "prodresil",
      slug: "resilience-course-access",
      title: "Resilience Course Access",
      type: "course",
    },
    prices: [usd(4900)],
    purchasable: true,
  },
];

export function courseDetail(slug) {
  const card = courseCards.find((c) => c.slug === slug);
  if (!card) return null;
  return {
    ...card,
    description: [{ type: "paragraph", text: `${card.title} is written for busy people.` }],
    outcomes: ["Pause before reacting", "Build a calm morning routine"],
    prerequisites: [],
    audience: ["Anyone who feels rushed in the morning"],
    author: { slug: "tpa", name: "TPA Editorial", bio: "", image: null, is_person: false },
    syllabus: [
      {
        title: "Getting started",
        description: "",
        objectives: [],
        lessons: [
          { title: "Notice the pause", slug: "notice-the-pause", minutes: 10, preview: true },
          { title: "Breathe", slug: null, minutes: 15, preview: false },
        ],
      },
    ],
    module_count: 1,
    assessment_count: 1,
    quiz_count: 1,
    enrollment_open: true,
    access_days: null,
    seo: { title: card.title, description: card.summary, image: null, noindex: false },
    updated_at: card.published_at,
    preview: false,
    related: courseCards.filter((c) => c.slug !== slug),
    access: card.is_free ? null : { label: "Lifetime access" },
  };
}

export function courseContentApi() {
  return {
    getCourses: vi.fn(async () =>
      ok(courseCards, {
        total: courseCards.length,
        categories: [{ slug: "mindset", name: "Mindset" }],
        topics: [{ slug: "positive-mindset", name: "Positive Mindset" }],
        sorts: ["featured", "newest", "title", "shortest"],
      }),
    ),
    getCourse: vi.fn(async (slug) => {
      const data = courseDetail(slug);
      return data ? ok(data) : fail(404, "not_found", "Course not found.");
    }),
  };
}

// ---- learner ------------------------------------------------------------------------------

function quizFor(attempts = []) {
  return {
    id: 7,
    kind: "quiz",
    graded: true,
    title: "Check-in",
    description: "",
    lesson_id: 2,
    passing_score: 60,
    max_attempts: 3,
    attempts_used: attempts.length,
    attempts_left: 3 - attempts.length,
    required_for_completion: true,
    status: attempts.length
      ? attempts.some((a) => a.passed)
        ? "passed"
        : "failed"
      : "not_started",
    questions: [
      {
        id: 71,
        kind: "single_choice",
        prompt: "Best first step?",
        help_text: "",
        required: true,
        graded: true,
        options: [
          { id: "a", text: "Rush" },
          { id: "b", text: "Pause" },
        ],
      },
    ],
    attempts,
  };
}

export function createCourseShopApi({ enrolled = true, verified = true } = {}) {
  const state = { acknowledged: [], responses: {}, completed: false, attempts: [], enrolled };
  const guard = () => {
    if (!verified)
      return fail(
        403,
        "email_verification_required",
        "Confirm your email address to start learning.",
      );
    if (!state.enrolled)
      return fail(403, "not_enrolled", "Enrol in this course to open its lessons.");
    return null;
  };
  const progress = () => ({
    percent: state.completed ? 50 : 0,
    required_lessons: 2,
    completed_lessons: state.completed ? 1 : 0,
    required_assessments: 0,
    completed_assessments: 0,
    complete: false,
  });
  const lesson = () => ({
    course: { slug: "calm-foundations", title: "Calm Foundations" },
    module: { id: 1, title: "Getting started" },
    lesson: {
      slug: "notice-the-pause",
      title: "Notice the pause",
      summary: "",
      minutes: 10,
      position: 1,
      count: 2,
      required: true,
      body: [
        { type: "paragraph", text: "Breathe in slowly and notice three things." },
        { type: "key_points", title: "Remember", items: ["Slow down", "Notice"] },
        {
          type: "exercise",
          id: "three-things",
          prompt: "List three things you can see.",
          required: true,
          allow_response: true,
        },
        {
          type: "download",
          file_id: "file1",
          title: "Workbook",
          file: {
            entitlement_id: 5,
            version_id: 9,
            title: "Workbook",
            format: "PDF",
            size_bytes: 120000,
          },
        },
      ],
    },
    state: {
      completed: state.completed,
      acknowledged: state.acknowledged,
      responses: state.responses,
      required_exercises: ["three-things"],
    },
    previous: null,
    next: { slug: "breathe", title: "Breathe" },
    assessments: [quizFor(state.attempts)],
    progress: progress(),
  });
  return {
    learning: vi.fn(
      () =>
        guard() ??
        ok({
          enrollments: state.enrolled
            ? [
                {
                  course: {
                    slug: "calm-foundations",
                    title: "Calm Foundations",
                    summary: "Short lessons.",
                    cover: null,
                    access_type: "free",
                    total_minutes: 45,
                    archived: false,
                  },
                  access: "active",
                  enrolled_at: "2026-10-26T10:00:00.000Z",
                  expires_at: null,
                  last_activity_at: null,
                  completed_at: null,
                  progress: progress(),
                  resume: { slug: "notice-the-pause", title: "Notice the pause" },
                  certificate: null,
                  certificate_available: false,
                },
              ]
            : [],
        }),
    ),
    learningStatus: vi.fn(() =>
      ok({
        verified,
        enrolled: state.enrolled,
        access: state.enrolled ? "active" : null,
        progress: 0,
        completed: false,
        can_enroll: !state.enrolled,
      }),
    ),
    enroll: vi.fn(() => {
      if (!verified)
        return fail(
          403,
          "email_verification_required",
          "Confirm your email address to start learning.",
        );
      state.enrolled = true;
      return ok({ enrolled: true, created: true, course: "calm-foundations" });
    }),
    learningCourse: vi.fn(
      () =>
        guard() ??
        ok({
          course: {
            slug: "calm-foundations",
            title: "Calm Foundations",
            summary: "Short lessons.",
            outcomes: [],
            total_minutes: 45,
            access_type: "free",
            certificate_enabled: true,
            cover: null,
          },
          access: "active",
          progress: progress(),
          resume: { slug: "notice-the-pause", title: "Notice the pause" },
          certificate: null,
          certificate_available: false,
          modules: [
            {
              id: 1,
              title: "Getting started",
              description: "",
              objectives: [],
              completed: false,
              lessons: [
                {
                  slug: "notice-the-pause",
                  title: "Notice the pause",
                  summary: "",
                  minutes: 10,
                  completed: state.completed,
                  viewed: true,
                  required: true,
                },
                {
                  slug: "breathe",
                  title: "Breathe",
                  summary: "",
                  minutes: 15,
                  completed: false,
                  viewed: false,
                  required: true,
                },
              ],
            },
          ],
          assessments: [],
        }),
    ),
    learningLesson: vi.fn(() => guard() ?? ok(lesson())),
    saveExercise: vi.fn((_slug, _lesson, exercise, body) => {
      if (body.done !== undefined) {
        state.acknowledged = body.done ? [exercise] : [];
      }
      if (body.response !== undefined) state.responses = { [exercise]: body.response };
      return ok({
        exercise_id: exercise,
        done: state.acknowledged.includes(exercise),
        response: state.responses[exercise] ?? "",
      });
    }),
    completeLesson: vi.fn(() => {
      if (!state.acknowledged.includes("three-things"))
        return fail(400, "validation_error", "Mark the required exercises as done first.");
      state.completed = true;
      return ok({ lesson_completed: true, progress: progress() });
    }),
    submitAttempt: vi.fn((_slug, _id, answers) => {
      const passed = answers["71"] === "b";
      const attempt = {
        id: state.attempts.length + 1,
        attempt_number: state.attempts.length + 1,
        score: passed ? 1 : 0,
        max_score: 1,
        percent: passed ? 100 : 0,
        passed,
        graded: true,
        answers_revealed: true,
        results: [
          {
            question_id: 71,
            kind: "single_choice",
            prompt: "Best first step?",
            answer: answers["71"],
            graded: true,
            correct: passed,
            points: passed ? 1 : 0,
            correct_answer: ["b"],
            options: [
              { id: "a", text: "Rush" },
              { id: "b", text: "Pause" },
            ],
            explanation: "Pausing first helps.",
          },
        ],
        submitted_at: "2026-10-27T10:00:00.000Z",
      };
      state.attempts = [attempt, ...state.attempts];
      return ok({ attempt, assessment: quizFor(state.attempts), progress: progress() });
    }),
    learningAssessment: vi.fn(
      () =>
        guard() ??
        ok({
          course: { slug: "calm-foundations", title: "Calm Foundations" },
          assessment: quizFor(state.attempts),
          progress: progress(),
        }),
    ),
    requestCertificate: vi.fn(() => ok({})),
    certificatePdfUrl: (code) => `/api/v1/account/certificates/${code}/pdf`,
    verifyCertificate: vi.fn((code) =>
      code === "TPA-AAAA-BBBB-CCCC"
        ? ok({
            code,
            status: "valid",
            recipient_name: "Ada Reader",
            course_title: "Calm Foundations",
            issued_at: "2026-10-27T10:00:00.000Z",
            issuer: "Think Positive Always",
            statement:
              "This is a platform-issued certificate of completion from Think Positive Always. It is not an accredited qualification, degree or professional licence.",
            revoked_at: null,
          })
        : fail(404, "not_found", "Certificate not found."),
    ),
    previewLesson: vi.fn((slug, lessonSlug) =>
      lessonSlug === "notice-the-pause"
        ? ok({
            course: {
              slug,
              title: "Calm Foundations",
              access_type: "free",
              is_free: true,
              prices: [],
              purchasable: false,
              product: null,
            },
            lesson: {
              slug: lessonSlug,
              title: "Notice the pause",
              summary: "",
              minutes: 10,
              body: [{ type: "paragraph", text: "A free sample lesson." }],
            },
          })
        : fail(404, "not_found", "Lesson not found."),
    ),
    _state: state,
  };
}

// ---- admin --------------------------------------------------------------------------------

export function createCourseAdminFake(getUser) {
  const perms = () => new Set(getUser()?.permissions ?? []);
  const can = () => {
    const p = perms();
    return {
      create: p.has("courses.create"),
      edit: p.has("courses.edit"),
      publish: p.has("courses.publish"),
      archive: p.has("courses.archive"),
      manage_curriculum: p.has("courses.manage_curriculum"),
      manage_assessments: p.has("courses.manage_assessments"),
      view_enrollments: p.has("courses.view_enrollments"),
      manage_enrollments: p.has("courses.manage_enrollments"),
      view_reports: p.has("courses.view_reports"),
    };
  };
  const modules = [
    {
      id: 1,
      title: "Getting started",
      description: "",
      objectives: [],
      position: 0,
      lessons: [
        {
          id: 11,
          module_id: 1,
          slug: "notice",
          title: "Notice the pause",
          summary: "",
          status: "published",
          is_preview: true,
          completion_required: true,
          estimated_minutes: null,
          minutes: 10,
          position: 0,
        },
        {
          id: 12,
          module_id: 1,
          slug: "breathe",
          title: "Breathe",
          summary: "",
          status: "draft",
          is_preview: false,
          completion_required: true,
          estimated_minutes: null,
          minutes: 5,
          position: 1,
        },
      ],
    },
    { id: 2, title: "Going deeper", description: "", objectives: [], position: 1, lessons: [] },
  ];
  const detail = () => ({
    id: 3,
    public_id: "c3",
    slug: "calm-foundations",
    title: "Calm Foundations",
    status: "draft",
    access_type: "free",
    availability: "available",
    enrollment_open: true,
    category: null,
    product: null,
    module_count: 2,
    lesson_count: 2,
    published_lesson_count: 1,
    assessment_count: 1,
    enrollment_count: 0,
    completion_count: 0,
    is_featured: false,
    published_at: null,
    updated_at: "2026-10-27T09:00:00.000Z",
    subtitle: "",
    summary: "Short lessons.",
    description: [],
    outcomes: ["Pause"],
    prerequisites: [],
    audience: [],
    level: "beginner",
    estimated_minutes: null,
    total_minutes: 10,
    category_id: null,
    author_id: null,
    author: null,
    topic_ids: [],
    cover_media_id: null,
    cover: null,
    social_image_id: null,
    access_days: null,
    product_id: null,
    product_files: [],
    certificate_enabled: true,
    featured_order: 0,
    seo_title: null,
    meta_description: null,
    noindex: false,
    first_published_at: null,
    archived_at: null,
    lock_version: 1,
    modules,
    assessments: [
      {
        id: 7,
        kind: "quiz",
        graded: true,
        title: "Check-in",
        status: "draft",
        lesson_id: null,
        question_count: 1,
        required_for_completion: true,
        passing_score: 70,
        max_attempts: null,
        show_answers: "after_submit",
        position: 0,
      },
    ],
    readiness: {
      issues: [],
      warnings: ["1 lesson(s) are still drafts and won't be shown to learners."],
      publishable: true,
    },
    can: can(),
    created_at: "2026-10-26T09:00:00.000Z",
  });
  const report = {
    courses: { total: 2, published: 1, draft: 1, scheduled: 0, archived: 0 },
    enrollments: {
      enrollments: 4,
      active_enrollments: 4,
      completions: 1,
      active_learners_30d: 3,
      new_enrollments_30d: 4,
      certificates_issued: 1,
      completion_rate: 25,
    },
    by_source: { free: 4 },
    by_status: { in_progress: 3, completed: 1, revoked: 0 },
    assessment_pass_rates: [
      {
        assessment_id: 7,
        course_id: 3,
        title: "Check-in",
        learners: 2,
        passed: 1,
        attempts: 3,
        pass_rate: 50,
      },
    ],
    per_course: [
      {
        id: 3,
        title: "Calm Foundations",
        status: "published",
        access_type: "free",
        learners: 4,
        completions: 1,
        average_progress: 40,
      },
    ],
    generated_at: "2026-10-27T10:00:00.000Z",
  };
  const forbidden = () =>
    fail(403, "forbidden", "You do not have permission to perform this action.");
  return {
    courses: {
      list: vi.fn(() =>
        perms().has("courses.view")
          ? ok([detail()], { page: 1, page_size: 25, total: 1, can: can() })
          : forbidden(),
      ),
      options: vi.fn(() =>
        ok({
          categories: [],
          authors: [],
          topics: [{ id: 1, name: "Positive Mindset" }],
          products: [],
          levels: [],
        }),
      ),
      reports: vi.fn(() => (perms().has("courses.view_reports") ? ok(report) : forbidden())),
      courseReports: vi.fn(() => ok(report)),
      get: vi.fn(() => ok(detail())),
      create: vi.fn((body) =>
        perms().has("courses.create") ? ok({ ...detail(), id: 9, title: body.title }) : forbidden(),
      ),
      update: vi.fn((_id, body) => ok({ ...detail(), ...body, lock_version: 2 })),
      remove: vi.fn(() => ok({ deleted: true })),
      action: vi.fn((_id, action) =>
        ok({ ...detail(), status: action === "publish" ? "published" : "draft" }),
      ),
      preview: vi.fn(() => ok({ ...courseDetail("calm-foundations"), preview: true })),
      categories: vi.fn(() => ok([])),
      createCategory: vi.fn(() => ok({})),
      updateCategory: vi.fn(() => ok({})),
      removeCategory: vi.fn(() => ok({})),
      addModule: vi.fn(() => ok(modules)),
      updateModule: vi.fn(() => ok(modules)),
      removeModule: vi.fn(() => ok(modules)),
      reorder: vi.fn(() => ok(modules)),
      addLesson: vi.fn(() => ok({ ...modules[0].lessons[1], id: 13 })),
      lesson: vi.fn((_id, lessonId) =>
        ok({
          ...(modules[0].lessons.find((l) => l.id === Number(lessonId)) ?? modules[0].lessons[0]),
          body: [{ type: "paragraph", text: "Hello" }],
          preview_body: [{ type: "paragraph", text: "Hello" }],
          assessments: [],
          word_count: 1,
          reading_minutes: 1,
          course_id: 3,
        }),
      ),
      updateLesson: vi.fn((_id, _lessonId, body) =>
        ok({
          ...modules[0].lessons[0],
          ...body,
          assessments: [],
          word_count: 1,
          reading_minutes: 1,
        }),
      ),
      removeLesson: vi.fn(() => ok(modules)),
      lessonStatus: vi.fn(() =>
        ok({ ...modules[0].lessons[1], status: "published", body: [], assessments: [] }),
      ),
      assessment: vi.fn(() =>
        ok({
          ...detail().assessments[0],
          description: "",
          attempt_count: 0,
          answer_key_visible: perms().has("courses.manage_assessments"),
          questions: [
            {
              id: 71,
              kind: "single_choice",
              graded: true,
              prompt: "Best first step?",
              help_text: "",
              options: [
                { id: "a", text: "Rush" },
                { id: "b", text: "Pause" },
              ],
              settings: {},
              points: 1,
              required: true,
              position: 0,
              ...(perms().has("courses.manage_assessments") && {
                correct: ["b"],
                explanation: "Pause.",
              }),
            },
          ],
        }),
      ),
      createAssessment: vi.fn(() => ok({ id: 8 })),
      updateAssessment: vi.fn(() => ok({})),
      removeAssessment: vi.fn(() => ok({})),
      assessmentStatus: vi.fn(() => ok({})),
      reorderAssessments: vi.fn(() => ok([])),
      addQuestion: vi.fn(() => ok({})),
      updateQuestion: vi.fn(() => ok({})),
      removeQuestion: vi.fn(() => ok({})),
      reorderQuestions: vi.fn(() => ok({})),
      enrollments: vi.fn(() => ok([], { page: 1, page_size: 25, total: 0 })),
      enrollment: vi.fn(() => ok({})),
      enroll: vi.fn(() => ok({})),
      enrollmentAction: vi.fn(() => ok({})),
      certificateAction: vi.fn(() => ok({})),
    },
  };
}

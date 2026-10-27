import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

/** Batch 09.2 permissions (mirrors backend/app/auth/permissions.py). */
export const ASSIGNMENT_PERMS = [
  "assignments.view",
  "assignments.manage",
  "assignments.view_submissions",
  "assignments.grade",
  "assignments.publish_grades",
  "assignments.manage_exceptions",
  "assignments.view_reports",
];
export const BANK_PERMS = ["question_banks.view", "question_banks.manage"];

const fail = (status, code, message, details) =>
  Promise.reject(new ApiError({ status, code, message, details }));
const ok = (data, meta) => Promise.resolve(meta ? { data, meta } : { data });
const NOW = "2026-10-29T10:00:00.000Z";

export const RUBRIC_V1 = {
  id: 1,
  version: 1,
  criteria: [
    {
      id: "c1",
      title: "Insight",
      description: "Depth of reflection",
      max_points: 10,
      descriptors: [
        { label: "Excellent", points: 10, description: "" },
        { label: "Basic", points: 4, description: "" },
      ],
    },
    { id: "c2", title: "Clarity", description: "", max_points: 5, descriptors: [] },
  ],
  total_points: 15,
  passing_percent: 60,
  feedback_required: true,
  created_at: NOW,
};

export function makeAssignment(overrides = {}) {
  return {
    id: "asg1",
    course_id: 3,
    lesson_id: null,
    kind: "written",
    title: "Morning reflection",
    instructions: "Reflect on one calm moment this week.",
    prompts: [{ id: "p1", text: "What did you notice?" }],
    requirements: { min_words: 20, max_words: null, files: "optional", max_files: 2 },
    required: true,
    passing_percent: null,
    max_attempts: 3,
    resubmission_policy: "on_request",
    available_from: null,
    due_at: null,
    late_policy: "block",
    status: "draft",
    rubric: RUBRIC_V1,
    position: 0,
    lock_version: 1,
    required_since: null,
    published_at: null,
    archived_at: null,
    updated_at: NOW,
    ...overrides,
  };
}

// ---- admin --------------------------------------------------------------------------------

export function createAssessmentAdminFake(getUser) {
  const perms = () => new Set(getUser()?.permissions ?? []);
  const state = {
    assignments: [makeAssignment()],
    rubrics: [RUBRIC_V1],
    grade: null,
    submissionStatus: "pending_review",
    banks: [
      {
        id: "qb1",
        title: "Breathing basics",
        description: "Shared quiz questions",
        status: "active",
        lock_version: 1,
        archived_at: null,
        created_at: NOW,
        updated_at: NOW,
      },
    ],
    questions: [
      {
        id: "bq1",
        kind: "single_choice",
        prompt: "Best first step when stressed?",
        help_text: "",
        options: [
          { id: "a", text: "Rush" },
          { id: "b", text: "Pause" },
        ],
        correct: ["b"],
        explanation: "Pausing first calms the body.",
        settings: {},
        points: 1,
        required: true,
        tags: ["breath"],
        status: "active",
        version: 1,
        lock_version: 1,
        updated_at: NOW,
      },
    ],
  };
  const withKey = (q) => {
    const graded = ["single_choice", "multiple_select", "true_false"].includes(q.kind);
    const data = { ...q, graded };
    if (!perms().has("question_banks.manage")) {
      delete data.correct;
      delete data.explanation;
    }
    return data;
  };
  const counts = () => ({
    active: state.questions.filter((q) => q.status === "active").length,
    retired: state.questions.filter((q) => q.status === "retired").length,
  });
  const bankDetail = (bank) => ({
    ...bank,
    question_counts: counts(),
    tags: [...new Set(state.questions.flatMap((q) => q.tags))].sort(),
    used_by: [],
    answer_key_visible: perms().has("question_banks.manage"),
  });
  const find = (id) => state.assignments.find((a) => a.id === id);
  const attempt = () => ({
    id: "att1",
    number: 1,
    status: "submitted",
    latest: true,
    responses: { p1: "I noticed my breathing slowed when I paused before replying." },
    word_count: 11,
    files: [
      {
        id: "file1",
        filename: "notes.pdf",
        format: "pdf",
        size_bytes: 2048,
        uploaded_at: NOW,
      },
    ],
    lock_version: null,
    submitted_at: NOW,
    is_late: false,
    updated_at: NOW,
    content_sha256: "abc",
    grade: state.grade,
  });
  const submission = () => ({
    id: "sub1",
    assignment: find("asg1"),
    learner: { customer_id: 5, name: "Ada Reader", email: "ada@example.com" },
    enrollment_id: 9,
    status: state.submissionStatus,
    lock_version: 1,
    completed_at: null,
    attempts: [attempt()],
  });
  return {
    _assessmentState: state,
    assignments: {
      list: vi.fn(() => ok(state.assignments)),
      get: vi.fn((_c, id) => ok(find(id))),
      create: vi.fn((_c, body) => {
        const item = makeAssignment({
          id: `asg${state.assignments.length + 1}`,
          rubric: null,
          ...body,
        });
        state.assignments.push(item);
        return ok(item);
      }),
      update: vi.fn((_c, id, body) => {
        const current = find(id);
        if (body.lock_version !== current.lock_version)
          return fail(409, "edit_conflict", "Someone else changed this.");
        const { lock_version: _ignored, ...rest } = body;
        Object.assign(current, rest, { lock_version: current.lock_version + 1 });
        return ok({ ...current });
      }),
      remove: vi.fn(() => ok({ deleted: true })),
      setStatus: vi.fn((_c, id, status) => {
        const current = find(id);
        current.status = status;
        current.lock_version += 1;
        if (status === "published") current.published_at = NOW;
        return ok({ ...current });
      }),
      rubrics: vi.fn(() => ok([...state.rubrics].reverse())),
      saveRubric: vi.fn((_c, id, body) => {
        const current = find(id);
        const rubric = {
          id: state.rubrics.length + 1,
          version: state.rubrics.length + 1,
          criteria: body.criteria.map((c, i) => ({ id: c.id ?? `n${i}`, ...c })),
          total_points: body.criteria.reduce((s, c) => s + c.max_points, 0),
          passing_percent: body.passing_percent,
          feedback_required: body.feedback_required,
          created_at: NOW,
        };
        state.rubrics.push(rubric);
        Object.assign(current, { rubric, lock_version: current.lock_version + 1 });
        return ok({ rubric, assignment: { ...current } });
      }),
      report: vi.fn(() => ok({})),
      submissions: vi.fn(() =>
        ok([
          {
            id: "sub1",
            customer_id: 5,
            status: "graded",
            attempts: 1,
            latest_attempt: "att1",
            submitted_at: NOW,
            late: false,
          },
        ]),
      ),
      assessors: vi.fn(() => ok([{ user_id: 7, name: "Gina Grader", email: "gina@example.org" }])),
      setAssessors: vi.fn((_c, ids) =>
        ok(ids.map((id) => ({ user_id: id, name: `User ${id}`, email: `u${id}@example.org` }))),
      ),
      queue: vi.fn((params = {}) => {
        const items = [
          {
            id: "sub1",
            status: state.submissionStatus,
            course: { id: 3, title: "Calm Foundations" },
            assignment: { id: "asg1", title: "Morning reflection" },
            learner: { name: "Ada Reader", email: "ada@example.com" },
            attempts: 1,
            latest_attempt: "att1",
            submitted_at: NOW,
            late: true,
            grade_status: state.grade?.status ?? null,
          },
          {
            id: "sub2",
            status: "pending_review",
            course: { id: 4, title: "Resilience Course" },
            assignment: { id: "asg9", title: "Case study" },
            learner: { name: "Ben Learner", email: "ben@example.com" },
            attempts: 1,
            latest_attempt: "att9",
            submitted_at: NOW,
            late: false,
            grade_status: null,
          },
        ].filter((i) => !params.course_id || String(i.course.id) === String(params.course_id));
        return ok({
          items,
          courses: [
            { id: 3, title: "Calm Foundations" },
            { id: 4, title: "Resilience Course" },
          ],
          truncated: false,
        });
      }),
      submission: vi.fn(() => ok(submission())),
      startReview: vi.fn(() => {
        state.submissionStatus = "under_review";
        return ok(submission());
      }),
      saveGrade: vi.fn((_id, body) => {
        const scores = body.scores ?? state.grade?.scores ?? {};
        const total = Object.values(scores).reduce((s, v) => s + v, 0);
        state.grade = {
          status: "draft",
          outcome: "graded",
          rubric: RUBRIC_V1,
          scores,
          total_points: Object.keys(scores).length === 2 ? total : null,
          max_points: 15,
          percent: Object.keys(scores).length === 2 ? Math.round((100 * total) / 15) : null,
          passed: null,
          feedback: body.feedback ?? "",
          private_notes: body.private_notes ?? "",
          lock_version: (state.grade?.lock_version ?? 0) + 1,
          published_at: null,
          retracted_at: null,
          retracted_reason: "",
        };
        state.submissionStatus = "under_review";
        return ok(state.grade);
      }),
      publishGrade: vi.fn((_id, body) => {
        if (!state.grade?.feedback)
          return fail(400, "validation_error", "The grade isn't ready to release.", {
            grade: ["This rubric requires written feedback."],
          });
        state.grade = {
          ...state.grade,
          status: "published",
          outcome: body.outcome,
          published_at: NOW,
          lock_version: state.grade.lock_version + 1,
        };
        state.submissionStatus = body.outcome === "graded" ? "completed" : "changes_requested";
        return ok(state.grade);
      }),
      retractGrade: vi.fn(() => ok(state.grade)),
      fileUrl: (id) => `/api/v1/admin/assignment-files/${id}/download`,
    },
    questionBanks: {
      list: vi.fn(() =>
        ok(state.banks.map(bankDetail), { page: 1, page_size: 100, total: state.banks.length }),
      ),
      get: vi.fn((id) => {
        const bank = state.banks.find((b) => b.id === id);
        return bank ? ok(bankDetail(bank)) : fail(404, "not_found", "Question bank not found.");
      }),
      create: vi.fn((body) => {
        const bank = { ...state.banks[0], id: "qb2", title: body.title, lock_version: 1 };
        state.banks.push(bank);
        return ok(bankDetail(bank));
      }),
      update: vi.fn((id, body) => {
        const bank = state.banks.find((b) => b.id === id);
        Object.assign(bank, body, { lock_version: bank.lock_version + 1 });
        return ok(bankDetail(bank));
      }),
      remove: vi.fn(() => ok({ deleted: true })),
      questions: vi.fn((_id, params = {}) => {
        const rows = state.questions.filter((q) => !params.status || q.status === params.status);
        return ok(rows.map(withKey), { page: 1, page_size: 25, total: rows.length });
      }),
      addQuestion: vi.fn((_id, body) => {
        const q = {
          ...state.questions[0],
          ...body,
          id: `bq${state.questions.length + 1}`,
          version: 1,
          lock_version: 1,
          status: "active",
        };
        state.questions.push(q);
        return ok(withKey(q));
      }),
      updateQuestion: vi.fn((_id, qid, body) => {
        const q = state.questions.find((x) => x.id === qid);
        if (body.lock_version !== q.lock_version)
          return fail(409, "edit_conflict", "Someone else changed this.");
        const { lock_version: _ignored, ...rest } = body;
        Object.assign(q, rest, { lock_version: q.lock_version + 1 });
        return ok(withKey(q));
      }),
      removeQuestion: vi.fn(() => ok({ deleted: true })),
    },
  };
}

// ---- learner ------------------------------------------------------------------------------

const PRACTICE_QUESTIONS = [
  {
    id: "b11",
    kind: "single_choice",
    prompt: "Which helps first?",
    help_text: "",
    required: true,
    graded: true,
    options: [
      { id: "a", text: "Rushing" },
      { id: "b", text: "Breathing" },
    ],
  },
  {
    id: "b12",
    kind: "true_false",
    prompt: "Rest matters.",
    help_text: "",
    required: true,
    graded: true,
    options: [
      { id: "true", text: "True" },
      { id: "false", text: "False" },
    ],
  },
];

export function practiceAssessment(overrides = {}) {
  return {
    id: 9,
    kind: "quiz",
    graded: true,
    title: "Calm practice exam",
    description: "Check what you remember.",
    lesson_id: null,
    passing_score: 50,
    max_attempts: 2,
    attempts_used: 0,
    attempts_left: 2,
    required_for_completion: false,
    status: "not_started",
    practice: true,
    time_limit_minutes: 10,
    requires_start: true,
    question_count: 2,
    best_percent: null,
    questions: [],
    in_progress: null,
    attempts: [],
    ...overrides,
  };
}

/**
 * Learner-side fake for assignments, started attempts and history. `secondsLeft` sets the
 * started attempt's remaining time (timed-attempt tests).
 */
export function createAssessmentShopApi({ secondsLeft = 600 } = {}) {
  const state = {
    view: {
      assignment: makeAssignment({ status: "published", published_at: NOW }),
      submission: null,
      attempts_allowed: 3,
      can_submit: true,
      blocked_reason: null,
      draft: null,
      history: [],
    },
    draftLock: 0,
    practice: practiceAssessment(),
    attempt: null,
    saved: {},
  };
  const draft = (responses) => ({
    id: "d1",
    number: 1,
    status: "draft",
    latest: false,
    responses,
    word_count: Object.values(responses).join(" ").split(/\s+/).filter(Boolean).length,
    files: state.view.draft?.files ?? [],
    lock_version: state.draftLock,
    submitted_at: null,
    is_late: false,
    updated_at: NOW,
    grade: null,
  });
  const result = (status = "submitted") => {
    const correct = state.saved.b11 === "b";
    const tf = state.saved.b12 === "true";
    const score = (correct ? 1 : 0) + (tf ? 1 : 0);
    return {
      id: 41,
      attempt_number: state.practice.attempts.length + 1,
      score,
      max_score: 2,
      percent: score * 50,
      passed: score >= 1,
      graded: true,
      answers_revealed: true,
      status,
      practice: true,
      started_at: NOW,
      deadline_at: NOW,
      submitted_at: NOW,
      results: [
        {
          question_id: "b11",
          kind: "single_choice",
          prompt: "Which helps first?",
          answer: state.saved.b11 ?? null,
          graded: true,
          correct,
          points: correct ? 1 : 0,
          correct_answer: ["b"],
          options: PRACTICE_QUESTIONS[0].options,
          explanation: "Breathing slows the stress response.",
        },
      ],
    };
  };
  return {
    _assessmentState: state,
    assignments: vi.fn(() =>
      ok([
        {
          id: "asg1",
          title: "Morning reflection",
          kind: "written",
          required: true,
          lesson_id: null,
          due_at: null,
          status: state.view.submission?.status ?? "not_started",
        },
      ]),
    ),
    assignment: vi.fn(() => ok(state.view)),
    saveAssignmentDraft: vi.fn((_slug, _id, body) => {
      if (state.view.draft && body.lock_version !== state.draftLock)
        return fail(409, "edit_conflict", "Someone else changed this.");
      state.draftLock += 1;
      state.view = {
        ...state.view,
        submission: state.view.submission ?? {
          id: "sub1",
          status: "draft",
          completed_at: null,
          attempts_used: 0,
        },
        draft: draft({ ...(state.view.draft?.responses ?? {}), ...body.responses }),
      };
      return ok(state.view);
    }),
    submitAssignment: vi.fn((_slug, _id, body) => {
      if (body.lock_version !== state.draftLock)
        return fail(409, "edit_conflict", "Someone else changed this.");
      const submitted = {
        ...state.view.draft,
        status: "submitted",
        latest: true,
        lock_version: null,
        submitted_at: NOW,
      };
      state.view = {
        ...state.view,
        submission: { id: "sub1", status: "pending_review", completed_at: null, attempts_used: 1 },
        can_submit: false,
        blocked_reason: "awaiting_review",
        draft: null,
        history: [submitted],
      };
      return ok(state.view);
    }),
    uploadAssignmentFile: vi.fn((_slug, _id, file) => {
      state.draftLock += 1;
      const files = [
        ...(state.view.draft?.files ?? []),
        {
          id: "file1",
          filename: file.name,
          format: "pdf",
          size_bytes: file.size,
          uploaded_at: NOW,
        },
      ];
      state.view = {
        ...state.view,
        draft: { ...draft(state.view.draft?.responses ?? {}), files },
      };
      return ok(state.view);
    }),
    removeAssignmentFile: vi.fn(() => ok({ deleted: true })),
    assignmentFileUrl: (id) => `/api/v1/account/assignment-files/${id}/download`,
    startAttempt: vi.fn(() => {
      state.attempt = {
        id: 40,
        attempt_number: state.practice.attempts.length + 1,
        status: "in_progress",
        started_at: NOW,
        deadline_at: NOW,
        seconds_left: secondsLeft,
        questions: PRACTICE_QUESTIONS,
        answers: {},
      };
      state.saved = {};
      state.practice = {
        ...state.practice,
        in_progress: state.attempt,
        attempts_used: state.practice.attempts_used + 1,
      };
      return ok({ attempt: state.attempt, assessment: state.practice });
    }),
    attempt: vi.fn(() => ok({ attempt: state.attempt })),
    saveAttemptAnswers: vi.fn((_slug, _id, _attemptId, answers) => {
      Object.entries(answers).forEach(([k, v]) => {
        if (v == null) delete state.saved[k];
        else state.saved[k] = v;
      });
      return ok({ attempt: { ...state.attempt, answers: { ...state.saved } } });
    }),
    submitStartedAttempt: vi.fn((_slug, _id, _attemptId, answers) => {
      const expired = answers === undefined;
      if (!expired) Object.assign(state.saved, answers);
      const attempt = result(expired ? "expired" : "submitted");
      state.practice = {
        ...state.practice,
        in_progress: null,
        attempts: [attempt, ...state.practice.attempts],
        attempts_left: state.practice.max_attempts - state.practice.attempts_used,
        status: attempt.passed ? "passed" : "failed",
        best_percent: Math.max(attempt.percent, state.practice.best_percent ?? 0),
      };
      return ok({
        attempt,
        assessment: state.practice,
        progress: {
          percent: 0,
          required_lessons: 2,
          completed_lessons: 0,
          required_assessments: 0,
          completed_assessments: 0,
          complete: false,
        },
      });
    }),
    assessmentHistory: vi.fn((slug) =>
      ok({
        course: { slug, title: "Calm Foundations" },
        assessments: [
          {
            assessment_id: 9,
            title: "Calm practice exam",
            kind: "quiz",
            practice: true,
            status: "passed",
            attempts_used: 1,
            max_attempts: 2,
            best_percent: 100,
            passing_score: 50,
            in_progress: null,
            attempts: [
              {
                id: 41,
                attempt_number: 1,
                status: "submitted",
                score: 2,
                max_score: 2,
                percent: 100,
                passed: true,
                started_at: NOW,
                submitted_at: NOW,
              },
            ],
          },
          {
            assessment_id: 7,
            title: "Check-in",
            kind: "quiz",
            practice: false,
            status: "not_started",
            attempts_used: 0,
            max_attempts: null,
            best_percent: null,
            passing_score: 60,
            in_progress: null,
            attempts: [],
          },
        ],
      }),
    ),
  };
}

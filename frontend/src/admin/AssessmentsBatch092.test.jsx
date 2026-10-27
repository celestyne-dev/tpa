import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { ApiError } from "@/services/apiClient";
import { plannedModules } from "@/admin/navigation";
import { createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

const openAssignment = async (user) => {
  await user.click(await screen.findByRole("button", { name: /Morning reflection/ }));
  return screen.findByRole("region", { name: /Written assignment: Morning reflection/ });
};

describe("Batch 09.2 navigation and permissions", () => {
  it("adds reviews and question banks to the Learning section only for permitted roles", async () => {
    renderApp("/admin/courses");
    const nav = (await screen.findAllByRole("navigation", { name: "Admin" }))[0];
    expect(within(nav).getByRole("link", { name: "Assignment reviews" })).toHaveAttribute(
      "href",
      "/admin/assignment-reviews",
    );
    expect(within(nav).getByRole("link", { name: "Question banks" })).toBeInTheDocument();
    // Memberships and Analytics stay planned (never links).
    expect(plannedModules.map((m) => m.label)).toEqual(["Memberships", "Analytics"]);
    expect(within(nav).queryByRole("link", { name: /Memberships|Analytics/ })).toBeNull();
  });

  it("hides the new areas from roles without the permissions", async () => {
    renderApp("/admin/courses", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    const nav = (await screen.findAllByRole("navigation", { name: "Admin" }))[0];
    expect(within(nav).queryByRole("link", { name: "Assignment reviews" })).toBeNull();
    expect(within(nav).queryByRole("link", { name: "Question banks" })).toBeNull();
  });

  it("blocks the review dashboard for roles without assignments.view_submissions", async () => {
    renderApp("/admin/assignment-reviews", {
      adminApi: createFakeAdminApi({ role: "analyst" }),
    });
    expect(await screen.findByText("You don't have access to this area")).toBeVisible();
  });
});

describe("assignment management", () => {
  it("creates an assignment from the course editor tab", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/courses/3/assignments");
    const tabs = await screen.findByRole("navigation", { name: "Course sections" });
    expect(within(tabs).getByRole("link", { name: "Assignments" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await screen.findByRole("button", { name: /Morning reflection/ });
    await user.type(screen.getByLabelText("New assignment"), "Calm office case");
    await user.selectOptions(screen.getAllByLabelText("Type").at(-1), "case_study");
    await user.click(screen.getByRole("button", { name: /Create/ }));
    await waitFor(() =>
      expect(adminApi.assignments.create).toHaveBeenCalledWith(3, {
        title: "Calm office case",
        kind: "case_study",
        lesson_id: null,
      }),
    );
    expect(
      await screen.findByRole("region", { name: /Case study: Calm office case/ }),
    ).toBeInTheDocument();
  });

  it("edits deadlines, attempts and requirements, publishes and previews", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/courses/3/assignments");
    const editor = await openAssignment(user);
    const attempts = within(editor).getByLabelText(/Attempts allowed/);
    await user.clear(attempts);
    await user.type(attempts, "2");
    await user.click(within(editor).getByLabelText(/Required for course completion/));
    await user.selectOptions(within(editor).getByLabelText(/Supporting documents/), "required");
    await user.type(within(editor).getByLabelText(/Deadline/), "2026-11-30T17:00");
    expect(within(editor).getByText("Unsaved changes")).toBeInTheDocument();
    await user.click(within(editor).getByRole("button", { name: "Save assignment" }));
    await waitFor(() => expect(adminApi.assignments.update).toHaveBeenCalled());
    const [courseId, id, body] = adminApi.assignments.update.mock.calls[0];
    expect([courseId, id]).toEqual([3, "asg1"]);
    expect(body).toMatchObject({
      max_attempts: 2,
      required: false,
      lock_version: 1,
      requirements: { files: "required", max_files: 2, min_words: 20, max_words: null },
      prompts: [{ id: "p1", text: "What did you notice?" }],
    });
    // Deadlines are sent with an explicit time zone (UTC ISO string).
    expect(body.due_at).toMatch(/Z$/);
    expect(await within(editor).findByText("All changes saved")).toBeInTheDocument();

    await user.click(within(editor).getByRole("button", { name: "Publish" }));
    await waitFor(() =>
      expect(adminApi.assignments.setStatus).toHaveBeenCalledWith(3, "asg1", "published"),
    );
    await user.click(within(editor).getByRole("button", { name: /Preview as learner/ }));
    const dialog = await screen.findByRole("dialog", { name: "Learner preview" });
    expect(within(dialog).getByText("Reflect on one calm moment this week.")).toBeVisible();
    expect(within(dialog).getByText(/Attach at least one supporting document/)).toBeVisible();
  });

  it("shows server validation as an accessible error summary", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    adminApi.assignments.update.mockImplementationOnce(() =>
      Promise.reject(
        new ApiError({
          status: 400,
          code: "validation_error",
          message: "Some fields need attention.",
          details: { due_at: ["Use an ISO 8601 date-time with a time zone."] },
        }),
      ),
    );
    renderApp("/admin/courses/3/assignments", { adminApi });
    const editor = await openAssignment(user);
    await user.type(within(editor).getByLabelText(/^Title/), "!");
    await user.click(within(editor).getByRole("button", { name: "Save assignment" }));
    const line = await within(editor).findByText(
      "due at: Use an ISO 8601 date-time with a time zone.",
    );
    expect(line.closest("[role=alert]")).toHaveFocus();
  });

  it("is read-only for roles that can view but not manage assignments", async () => {
    const user = userEvent.setup();
    renderApp("/admin/courses/3/assignments", {
      adminApi: createFakeAdminApi({ role: "analyst" }),
    });
    await openAssignment(user);
    expect(screen.queryByLabelText("New assignment")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save assignment" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
    expect(screen.getByLabelText(/^Title/)).toBeDisabled();
  });
});

describe("rubric builder", () => {
  it("warns about graded submissions, validates and saves a new version", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/courses/3/assignments");
    const editor = await openAssignment(user);
    expect(
      await within(editor).findByText(/1 submission has already been reviewed or graded/),
    ).toBeInTheDocument();
    expect(within(editor).getByText(/Saving creates version 2/)).toBeInTheDocument();

    await user.click(within(editor).getByRole("button", { name: /Add criterion/ }));
    await user.type(within(editor).getByLabelText("Criterion 3 name"), "Practical steps");
    await user.click(
      within(editor)
        .getAllByRole("button", { name: /Add descriptor/ })
        .at(-1),
    );
    await user.type(within(editor).getAllByLabelText("Descriptor 1 label").at(-1), "x");
    // Points above the criterion maximum are caught before anything is sent.
    const points = within(editor).getAllByLabelText("Descriptor 1 points").at(-1);
    await user.clear(points);
    await user.type(points, "50");
    await user.click(within(editor).getByRole("button", { name: "Save as new version" }));
    expect(await within(editor).findByText(/points must be 0 to 10/)).toBeInTheDocument();
    expect(adminApi.assignments.saveRubric).not.toHaveBeenCalled();

    await user.clear(points);
    await user.type(points, "8");
    await user.click(within(editor).getByRole("button", { name: "Move criterion 3 up" }));
    await user.click(within(editor).getByRole("button", { name: "Save as new version" }));
    await waitFor(() => expect(adminApi.assignments.saveRubric).toHaveBeenCalled());
    const [, , body] = adminApi.assignments.saveRubric.mock.calls[0];
    expect(body.lock_version).toBe(1);
    expect(body.criteria.map((c) => c.title)).toEqual(["Insight", "Practical steps", "Clarity"]);
    expect(body.criteria[0]).toMatchObject({ id: "c1", max_points: 10 });
    expect(await screen.findByText("Rubric version 2 saved.")).toBeInTheDocument();

    await user.click(within(editor).getByRole("button", { name: /Version history/ }));
    const versions = await within(editor).findByRole("list", { name: "Rubric versions" });
    expect(within(versions).getByText(/Version 2 \(current\)/)).toBeInTheDocument();
    expect(within(versions).getByText(/Version 1 ·/)).toBeInTheDocument();
  });
});

describe("instructor grading", () => {
  it("filters the review queue and grades with the rubric, then releases", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/assignment-reviews");
    expect(await screen.findByRole("heading", { name: "Assignment reviews" })).toBeVisible();
    const table = await screen.findByRole("table", { name: "Submissions" });
    expect(within(table).getByText("Ben Learner")).toBeInTheDocument();
    expect(within(table).getByText("Late")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Course"), "3");
    await waitFor(() =>
      expect(adminApi.assignments.queue).toHaveBeenLastCalledWith({
        status: "awaiting",
        course_id: "3",
      }),
    );
    await waitFor(() => expect(screen.queryByText("Ben Learner")).toBeNull());
    await user.click(screen.getByRole("link", { name: /Ada Reader/ }));

    expect(
      await screen.findByText("I noticed my breathing slowed when I paused before replying."),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: /notes\.pdf/ })).toHaveAttribute(
      "href",
      "/api/v1/admin/assignment-files/file1/download",
    );
    await user.click(screen.getByRole("button", { name: "Start review" }));
    await waitFor(() => expect(adminApi.assignments.startReview).toHaveBeenCalledWith("sub1", 1));

    const panel = await screen.findByRole("region", { name: "Grade attempt 1" });
    await user.click(within(panel).getByRole("button", { name: "Excellent · 10" }));
    await user.type(within(panel).getByLabelText("Score for Clarity"), "4");
    expect(within(panel).getByText(/Total: 14 of 15 points/)).toBeInTheDocument();
    await user.type(within(panel).getByLabelText(/Feedback for the learner/), "Thoughtful work.");
    await user.type(within(panel).getByLabelText(/Private staff notes/), "Strong");
    await user.click(within(panel).getByRole("button", { name: "Save draft grade" }));
    await waitFor(() =>
      expect(adminApi.assignments.saveGrade).toHaveBeenCalledWith("att1", {
        scores: { c1: 10, c2: 4 },
        feedback: "Thoughtful work.",
        private_notes: "Strong",
      }),
    );
    const refreshed = await screen.findByRole("region", { name: "Grade attempt 1" });
    expect(within(refreshed).getByText(/Draft — not visible to the learner/)).toBeInTheDocument();
    await user.click(within(refreshed).getByRole("button", { name: "Release grade" }));
    await waitFor(() =>
      expect(adminApi.assignments.publishGrade).toHaveBeenCalledWith("att1", {
        lock_version: 1,
        outcome: "graded",
      }),
    );
    expect(await screen.findByText("Grade released to the learner.")).toBeInTheDocument();
  });

  it("lets assessors grade but hides release controls they can't use", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi({ role: "course_assessor" });
    adminApi.assignments._grade = null;
    renderApp("/admin/assignment-reviews/sub1", { adminApi });
    const panel = await screen.findByRole("region", { name: "Grade attempt 1" });
    await user.type(within(panel).getByLabelText("Score for Insight"), "8");
    await user.click(within(panel).getByRole("button", { name: "Save draft grade" }));
    await waitFor(() => expect(adminApi.assignments.saveGrade).toHaveBeenCalled());
    await screen.findByText(/Draft — not visible to the learner/);
    expect(screen.queryByRole("button", { name: "Release grade" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Request changes" })).toBeNull();
  });

  it("shows release problems returned by the server", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/assignment-reviews/sub1");
    const panel = await screen.findByRole("region", { name: "Grade attempt 1" });
    await user.type(within(panel).getByLabelText("Score for Insight"), "8");
    await user.click(within(panel).getByRole("button", { name: "Save draft grade" }));
    await waitFor(() => expect(adminApi.assignments.saveGrade).toHaveBeenCalled());
    const fresh = await screen.findByRole("region", { name: "Grade attempt 1" });
    await user.click(within(fresh).getByRole("button", { name: "Request changes" }));
    expect(await within(fresh).findByRole("alert")).toHaveTextContent(
      "This rubric requires written feedback.",
    );
  });
});

describe("question banks", () => {
  it("manages banks and questions with answer keys for managers", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/question-banks");
    await user.click(await screen.findByRole("link", { name: /Breathing basics/ }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Breathing basics" }),
    ).toBeVisible();
    const list = await screen.findByRole("list", { name: "Bank questions" });
    expect(within(list).getByText("Answer: Pause")).toBeInTheDocument();

    await user.click(within(list).getByRole("button", { name: "Edit" }));
    const prompt = within(list).getByLabelText(/^Question/);
    await user.clear(prompt);
    await user.type(prompt, "What helps first?");
    await user.clear(within(list).getByLabelText(/Tags/));
    await user.type(within(list).getByLabelText(/Tags/), "Breath, Beginner");
    await user.click(within(list).getByRole("button", { name: "Save question" }));
    await waitFor(() =>
      expect(adminApi.questionBanks.updateQuestion).toHaveBeenCalledWith(
        "qb1",
        "bq1",
        expect.objectContaining({
          prompt: "What helps first?",
          tags: ["breath", "beginner"],
          correct: ["b"],
          lock_version: 1,
        }),
      ),
    );

    await user.click(await screen.findByRole("button", { name: "Add question" }));
    await user.selectOptions(screen.getByLabelText("Question type"), "true_false");
    await user.type(screen.getAllByLabelText(/^Question/).at(-1), "Sleep matters.");
    await user.selectOptions(screen.getByLabelText("The statement is"), "true");
    await user.type(screen.getByLabelText(/Explanation/), "Rest restores.");
    await user.click(screen.getByRole("button", { name: "Save question" }));
    await waitFor(() =>
      expect(adminApi.questionBanks.addQuestion).toHaveBeenCalledWith(
        "qb1",
        expect.objectContaining({
          kind: "true_false",
          prompt: "Sleep matters.",
          correct: ["true"],
          explanation: "Rest restores.",
          tags: [],
        }),
      ),
    );
  });

  it("never shows or sends answer keys for view-only roles", async () => {
    const adminApi = createFakeAdminApi({ role: "bank_viewer" });
    renderApp("/admin/question-banks/qb1", { adminApi });
    expect(
      await screen.findByText("Answer keys and explanations are hidden for your role."),
    ).toBeVisible();
    const list = await screen.findByRole("list", { name: "Bank questions" });
    expect(within(list).queryByText(/Answer:/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add question" })).toBeNull();
    const payload = await adminApi.questionBanks.questions.mock.results[0].value;
    expect(payload.data[0]).not.toHaveProperty("correct");
    expect(payload.data[0]).not.toHaveProperty("explanation");
  });
});

describe("practice exam configuration", () => {
  it("configures practice mode, timing, shuffling and bank draws on a quiz", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/courses/3/assessments");
    await user.click(await screen.findByRole("button", { name: /^Check-in/ }));
    const editor = await screen.findByRole("region", { name: /Quiz: Check-in/ });
    await user.selectOptions(within(editor).getByLabelText("Mode"), "practice");
    expect(within(editor).getByLabelText(/Required for course completion/)).toBeDisabled();
    await user.type(within(editor).getByLabelText(/Time limit/), "20");
    await user.click(within(editor).getByLabelText(/Shuffle question order/));
    await user.click(within(editor).getByLabelText(/Shuffle answer options/));
    await user.click(within(editor).getByRole("button", { name: /Add a draw/ }));
    await user.selectOptions(await within(editor).findByLabelText("Draw 1: question bank"), "qb1");
    const count = within(editor).getByLabelText("Draw 1: number of questions");
    await user.clear(count);
    await user.type(count, "3");
    await user.type(within(editor).getByLabelText(/Draw 1: only these tags/), "Breath");
    await user.click(within(editor).getByRole("button", { name: "Save settings" }));
    await waitFor(() =>
      expect(adminApi.courses.updateAssessment).toHaveBeenCalledWith(
        3,
        7,
        expect.objectContaining({
          practice: true,
          required_for_completion: false,
          time_limit_minutes: 20,
          shuffle_questions: true,
          shuffle_options: true,
          selection: [{ bank_id: "qb1", count: 3, tags: ["breath"] }],
        }),
      ),
    );
  });

  it("explains when a role can't list question banks", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi({ role: "content_editor" });
    const original = adminApi.courses.assessment.getMockImplementation();
    adminApi.courses.assessment.mockImplementation(async (...args) => {
      const res = await original(...args);
      return { data: { ...res.data, selection: [{ bank_id: "qb1", count: 2, tags: [] }] } };
    });
    renderApp("/admin/courses/3/assessments", { adminApi });
    await user.click(await screen.findByRole("button", { name: /^Check-in/ }));
    const editor = await screen.findByRole("region", { name: /Quiz: Check-in/ });
    expect(within(editor).getByText(/can't list question banks/)).toBeInTheDocument();
    expect(within(editor).getByLabelText("Draw 1: bank id")).toHaveValue("qb1");
    expect(adminApi.questionBanks.list).not.toHaveBeenCalled();
  });
});

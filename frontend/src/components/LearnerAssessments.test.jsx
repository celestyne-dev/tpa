import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/apiClient";
import { RUBRIC_V1, createAssessmentShopApi } from "@/test/assessmentFake";
import { createFakeShopApi, customerProfile } from "@/test/commerceFake";
import { createCourseShopApi } from "@/test/courseFake";
import { preloadCommerce, renderApp } from "@/test/utils";

beforeAll(preloadCommerce);

const CSRF = "tpa_customer_csrf";
const signIn = () => {
  document.cookie = `${CSRF}=test-token; path=/`;
};
afterEach(() => {
  document.cookie = `${CSRF}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  window.localStorage.clear();
});

const ASSIGNMENT = "/learn/calm-foundations/assignments/asg1";
const EXAM = "/learn/calm-foundations/assessments/9";

function learnerApi(options) {
  const assessments = createAssessmentShopApi(options);
  const base = { ...createFakeShopApi({ customer: customerProfile() }), ...createCourseShopApi() };
  const api = { ...base, ...assessments };
  api.learningAssessment = vi.fn((slug, id) =>
    id === 9
      ? Promise.resolve({
          data: {
            course: { slug, title: "Calm Foundations" },
            assessment: assessments._assessmentState.practice,
            progress: { percent: 0, required_lessons: 2, completed_lessons: 0 },
          },
        })
      : base.learningAssessment(slug, id),
  );
  return api;
}

describe("learner written assignments", () => {
  it("autosaves drafts, uploads a document and submits once", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learnerApi();
    renderApp(ASSIGNMENT, { shopApi });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Morning reflection" }),
    ).toBeVisible();
    expect(screen.getByText("Reflect on one calm moment this week.")).toBeVisible();
    expect(screen.getByText(/0 of 3 attempts used/)).toBeInTheDocument();

    const box = screen.getByLabelText(/What did you notice\?/);
    await user.type(box, "My shoulders dropped when I paused.");
    expect(screen.getByText("6 words")).toBeInTheDocument();
    await waitFor(
      () =>
        expect(shopApi.saveAssignmentDraft).toHaveBeenCalledWith("calm-foundations", "asg1", {
          responses: { p1: "My shoulders dropped when I paused." },
        }),
      { timeout: 5000 },
    );
    expect(await screen.findByText("Draft saved.")).toBeInTheDocument();

    const file = new File(["%PDF-1.4"], "notes.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/Attach a document/), file);
    await waitFor(() => expect(shopApi.uploadAssignmentFile).toHaveBeenCalled());
    expect(await screen.findByRole("link", { name: /notes\.pdf/ })).toHaveAttribute(
      "href",
      "/api/v1/account/assignment-files/file1/download",
    );

    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    await user.click(screen.getByRole("button", { name: "Yes, submit" }));
    await waitFor(() =>
      expect(shopApi.submitAssignment).toHaveBeenCalledWith("calm-foundations", "asg1", {
        idempotency_key: expect.stringMatching(/^[A-Za-z0-9-]{8,64}$/),
        lock_version: 2,
      }),
    );
    expect(await screen.findByText("Status: Submitted — waiting for review")).toBeInTheDocument();
    expect(screen.getByText(/Your reviewer will be notified/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit for review" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Your submissions" })).toBeInTheDocument();
  });

  it("keeps the learner's text when saving fails and retries", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learnerApi();
    const real = shopApi.saveAssignmentDraft.getMockImplementation();
    shopApi.saveAssignmentDraft.mockImplementationOnce(() =>
      Promise.reject(new ApiError({ code: "network_error", message: "Offline" })),
    );
    renderApp(ASSIGNMENT, { shopApi });
    const box = await screen.findByLabelText(/What did you notice\?/);
    await user.type(box, "Kept safe");
    expect(
      await screen.findByText(/Couldn't save your draft/, {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(box).toHaveValue("Kept safe");
    const backup = JSON.parse(
      window.localStorage.getItem("tpa-assignment-draft:calm-foundations:asg1"),
    );
    expect(backup.responses).toEqual({ p1: "Kept safe" });
    shopApi.saveAssignmentDraft.mockImplementation(real);
    expect(await screen.findByText("Draft saved.", {}, { timeout: 6000 })).toBeInTheDocument();
    expect(window.localStorage.getItem("tpa-assignment-draft:calm-foundations:asg1")).toBeNull();
  }, 15_000);

  it("lists submission requirements returned by the server", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learnerApi();
    shopApi.submitAssignment.mockImplementationOnce(() =>
      Promise.reject(
        new ApiError({
          status: 400,
          code: "validation_error",
          message: "Your submission isn't complete yet.",
          details: { requirements: ["Write at least 20 words in total."] },
        }),
      ),
    );
    renderApp(ASSIGNMENT, { shopApi });
    await user.type(await screen.findByLabelText(/What did you notice\?/), "Too short");
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    await user.click(screen.getByRole("button", { name: "Yes, submit" }));
    const line = await screen.findByText("Write at least 20 words in total.");
    expect(line.closest("[role=alert]")).toHaveFocus();
    expect(screen.getByLabelText(/What did you notice\?/)).toHaveValue("Too short");
  });

  it("shows only released feedback, never staff notes, and explains why resubmitting is closed", async () => {
    signIn();
    const shopApi = learnerApi();
    const state = shopApi._assessmentState;
    state.view = {
      ...state.view,
      submission: { id: "sub1", status: "completed", completed_at: null, attempts_used: 1 },
      can_submit: false,
      blocked_reason: "completed",
      history: [
        {
          id: "att1",
          number: 1,
          status: "submitted",
          latest: true,
          responses: { p1: "My answer" },
          word_count: 2,
          files: [],
          submitted_at: "2026-10-29T10:00:00.000Z",
          is_late: false,
          grade: {
            outcome: "graded",
            scores: { c1: 8, c2: 4 },
            total_points: 12,
            max_points: 15,
            percent: 80,
            passed: true,
            feedback: "Lovely detail.",
            rubric: RUBRIC_V1,
            released_at: "2026-10-29T11:00:00.000Z",
          },
        },
      ],
    };
    renderApp(ASSIGNMENT, { shopApi });
    const feedback = await screen.findByRole("region", { name: "Instructor feedback" });
    expect(within(feedback).getByText("Passed — 80%")).toBeInTheDocument();
    expect(within(feedback).getByText("Insight: 8 / 10")).toBeInTheDocument();
    expect(within(feedback).getByText("Lovely detail.")).toBeInTheDocument();
    expect(screen.getByText("You have completed this assignment.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit for review" })).toBeNull();
    expect(screen.queryByText(/staff note/i)).toBeNull();
  });

  it("lists assignments in the course outline", async () => {
    signIn();
    renderApp("/learn/calm-foundations", { shopApi: learnerApi() });
    const section = await screen.findByRole("region", { name: "Assignments" });
    expect(within(section).getByRole("link", { name: "Morning reflection" })).toHaveAttribute(
      "href",
      ASSIGNMENT,
    );
    expect(within(section).getByText(/Not started/)).toBeInTheDocument();
  });
});

describe("learner practice exams", () => {
  it("starts, navigates, autosaves and submits a timed exam without exposing answers", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learnerApi();
    renderApp(EXAM, { shopApi });
    expect(await screen.findByRole("heading", { name: "Calm practice exam" })).toBeVisible();
    expect(screen.getByText(/never count towards course completion/)).toBeInTheDocument();
    expect(screen.getByText(/keeps counting down even if you leave this page/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Start exam" }));
    expect(shopApi.startAttempt).toHaveBeenCalledWith("calm-foundations", 9);
    const timer = await screen.findByRole("timer");
    expect(timer).toHaveTextContent(/(10:00|9:5\d)/);
    expect(timer).toHaveAccessibleName(/Time remaining:/);
    expect(document.body.textContent).not.toMatch(/Breathing slows the stress response/);
    expect(screen.getByRole("heading", { name: "Question 1 of 2" })).toBeInTheDocument();

    await user.click(screen.getByLabelText("Breathing"));
    await waitFor(
      () =>
        expect(shopApi.saveAttemptAnswers).toHaveBeenCalledWith("calm-foundations", 9, 40, {
          b11: "b",
        }),
      { timeout: 4000 },
    );
    expect(await screen.findByText("All answers saved.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByLabelText("True"));
    const nav = screen.getByRole("navigation", { name: "Questions" });
    expect(within(nav).getByRole("button", { name: "Question 1, answered" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review and submit" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Submit your answers?" });
    expect(confirm).toHaveTextContent("Every question has an answer.");
    await user.click(within(confirm).getByRole("button", { name: "Yes, submit" }));
    await waitFor(() =>
      expect(shopApi.submitStartedAttempt).toHaveBeenCalledWith("calm-foundations", 9, 40, {
        b11: "b",
        b12: "true",
      }),
    );
    // The result is shown (and repeated in the collapsed attempt history below).
    expect((await screen.findAllByText(/Passed: 100%/))[0]).toBeVisible();
    expect(screen.getAllByText("Breathing slows the stress response.")[0]).toBeVisible();
    expect(
      screen.getAllByText(/this score doesn't count towards course completion/)[0],
    ).toBeVisible();
    expect(screen.getByRole("region", { name: "Your previous attempts" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start a new attempt" })).toBeInTheDocument();
  });

  it("submits the saved answers when the server-side time runs out", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learnerApi({ secondsLeft: 1 });
    renderApp(EXAM, { shopApi });
    await user.click(await screen.findByRole("button", { name: "Start exam" }));
    await waitFor(
      () =>
        expect(shopApi.submitStartedAttempt).toHaveBeenCalledWith(
          "calm-foundations",
          9,
          40,
          undefined,
        ),
      { timeout: 5000 },
    );
    expect((await screen.findAllByText(/Time ran out on this attempt/))[0]).toBeVisible();
  }, 10_000);

  it("shows why an attempt can't start", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learnerApi();
    shopApi.startAttempt.mockImplementationOnce(() =>
      Promise.reject(
        new ApiError({
          status: 409,
          code: "attempts_exhausted",
          message: "You have used all attempts for this assessment.",
        }),
      ),
    );
    renderApp(EXAM, { shopApi });
    await user.click(await screen.findByRole("button", { name: "Start exam" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You have used all attempts for this assessment.",
    );
  });
});

describe("assessment history", () => {
  it("shows practice and graded results per course with a loading state", async () => {
    signIn();
    renderApp("/account/learning/history", { shopApi: learnerApi() });
    expect(await screen.findByText("Loading your results…")).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: /Assessments in Calm Foundations/ });
    const practice = within(table).getByRole("rowheader", { name: /Calm practice exam/ });
    expect(practice).toHaveTextContent("Practice — doesn't count towards completion");
    expect(within(table).getByText("Best 100%")).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: /Check-in/ })).toHaveTextContent(
      "Graded quiz",
    );
    expect(screen.getByRole("link", { name: "Morning reflection" })).toHaveAttribute(
      "href",
      ASSIGNMENT,
    );
    expect(screen.getByRole("link", { name: "Results" })).toHaveAttribute(
      "href",
      "/account/learning/history",
    );
  });

  it("offers a retry when results can't be loaded", async () => {
    signIn();
    const shopApi = learnerApi();
    shopApi.learning = vi.fn(() =>
      Promise.reject(new ApiError({ status: 500, code: "http_error", message: "Down" })),
    );
    renderApp("/account/learning/history", { shopApi });
    expect(await screen.findByText("We couldn't load your results")).toBeInTheDocument();
  });
});

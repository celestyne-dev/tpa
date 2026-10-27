import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { redirectTo } from "@/commerce/hooks";
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
});

function learner(options) {
  return { ...createFakeShopApi({ customer: customerProfile() }), ...createCourseShopApi(options) };
}

describe("public course catalogue", () => {
  it("lists courses with search, access and level filters", async () => {
    const user = userEvent.setup();
    renderApp("/courses");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Learn at your own pace" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Calm Foundations" })).toHaveAttribute(
      "href",
      "/courses/calm-foundations",
    );
    expect(screen.getByText("USD 49.00")).toBeInTheDocument();
    expect(screen.getByText("2 courses")).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "Free or premium" }), "premium");
    expect(screen.getByText("1 course")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Calm Foundations" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Free or premium" }), "");

    await user.type(screen.getByRole("searchbox", { name: "Search courses" }), "resilience");
    expect(screen.getByText("1 course")).toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox", { name: "Search courses" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Level" }), "beginner");
    expect(screen.getByRole("link", { name: "Calm Foundations" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Resilience Course" })).not.toBeInTheDocument();
  });

  it("shows outcomes, the outline (titles only), price and structured data", async () => {
    renderApp("/courses/resilience-course");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Resilience Course" }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "What you'll learn" })).toBeInTheDocument();
    expect(screen.getByText("Pause before reacting")).toBeInTheDocument();
    const outline = screen.getByRole("heading", { name: "Course outline" }).closest("section");
    expect(within(outline).getByText("Breathe")).toBeInTheDocument();
    expect(within(outline).getByRole("link", { name: /Free preview/ })).toHaveAttribute(
      "href",
      "/learn/resilience-course/notice-the-pause",
    );
    expect(screen.getAllByText("USD 49.00").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Add to cart/ })).toBeInTheDocument();
    expect(screen.getByText(/not an accredited qualification/)).toBeInTheDocument();
    await waitFor(() => {
      const scripts = [...document.head.querySelectorAll('script[type="application/ld+json"]')];
      const course = scripts
        .map((s) => JSON.parse(s.textContent))
        .find((d) => d["@type"] === "Course");
      expect(course).toMatchObject({ name: "Resilience Course", isAccessibleForFree: false });
      expect(course.offers[0]).toMatchObject({ price: "49.00", priceCurrency: "USD" });
    });
  });

  it("sends signed-out visitors to log in before enrolling in a free course", async () => {
    const user = userEvent.setup();
    renderApp("/courses/calm-foundations");
    await user.click(await screen.findByRole("button", { name: "Enrol for free" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Log in" })).toBeVisible();
  });

  it("enrols a verified customer and opens the course", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learner({ enrolled: false });
    renderApp("/courses/calm-foundations", { shopApi });
    await user.click(await screen.findByRole("button", { name: "Enrol for free" }));
    await waitFor(() => expect(shopApi.enroll).toHaveBeenCalledWith("calm-foundations"));
    expect(await screen.findByRole("progressbar", { name: "Course progress" })).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
    expect(screen.getByRole("heading", { level: 1, name: "Calm Foundations" })).toBeVisible();
  });

  it("offers Continue learning to enrolled learners instead of enrolling again", async () => {
    signIn();
    renderApp("/courses/calm-foundations", { shopApi: learner({ enrolled: true }) });
    expect(await screen.findByRole("link", { name: /Continue learning/ })).toHaveAttribute(
      "href",
      "/learn/calm-foundations",
    );
    expect(screen.queryByRole("button", { name: "Enrol for free" })).not.toBeInTheDocument();
  });
});

describe("learning", () => {
  it("reads a lesson: exercises gate completion, downloads use secure links", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learner({ enrolled: true });
    shopApi.authorizeDownload = vi.fn(() =>
      Promise.resolve({ data: { url: "/api/v1/downloads/token" } }),
    );
    const go = redirectTo.go;
    redirectTo.go = vi.fn();
    try {
      renderApp("/learn/calm-foundations/notice-the-pause", { shopApi });
      expect(
        await screen.findByRole("heading", { level: 1, name: "Notice the pause" }),
      ).toBeVisible();
      expect(screen.getByText("Slow down")).toBeInTheDocument();
      const complete = screen.getByRole("button", { name: /Complete and continue/ });
      expect(complete).toBeDisabled();

      await user.type(screen.getByLabelText("Your notes (private)"), "Sky, tree, cup");
      await user.click(screen.getByRole("checkbox", { name: "I've done this exercise" }));
      await waitFor(() =>
        expect(shopApi.saveExercise).toHaveBeenCalledWith(
          "calm-foundations",
          "notice-the-pause",
          "three-things",
          { done: true, response: "Sky, tree, cup" },
        ),
      );
      await waitFor(() => expect(complete).toBeEnabled());

      await user.click(screen.getByRole("button", { name: /Download/ }));
      await waitFor(() => expect(shopApi.authorizeDownload).toHaveBeenCalledWith(5, 9));
      expect(redirectTo.go).toHaveBeenCalledWith("/api/v1/downloads/token");

      // Text size is adjustable.
      await user.click(screen.getByRole("button", { name: "Larger text" }));
      expect(screen.getByText("Text L")).toBeInTheDocument();

      await user.click(complete);
      await waitFor(() => expect(shopApi.completeLesson).toHaveBeenCalled());
    } finally {
      redirectTo.go = go;
    }
  });

  it("submits a quiz and announces the result with explanations", async () => {
    signIn();
    const user = userEvent.setup();
    const shopApi = learner({ enrolled: true });
    renderApp("/learn/calm-foundations/notice-the-pause", { shopApi });
    await screen.findByRole("heading", { level: 2, name: "Check-in" });
    await user.click(screen.getByRole("radio", { name: "Rush" }));
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    expect(await screen.findByText(/Not passed yet: 0%/)).toBeInTheDocument();
    expect(screen.getByText("Correct answer: Pause")).toBeInTheDocument();
    expect(screen.getByText("Pausing first helps.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await user.click(screen.getByRole("radio", { name: "Pause" }));
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    expect(await screen.findByText(/Passed: 100%/)).toBeInTheDocument();
    expect(shopApi.submitAttempt).toHaveBeenLastCalledWith("calm-foundations", 7, { 71: "b" });
  });

  it("explains how to start when not enrolled or not verified", async () => {
    signIn();
    renderApp("/learn/calm-foundations", { shopApi: learner({ enrolled: false }) });
    expect(await screen.findByText("You're not enrolled in this course yet")).toBeVisible();
  });

  it("asks unverified accounts to confirm their email", async () => {
    signIn();
    renderApp("/account/learning", { shopApi: learner({ verified: false }) });
    expect(await screen.findByText("Confirm your email to start learning")).toBeVisible();
  });

  it("shows free preview lessons to visitors", async () => {
    renderApp("/learn/calm-foundations/notice-the-pause");
    expect(await screen.findByText("A free sample lesson.")).toBeVisible();
    expect(screen.getByText("Free preview")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the course" })).toHaveAttribute(
      "href",
      "/courses/calm-foundations",
    );
  });

  it("lists enrolled courses in My learning", async () => {
    signIn();
    renderApp("/account/learning", { shopApi: learner({ enrolled: true }) });
    expect(
      await screen.findByRole("heading", { level: 2, name: "Calm Foundations" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Start" })).toHaveAttribute(
      "href",
      "/learn/calm-foundations/notice-the-pause",
    );
    expect(screen.getByRole("link", { name: "My learning" })).toBeInTheDocument();
  });

  it("verifies certificates publicly", async () => {
    renderApp("/certificates/TPA-AAAA-BBBB-CCCC");
    expect(await screen.findByText("Valid certificate")).toBeVisible();
    expect(screen.getByText("Ada Reader")).toBeInTheDocument();
    expect(screen.getByText(/not an accredited qualification/)).toBeInTheDocument();
  });

  it("reports unknown certificate codes", async () => {
    renderApp("/certificates/TPA-XXXX-XXXX-XXXX");
    expect(await screen.findByText(/No certificate matches this ID/)).toBeVisible();
  });
});

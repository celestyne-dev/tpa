import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

describe("courses module", () => {
  it("is a real section in the admin navigation, with a real-data dashboard", async () => {
    renderApp("/admin/courses");
    expect(await screen.findByRole("heading", { level: 1, name: "Courses" })).toBeVisible();
    const nav = screen.getAllByRole("navigation", { name: "Admin" })[0];
    expect(within(nav).getByRole("link", { name: "Courses" })).toHaveAttribute(
      "href",
      "/admin/courses",
    );
    const stats = await screen.findByRole("region", { name: "Course statistics" });
    expect(within(stats).getByText("25% completion rate · 1 certificates")).toBeInTheDocument();
    expect(within(stats).getByRole("table", { name: "Quiz pass rates" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Calm Foundations/ })).toHaveAttribute(
      "href",
      "/admin/courses/3",
    );
  });

  it("creates a course from the dialog (and from /admin/courses/new)", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/courses/new");
    const dialog = await screen.findByRole("dialog", { name: "New course" });
    await user.type(within(dialog).getByLabelText(/Title/), "Sleep Better");
    await user.click(within(dialog).getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(adminApi.courses.create).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Sleep Better", access_type: "free" }),
      ),
    );
  });

  it("hides actions a limited role can't take", async () => {
    renderApp("/admin/courses", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    expect(await screen.findByRole("heading", { level: 1, name: "Courses" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /New course/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Categories/ })).not.toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Course statistics" })).toBeInTheDocument();
  });

  it("blocks roles without courses.view", async () => {
    renderApp("/admin/courses", { adminApi: createFakeAdminApi({ role: "moderator" }) });
    expect(await screen.findByText("You don't have access to this area")).toBeVisible();
  });

  it("edits details and publishes with readiness checks", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/courses/3");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Calm Foundations" }),
    ).toBeVisible();
    expect(screen.getByText(/still drafts/)).toBeInTheDocument();
    const subtitle = screen.getByLabelText("Subtitle");
    await user.type(subtitle, "Calmer mornings");
    await user.click(screen.getByRole("button", { name: "Save course" }));
    await waitFor(() =>
      expect(adminApi.courses.update).toHaveBeenCalledWith(
        3,
        expect.objectContaining({
          subtitle: "Calmer mornings",
          lock_version: 1,
          outcomes: ["Pause"],
        }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Publish" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish course" });
    await user.click(within(dialog).getByRole("button", { name: "Publish now" }));
    await waitFor(() => expect(adminApi.courses.action).toHaveBeenCalledWith(3, "publish", {}));
  });

  it("reorders the curriculum with accessible controls and edits lessons with lesson blocks", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/courses/3/content");
    await user.click(await screen.findByRole("button", { name: "Move lesson Breathe up" }));
    await waitFor(() =>
      expect(adminApi.courses.reorder).toHaveBeenCalledWith(3, [
        { module_id: 1, lesson_ids: [12, 11] },
        { module_id: 2, lesson_ids: [] },
      ]),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Move Notice the pause to module" }),
      "2",
    );
    await waitFor(() =>
      expect(adminApi.courses.reorder).toHaveBeenLastCalledWith(3, [
        { module_id: 1, lesson_ids: [12] },
        { module_id: 2, lesson_ids: [11] },
      ]),
    );
    await user.click(screen.getByRole("button", { name: /^Breathe/ }));
    expect(await screen.findByRole("heading", { name: "Edit lesson: Breathe" })).toBeVisible();
    const add = screen.getByRole("group", { name: "Add a block" });
    expect(within(add).getByRole("button", { name: /Exercise \/ reflection/ })).toBeInTheDocument();
    expect(within(add).queryByRole("button", { name: /Video/ })).not.toBeInTheDocument();
    await user.click(within(add).getByRole("button", { name: /Key points/ }));
    await user.click(screen.getByRole("button", { name: "Save lesson" }));
    await waitFor(() => expect(adminApi.courses.updateLesson).toHaveBeenCalled());
  });

  it("keeps answer keys from roles that can't manage assessments", async () => {
    const user = userEvent.setup();
    renderApp("/admin/courses/3/assessments", {
      adminApi: createFakeAdminApi({ role: "analyst" }),
    });
    await user.click(await screen.findByRole("button", { name: /Check-in/ }));
    expect(await screen.findByText(/Answer keys are hidden for your role/)).toBeVisible();
  });

  it("previews the course page privately, drafts included", async () => {
    renderApp("/admin/courses/3/preview");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Preview: Calm Foundations" }),
    ).toBeVisible();
    expect(screen.getByText("Preview: enrolment actions appear here.")).toBeInTheDocument();
  });
});

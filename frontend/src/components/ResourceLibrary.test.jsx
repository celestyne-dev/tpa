import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderApp } from "@/test/utils";

describe("resource library", () => {
  it("lists written resources by type and access without converting prices", async () => {
    const user = userEvent.setup();
    renderApp("/resources");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Written resources for your growth" }),
    ).toBeVisible();
    expect(await screen.findByText("4 resources")).toBeVisible();
    const types = screen.getByRole("group", { name: "Type" });
    expect(within(types).getByRole("button", { name: "All types" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(within(types).getByRole("button", { name: "Workbook" }));
    expect(screen.getByText("1 resource")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Calm Mornings Workbook" })).toBeVisible();
    expect(screen.getByText("USD 15.00")).toBeVisible();
    await user.click(within(types).getByRole("button", { name: "All types" }));
    const access = screen.getByRole("group", { name: "Access" });
    await user.click(within(access).getByRole("button", { name: "Free" }));
    expect(screen.getByText("1 resource")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Gratitude Worksheet" })).toBeVisible();
    expect(screen.getByText(/we never convert them/)).toBeVisible();
  });

  it("shows a resource's access terms on its page", async () => {
    renderApp("/shop/calm-mornings-workbook");
    expect(await screen.findByText("365-day access · 5 downloads")).toBeVisible();
  });
});

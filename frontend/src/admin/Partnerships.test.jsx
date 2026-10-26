import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

const sidebar = () => screen.getAllByRole("navigation", { name: "Admin" })[0];

describe("partnership admin", () => {
  it("gives the Partnership Manager CRM and sponsorships but not finance or reports", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "partnerships_manager" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    const nav = sidebar();
    for (const label of ["Partners", "Partnership inquiries", "Sponsorships", "Media kit"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(
      within(nav).queryByRole("link", { name: "Partnership reports" }),
    ).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Affiliates" })).not.toBeInTheDocument();
  });

  it("hides every partnership module from content writers", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "content_writer" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    const nav = sidebar();
    for (const label of ["Partners", "Sponsorships", "Affiliates", "Partnership reports"]) {
      expect(within(nav).queryByRole("link", { name: label })).not.toBeInTheDocument();
    }
  });

  it("lists partners and opens the sponsorship tabs allowed for the role", async () => {
    const adminApi = createFakeAdminApi({ role: "partnerships_manager" });
    renderApp("/admin/partners", { adminApi });
    expect(await screen.findByRole("button", { name: "Calm Co" })).toBeInTheDocument();
    renderApp("/admin/sponsorships", { adminApi });
    const tabs = await screen.findAllByRole("tab");
    const names = tabs.map((t) => t.textContent);
    expect(names).toEqual(expect.arrayContaining(["Opportunities", "Campaigns", "Bookings"]));
    expect(names).not.toContain("Invoices & payments");
  });

  it("reports each currency on its own row for finance", async () => {
    renderApp("/admin/partnership-reports", {
      adminApi: createFakeAdminApi({ role: "finance_manager" }),
    });
    const kes = (await screen.findAllByText("KES 50,000.00"))[0].closest("tr");
    expect(within(kes).getByText("KES 30,000.00")).toBeInTheDocument(); // outstanding
    const usd = screen.getByText("USD 9,000.00").closest("tr");
    expect(within(usd).queryByText(/KES/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Export CSV/ })).toBeInTheDocument();
    expect(screen.getByText("Pipeline values are expectations, not revenue.")).toBeInTheDocument();
  });

  it("offers sponsorship marking on an article for sponsorship roles", async () => {
    const adminApi = createFakeAdminApi();
    const user = userEvent.setup();
    renderApp("/admin/articles/7/edit", { adminApi });
    await user.click(await screen.findByRole("tab", { name: "Sponsorship" }));
    await user.click(await screen.findByRole("button", { name: "Mark as sponsored content" }));
    expect(screen.getByLabelText(/Disclosure shown to readers/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Paid outbound links/)).toBeInTheDocument();
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

const sidebar = () => screen.getAllByRole("navigation", { name: "Admin" })[0];

describe("commerce navigation", () => {
  it("shows the Commerce section and payment settings to a Super Admin", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi() });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    const nav = sidebar();
    for (const label of [
      "Products",
      "Categories & Collections",
      "Bundles",
      "Orders",
      "Customers",
      "Download Entitlements",
      "Revenue Reports",
      "Payment Settings",
    ]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("hides commerce modules from editorial roles", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "editor" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    const nav = sidebar();
    expect(within(nav).queryByRole("link", { name: "Orders" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Products" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Payment Settings" })).not.toBeInTheDocument();
  });

  it("gives Customer Support orders and customers but not reports or payment settings", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "customer_support" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    const nav = sidebar();
    expect(within(nav).getByRole("link", { name: "Orders" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Customers" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Revenue Reports" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Payment Settings" })).not.toBeInTheDocument();
  });

  it("blocks direct visits to pages a role cannot use", async () => {
    renderApp("/admin/payments", { adminApi: createFakeAdminApi({ role: "editor" }) });
    expect(
      await screen.findByRole("heading", { name: /access denied|don't have access/i }),
    ).toBeInTheDocument();
  });
});

describe("product management", () => {
  it("lists products with their setup problems and creates drafts", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    renderApp("/admin/products", { adminApi });
    expect(await screen.findByRole("link", { name: "Calm Mornings Workbook" })).toBeInTheDocument();
    expect(screen.getByText(/No deliverable files uploaded\./)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /New product/ }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Title/), "Evening Journal");
    expect(within(dialog).getByRole("option", { name: "Online course (planned)" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(adminApi.products.create).toHaveBeenCalledWith({
        title: "Evening Journal",
        product_type: "ebook",
      }),
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "Evening Journal" }),
    ).toBeInTheDocument();
  });

  it("saves prices as exact minor units with the currency", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    renderApp("/admin/products/1", { adminApi });
    await user.click(await screen.findByRole("tab", { name: "Pricing" }));
    await user.type(screen.getByLabelText(/Price \(USD\)/), "12.50");
    await user.type(screen.getByLabelText(/Compare-at price/), "19.99");
    await user.click(screen.getByRole("button", { name: "Save price" }));
    await waitFor(() =>
      expect(adminApi.products.setPrice).toHaveBeenCalledWith(1, {
        currency: "USD",
        kind: "regular",
        amount_minor: 1250,
        compare_at_minor: 1999,
      }),
    );
    expect(await screen.findByText("USD 12.50")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Price \(USD\)/), "12.505");
    await user.click(screen.getByRole("button", { name: "Save price" }));
    expect(await screen.findByText(/at most 2 decimal places/)).toBeInTheDocument();
    expect(adminApi.products.setPrice).toHaveBeenCalledTimes(1);
  });

  it("shows prices read-only without the price permission", async () => {
    const user = userEvent.setup();
    renderApp("/admin/products/1", { adminApi: createFakeAdminApi({ role: "customer_support" }) });
    await user.click(await screen.findByRole("tab", { name: "Pricing" }));
    expect(screen.getByText("You can view prices but not change them.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save price" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
  });

  it("explains why a product cannot be published or a file was refused", async () => {
    const user = userEvent.setup();
    renderApp("/admin/products/1", { adminApi: createFakeAdminApi() });
    await user.click(await screen.findByRole("button", { name: "Publish" }));
    expect(
      await screen.findByText(/not ready to publish\. No deliverable files uploaded\./),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Files" }));
    expect(await screen.findByText(/Replacing a file adds a new version/)).toBeInTheDocument();
    const file = new File(["%PDF-1.4"], "workbook.pdf", { type: "application/pdf" });
    const form = screen.getByRole("form", { name: "Upload a new file" });
    await user.upload(within(form).getByLabelText("Choose a PDF, EPUB or ZIP file"), file);
    await user.click(within(form).getByRole("button", { name: "Upload a new file" }));
    expect(await screen.findByText(/active content \(JavaScript\)/)).toBeInTheDocument();
  });
});

describe("orders and refunds", () => {
  it("records a manual refund only after explicit confirmation", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi({ role: "finance_manager" });
    renderApp("/admin/orders/5", { adminApi });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Order TPA-261023-ABCDEF" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/TEST MODE/)).toBeInTheDocument();
    expect(screen.getByText(/Not sent \(development log only\)/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refund" }));
    const dialog = screen.getByRole("dialog");
    await user.clear(within(dialog).getByLabelText(/Amount/));
    await user.type(within(dialog).getByLabelText(/Amount/), "15.00");
    await user.type(within(dialog).getByLabelText(/Reason/), "Customer request");
    await user.click(within(dialog).getByRole("button", { name: "Request refund" }));
    await waitFor(() => expect(adminApi.orders.refund).toHaveBeenCalled());
    const body = adminApi.orders.refund.mock.calls[0][1];
    expect(body).toMatchObject({
      amount_minor: 1500,
      reason: "Customer request",
      revoke_access: true,
    });
    expect(body.idempotency_key).toMatch(/^[0-9a-f]{32}$/);
    expect((await screen.findAllByText(/Awaiting manual refund/)).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Record completed refund" }));
    const confirm = screen.getByRole("dialog");
    await user.type(within(confirm).getByLabelText(/Paystack refund reference/), "RF_1");
    expect(within(confirm).getByRole("button", { name: "Record as refunded" })).toBeDisabled();
    await user.click(within(confirm).getByRole("checkbox"));
    await user.click(within(confirm).getByRole("button", { name: "Record as refunded" }));
    await waitFor(() =>
      expect(adminApi.orders.refundAction).toHaveBeenCalledWith(5, 1, "complete", {
        provider_reference: "RF_1",
        confirm: true,
      }),
    );
  });

  it("does not offer refunds to Customer Support", async () => {
    renderApp("/admin/orders/5", { adminApi: createFakeAdminApi({ role: "customer_support" }) });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Order TPA-261023-ABCDEF" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Refund" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resend receipt" })).not.toBeInTheDocument();
  });
});

describe("payments and reports", () => {
  it("shows payment configuration without any secret values", async () => {
    renderApp("/admin/payments", { adminApi: createFakeAdminApi() });
    expect(await screen.findByText("Configured · test mode")).toBeInTheDocument();
    // Readiness labels may name the key prefix, but never a key value.
    expect(document.body.textContent).not.toMatch(/sk_(test|live)_[A-Za-z0-9]/);
    expect(
      screen.getByText("https://example.com/api/v1/payments/paystack/webhook"),
    ).toBeInTheDocument();
    expect(screen.getByText("Live activation checklist")).toBeInTheDocument();
  });

  it("lets other permitted roles review events but not configure payments", async () => {
    renderApp("/admin/payments", { adminApi: createFakeAdminApi({ role: "orders_manager" }) });
    expect(
      await screen.findByText(/Only a Super Admin can change payment settings/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save payment settings" })).not.toBeInTheDocument();
  });

  it("reports each currency separately and labels test figures", async () => {
    const user = userEvent.setup();
    renderApp("/admin/reports/revenue", {
      adminApi: createFakeAdminApi({ role: "finance_manager" }),
    });
    expect(await screen.findByText(/No live orders in this period/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Payments"), "test");
    expect(await screen.findByRole("heading", { name: "USD" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "KES" })).toBeInTheDocument();
    expect(screen.getByText("Test-mode figures: no real money was received.")).toBeInTheDocument();
    expect(screen.getByText("USD 10.00")).toBeInTheDocument();
    expect(screen.getByText(/never added together/)).toBeInTheDocument();
  });
});

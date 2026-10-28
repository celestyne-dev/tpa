import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

describe("premium resources admin", () => {
  it("lists resources with access terms and creates new ones from resource types only", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    renderApp("/admin/resources", { adminApi });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Premium resources" }),
    ).toBeVisible();
    expect(adminApi.products.list).toHaveBeenCalledWith({ group: "resources" });
    const table = await screen.findByRole("table", { name: "Premium resources" });
    expect(within(table).getByText("Premium · Lifetime access")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Access"), "free");
    await waitFor(() =>
      expect(adminApi.products.list).toHaveBeenLastCalledWith({
        group: "resources",
        access: "free",
      }),
    );
    await user.click(screen.getByRole("button", { name: /New resource/ }));
    const typeSelect = screen.getByLabelText("Resource type");
    const options = within(typeSelect)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["eBook", "Workbook", "Template"]); // no bundles, no planned types
  });

  it("saves access rules separately and related resources with the draft", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    renderApp("/admin/products/1", { adminApi });
    await user.click(await screen.findByRole("tab", { name: "Access & related" }));
    await user.type(screen.getByLabelText(/Access period/), "365");
    await user.type(screen.getByLabelText(/Downloads per buyer/), "5");
    await user.click(screen.getByLabelText(/included in membership plans/));
    await user.click(screen.getByRole("button", { name: "Save access rules" }));
    await waitFor(() =>
      expect(adminApi.products.update).toHaveBeenCalledWith(1, {
        access_days: 365,
        download_limit: 5,
        membership_eligible: true,
      }),
    );
    expect(screen.getByRole("heading", { name: "Related resources" })).toBeVisible();
    expect(screen.getByText(/None chosen/)).toBeVisible();
  });
});

describe("media library premium files", () => {
  it("shows protected files with usage, filters by format and explains deletion rules", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    renderApp("/admin/media?tab=premium", { adminApi });
    const table = await screen.findByRole("table", { name: "Premium files" });
    expect(within(table).getByText("Workbook (PDF)")).toBeInTheDocument();
    expect(within(table).getByText("Workbooks & planners")).toBeInTheDocument();
    expect(within(table).getByText("12")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Format"), "xlsx");
    await waitFor(() =>
      expect(adminApi.premiumFiles.list).toHaveBeenLastCalledWith({
        format: "xlsx",
        sort: "newest",
      }),
    );
    await user.selectOptions(screen.getByLabelText("Format"), "");
    await user.click(await screen.findByRole("button", { name: /Workbook \(PDF\)/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/never available at a public address/)).toBeVisible();
    expect(
      within(dialog).getByText("Buyers received this version; it is kept for them."),
    ).toBeVisible();
    // Only the unused old version offers deletion.
    const deletes = within(dialog).getAllByRole("button", { name: "Delete" });
    expect(deletes).toHaveLength(1);
    await user.click(deletes[0]);
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(adminApi.premiumFiles.removeVersion).toHaveBeenCalledWith(11, 111));
    expect(within(dialog).getByText(/Archive it instead/)).toBeVisible();
  });

  it("keeps the images tab with categories for uploads and filters", async () => {
    const adminApi = createFakeAdminApi();
    adminApi.media.stats.mockResolvedValue({
      data: {
        assets: 1,
        variants_bytes: 1000,
        originals_bytes: 1000,
        superseded_bytes: 0,
        max_upload_mb: 20,
        categories: [
          { key: "general", label: "General" },
          { key: "resources", label: "Resource covers & previews" },
        ],
        category_counts: { general: 1 },
      },
    });
    renderApp("/admin/media", { adminApi });
    expect(await screen.findByRole("tab", { name: "Images", selected: true })).toBeVisible();
    expect(await screen.findByLabelText("Category for new uploads")).toHaveValue("general");
    expect(screen.getByRole("option", { name: "General (1)" })).toBeInTheDocument();
  });
});

describe("storage health", () => {
  it("shows disk space, findings, backups and upload errors", async () => {
    renderApp("/admin/storage");
    expect(await screen.findByText("Storage needs attention soon.")).toBeVisible();
    expect(screen.getByText(/Disk space is getting low/)).toBeVisible();
    const areas = screen.getByRole("table", { name: "Storage areas" });
    expect(within(areas).getByText("/var/lib/tpa/resources/private")).toBeInTheDocument();
    expect(within(areas).getAllByRole("meter", { name: "Disk used" })).toHaveLength(4);
    expect(screen.getByText(/encrypted copy stored off the server/)).toBeVisible();
    const errors = await screen.findByRole("table", { name: "Recent upload errors" });
    expect(within(errors).getByText("planner.docm.docx")).toBeInTheDocument();
    expect(within(errors).getByText("File refused")).toBeInTheDocument();
  });

  it("is hidden from roles without storage access", async () => {
    renderApp("/admin/storage", { adminApi: createFakeAdminApi({ role: "editor" }) });
    expect(
      await screen.findByRole("heading", { name: "You don't have access to this area" }),
    ).toBeVisible();
    expect(screen.queryByText("Storage areas")).not.toBeInTheDocument();
  });
});

describe("download activity", () => {
  it("summarises the last 30 days with readable refusal reasons", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    renderApp("/admin/entitlements", { adminApi });
    await user.click(await screen.findByRole("tab", { name: "Download activity" }));
    expect(await screen.findByText("Last 30 days")).toBeVisible();
    expect(screen.getByText("Access period ended")).toBeVisible();
    expect(screen.getByText("Download limit reached")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Calm Mornings Workbook" }));
    await waitFor(() =>
      expect(adminApi.downloads.list).toHaveBeenLastCalledWith({ product_id: "1" }),
    );
  });
});

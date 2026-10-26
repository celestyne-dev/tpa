import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { createFakeAdminApi } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";

beforeAll(preloadAdminApp);

const image = (name = "sunrise.jpg", type = "image/jpeg") =>
  new File([new Uint8Array([1, 2, 3])], name, { type });

describe("admin navigation for Batch 03 features", () => {
  it("shows the content, website and administration tools to super admins", async () => {
    renderApp("/admin");
    const nav = await screen.findByRole("navigation", { name: /admin/i });
    for (const label of [
      "Media Library",
      "Editorial Workflow",
      "SEO",
      "Redirects",
      "Publishing Jobs",
    ])
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    expect(within(nav).queryByText("SEO tools")).not.toBeInTheDocument();
  });

  it("only shows what a content writer may use", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "content_writer" }) });
    const nav = await screen.findByRole("navigation", { name: /admin/i });
    expect(within(nav).getByRole("link", { name: "Media Library" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Editorial Workflow" })).toBeInTheDocument();
    for (const label of ["Redirects", "Publishing Jobs", "SEO"])
      expect(within(nav).queryByRole("link", { name: label })).not.toBeInTheDocument();
  });

  it("blocks direct access to pages without permission", async () => {
    renderApp("/admin/redirects", { adminApi: createFakeAdminApi({ role: "content_writer" }) });
    expect(await screen.findByText("You don't have access to this area")).toBeInTheDocument();
  });
});

describe("media library", () => {
  it("uploads several images with progress and shows the optimisation result", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/media");
    const input = await screen.findByTestId("media-file-input");
    await user.upload(input, [image("a.jpg"), image("b.png", "image/png")]);
    await waitFor(() => expect(adminApi.media.upload).toHaveBeenCalledTimes(2));
    const uploads = screen.getByRole("list", { name: "Uploads" });
    await waitFor(() =>
      expect(within(uploads).getAllByText(/Optimised: 2 versions/)).toHaveLength(2),
    );
    expect(adminApi.media.list.mock.calls.length).toBeGreaterThan(1); // grid refreshed
  });

  it("rejects unsupported files before uploading", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const { adminApi } = renderApp("/admin/media");
    await user.upload(await screen.findByTestId("media-file-input"), [
      image("vector.svg", "image/svg+xml"),
    ]);
    expect(await screen.findByText(/Unsupported file type/)).toBeInTheDocument();
    expect(adminApi.media.upload).not.toHaveBeenCalled();
  });

  it("filters the library and opens archived images", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/media");
    await screen.findByRole("list", { name: "Media" });
    await user.selectOptions(screen.getByLabelText("Usage"), "missing_alt");
    await waitFor(() =>
      expect(adminApi.media.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ usage: "missing_alt" }),
      ),
    );
    await user.selectOptions(screen.getByLabelText("Usage"), "");
    await user.selectOptions(screen.getByLabelText("Status"), "archived");
    expect(await screen.findByRole("button", { name: "Open Old sign" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Sort"), "size");
    await waitFor(() =>
      expect(adminApi.media.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: "size" }),
      ),
    );
  });

  it("edits alt text and protects images that are in use", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/media");
    await user.click(await screen.findByRole("button", { name: "Open Calm lake" }));
    const dialog = await screen.findByRole("dialog", { name: "Calm lake" });
    const alt = await within(dialog).findByLabelText(/Alt text/);
    await user.clear(alt);
    await user.type(alt, "Mist over a quiet lake");
    await user.click(within(dialog).getByRole("button", { name: "Save details" }));
    await waitFor(() =>
      expect(adminApi.media.update).toHaveBeenCalledWith(
        3,
        expect.objectContaining({ alt_text: "Mist over a quiet lake" }),
      ),
    );
    expect(within(dialog).getByText("Finding Calm")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /Delete permanently/ })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(adminApi.media.archive).toHaveBeenCalledWith(3));
  });

  it("hides upload and editing for read-only roles", async () => {
    const user = userEvent.setup();
    renderApp("/admin/media", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    await screen.findByRole("list", { name: "Media" });
    expect(screen.queryByTestId("media-file-input")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open Calm lake" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText(/Alt text/)).toBeDisabled();
    expect(within(dialog).queryByRole("button", { name: "Replace image" })).toBeNull();
    expect(within(dialog).queryByRole("button", { name: "Archive" })).toBeNull();
  });
});

describe("redirect manager", () => {
  it("lists, creates, validates and imports redirects", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/redirects");
    const table = await screen.findByRole("table", { name: "Redirects" });
    expect(within(table).getByText("/2019/05/old-post")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Export CSV/ })).toHaveAttribute(
      "href",
      "/api/v1/admin/redirects/export",
    );

    await user.click(screen.getByRole("button", { name: "Add redirect" }));
    let dialog = await screen.findByRole("dialog", { name: "Add redirect" });
    // Paths are pasted (one input event each) to keep this long flow fast under CPU load.
    await user.click(within(dialog).getByLabelText(/Old path/));
    await user.paste("/same");
    await user.click(within(dialog).getByLabelText(/Destination/));
    await user.paste("/same");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(
      await within(dialog).findByText("A path cannot redirect to itself."),
    ).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText(/Destination/));
    await user.paste("/articles/finding-calm");
    await user.selectOptions(within(dialog).getByLabelText("Redirect type"), "308");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(adminApi.redirects.create).toHaveBeenLastCalledWith(
        expect.objectContaining({
          source_path: "/same",
          destination: "/articles/finding-calm",
          status_code: 308,
        }),
      ),
    );

    await user.click(screen.getByRole("button", { name: "Import" }));
    dialog = await screen.findByRole("dialog", { name: "Import redirects" });
    await user.click(within(dialog).getByLabelText("CSV"));
    await user.paste("source_path,destination");
    await user.click(within(dialog).getByRole("button", { name: "Dry run" }));
    expect(
      await within(dialog).findByText(/1 valid row\(s\) would be imported/),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Row 2 \(\/admin\)/)).toBeInTheDocument();
  });

  it("is read-only for SEO viewers without redirects.manage", async () => {
    renderApp("/admin/redirects", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    await screen.findByRole("table", { name: "Redirects" });
    expect(screen.queryByRole("button", { name: "Add redirect" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit redirect/ })).not.toBeInTheDocument();
  });
});

describe("publishing jobs", () => {
  it("shows the live release, failures with logs, and retries", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp("/admin/publishing");
    expect(await screen.findByText(/20261020-100000-job1/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Publishing jobs" });
    await user.click(within(table).getAllByRole("button", { name: "Details" })[0]);
    expect(await screen.findByText("vite build failed")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(within(table).getByRole("button", { name: /Retry/ }));
    await waitFor(() => expect(adminApi.publishing.retry).toHaveBeenCalledWith(2));
    await user.click(screen.getByRole("button", { name: "Rebuild now" }));
    await waitFor(() => expect(adminApi.publishing.request).toHaveBeenCalled());
  });

  it("is view-only without publishing.manage", async () => {
    renderApp("/admin/publishing", { adminApi: createFakeAdminApi({ role: "editor" }) });
    await screen.findByRole("table", { name: "Publishing jobs" });
    expect(screen.queryByRole("button", { name: "Rebuild now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
  });
});

describe("SEO dashboard", () => {
  it("reports real audit data and links to the affected articles", async () => {
    renderApp("/admin/seo", { adminApi: createFakeAdminApi({ role: "analyst" }) });
    expect(await screen.findByText("Published articles needing attention")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quiet Confidence" })).toHaveAttribute(
      "href",
      "/admin/articles/8/edit",
    );
    expect(screen.getByText(/does not point to a published page/)).toBeInTheDocument();
    expect(screen.getByText(/No \(robots.txt disallows crawling\)/)).toBeInTheDocument();
    expect(screen.getByText(/Search Console data is not connected/)).toBeInTheDocument();
  });
});

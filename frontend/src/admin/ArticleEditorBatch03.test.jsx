import { act, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/apiClient";
import { createFakeAdminApi, makeArticle, manualSave } from "@/test/adminFake";
import { preloadAdminApp, renderApp } from "@/test/utils";
import { useAutosave } from "./hooks/useAutosave";

beforeAll(preloadAdminApp);

const EDIT = "/admin/articles/7/edit";

describe("article editor sections", () => {
  it("organises the editor in tabs and shows word count and draft status", async () => {
    const user = userEvent.setup();
    renderApp(EDIT);
    const tabs = await screen.findByRole("tablist", { name: "Editor sections" });
    expect(
      within(tabs)
        .getAllByRole("tab")
        .map((t) => t.textContent),
      // The default Super Admin holds sponsorships.view, so the Sponsorship tab is shown.
    ).toEqual(["Content", "Details", "SEO1", "Sponsorship", "History"]);
    expect(screen.getByText(/2 words · 1 min read/)).toBeInTheDocument();
    expect(screen.getByText("Draft — not visible on the website")).toBeInTheDocument();
    await user.click(within(tabs).getByRole("tab", { name: "Details" }));
    expect(screen.getByLabelText("Author")).toBeInTheDocument();
    expect(screen.queryByLabelText(/^Title/)).not.toBeInTheDocument();
  });

  it("selects a featured image from the media library", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(EDIT, {
      adminApi: createFakeAdminApi({ article: makeArticle({ featured_image_id: null }) }),
    });
    await user.click(await screen.findByRole("tab", { name: "Details" }));
    await user.click(screen.getByRole("button", { name: "Choose featured image" }));
    const picker = await screen.findByRole("dialog", { name: "Choose an image" });
    await user.click(await within(picker).findByRole("button", { name: "Select Calm lake" }));
    expect(screen.queryByRole("dialog", { name: "Choose an image" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(adminApi.articles.update).toHaveBeenCalledWith(
        "7",
        expect.objectContaining({ featured_image_id: 3, lock_version: 1 }),
      ),
    );
  });

  it("adds, duplicates and saves new block types", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(EDIT);
    const add = await screen.findByRole("group", { name: "Add a block" });
    await user.click(within(add).getByRole("button", { name: "Pull quote" }));
    await user.type(screen.getByLabelText("Pull quote 2 text"), "Small steps count.");
    await user.click(screen.getByRole("button", { name: "Duplicate block 2" }));
    await user.click(within(add).getByRole("button", { name: "Video" }));
    await user.click(screen.getByLabelText("Video 4 link"));
    await user.paste("https://youtu.be/dQw4w9WgXcQ"); // links are pasted, not typed
    await user.type(screen.getByLabelText("Video title"), "A short talk");
    await user.click(within(add).getByRole("button", { name: "Table" }));
    await user.type(screen.getByLabelText("Table 5 row 1 column 1"), "Habit");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(manualSave(adminApi.articles.update)).toBeDefined());
    const { body } = manualSave(adminApi.articles.update)[1];
    expect(body.map((b) => b.type)).toEqual([
      "paragraph",
      "pullquote",
      "pullquote",
      "video",
      "table",
    ]);
    expect(body[3]).toEqual({
      type: "video",
      url: "https://youtu.be/dQw4w9WgXcQ",
      title: "A short talk",
    });
    expect(body[4].rows[0][0]).toBe("Habit");
  });

  it("autosaves after a pause and reports the status", async () => {
    const { adminApi } = renderApp(EDIT);
    const title = await screen.findByLabelText(/^Title/);
    // Drive the 2.5 s debounce with fake timers so the test doesn't depend on machine speed.
    vi.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.type(title, " today");
    expect(screen.getByTestId("autosave-status")).toHaveTextContent("Unsaved changes");
    await act(() => vi.advanceTimersByTimeAsync(2400));
    expect(adminApi.articles.update).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(adminApi.articles.update).toHaveBeenCalledTimes(1); // debounced, not per keystroke
    expect(adminApi.articles.update).toHaveBeenCalledWith(
      "7",
      expect.objectContaining({ mode: "autosave", title: "Finding Calm today" }),
    );
    vi.useRealTimers();
    await waitFor(() =>
      expect(screen.getByTestId("autosave-status")).toHaveTextContent("All changes saved"),
    );
  });

  it("explains edit conflicts instead of overwriting newer work", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi();
    adminApi.articles.update = vi.fn(() =>
      Promise.reject(
        new ApiError({
          status: 409,
          code: "edit_conflict",
          message: "This article was changed by someone else since you opened it.",
          details: { lock_version: 5, updated_by: "Ngozi" },
        }),
      ),
    );
    renderApp(EDIT, { adminApi });
    await user.type(await screen.findByLabelText(/^Title/), "!");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const dialog = await screen.findByRole("dialog", { name: "Someone else changed this article" });
    expect(within(dialog).getByText(/Last saved by Ngozi/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Load their version" }));
    await waitFor(() => expect(adminApi.articles.get).toHaveBeenCalledTimes(2));
  });
});

describe("revision history", () => {
  it("lists, compares and restores revisions", async () => {
    const user = userEvent.setup();
    const { adminApi } = renderApp(EDIT);
    await user.click(await screen.findByRole("tab", { name: "History" }));
    expect(await screen.findByText("Changed title")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Select revision 2"));
    await user.click(screen.getByLabelText("Select revision 1"));
    await user.click(screen.getByRole("button", { name: /Compare selected/ }));
    const diff = await screen.findByRole("region", { name: "Revision comparison" });
    expect(within(diff).getByText("Old title")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restore" }));
    const confirm = await screen.findByRole("dialog", { name: "Restore revision #1?" });
    await user.click(within(confirm).getByRole("button", { name: "Restore revision" }));
    await waitFor(() => expect(adminApi.articles.restoreRevision).toHaveBeenCalledWith(7, 11, 1));
    expect(await screen.findByText("Restored revision #1")).toBeInTheDocument();
  });

  it("hides history from roles without revision access", async () => {
    renderApp(EDIT, { adminApi: createFakeAdminApi({ role: "pages_only" }) });
    expect(await screen.findByText("You don't have access to this area")).toBeInTheDocument();
  });
});

describe("SEO panel", () => {
  it("previews search and social appearance and lists checks", async () => {
    const user = userEvent.setup();
    renderApp(EDIT);
    await user.click(await screen.findByRole("tab", { name: /SEO/ }));
    const search = screen.getByTestId("search-preview");
    expect(within(search).getByText("Finding Calm")).toBeInTheDocument();
    await user.type(screen.getByLabelText("SEO title"), "Calm in busy weeks");
    expect(within(search).getByText("Calm in busy weeks")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("social-preview")).getByText("Calm in busy weeks"),
    ).toBeVisible();
    expect(await screen.findByText("No meta description.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("URL slug"));
    await user.type(screen.getByLabelText("URL slug"), "taken");
    expect(await screen.findByText(/already used by another article/)).toBeInTheDocument();
  });

  it("locks indexing controls without the SEO permission", async () => {
    const user = userEvent.setup();
    renderApp(EDIT, { adminApi: createFakeAdminApi({ role: "editor" }) });
    await user.click(await screen.findByRole("tab", { name: /SEO/ }));
    expect(screen.getByLabelText("Canonical URL")).toBeDisabled();
    expect(screen.getByLabelText(/noindex/)).toBeDisabled();
    expect(screen.getByLabelText("SEO title")).toBeEnabled();
  });
});

describe("publishing a live article", () => {
  const live = () =>
    makeArticle({
      status: "published",
      is_public: true,
      published_at: "2026-10-01T10:00:00.000Z",
      first_published_at: "2026-10-01T10:00:00.000Z",
      slug_locked: true,
      has_pending_changes: true,
      pending_fields: ["excerpt"],
    });

  it("lets publishers publish or discard unpublished changes", async () => {
    const user = userEvent.setup();
    const adminApi = createFakeAdminApi({ role: "editor", article: live() });
    renderApp(EDIT, { adminApi });
    expect(await screen.findByText(/Unpublished changes/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Publish changes/ }));
    await waitFor(() => expect(adminApi.articles.publishChanges).toHaveBeenCalledWith("7", 1));
    expect(await screen.findByText(/Changes published/)).toBeInTheDocument();
  });

  it("asks non-publishers to save for review and hides publishing", async () => {
    renderApp(EDIT, { adminApi: createFakeAdminApi({ role: "content_editor", article: live() }) });
    expect(await screen.findByRole("button", { name: "Save for review" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Publish changes/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish now" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discard" })).toBeInTheDocument();
  });
});

describe("draft preview", () => {
  it("renders the private preview with a not-public banner", async () => {
    const adminApi = createFakeAdminApi();
    adminApi.articles.preview = vi.fn(() =>
      Promise.resolve({
        data: {
          article: {
            title: "Preview title",
            subtitle: null,
            body: [{ type: "paragraph", text: "Draft words." }],
            author: { name: "TPA Editorial" },
            image: null,
            topic: null,
            published_at: null,
          },
          status: "draft",
          has_pending_changes: false,
        },
      }),
    );
    renderApp("/admin/articles/7/preview", { adminApi });
    expect(await screen.findByRole("heading", { level: 1, name: "Preview title" })).toBeVisible();
    expect(screen.getByText(/Private preview · draft/)).toBeInTheDocument();
    expect(screen.getByText(/not public, not indexed/)).toBeInTheDocument();
    expect(screen.getByText("Draft words.")).toBeInTheDocument();
  });

  it("requires the preview permission", async () => {
    renderApp("/admin/articles/7/preview", {
      adminApi: createFakeAdminApi({ role: "pages_only" }),
    });
    expect(await screen.findByText("You don't have access to this area")).toBeInTheDocument();
  });
});

describe("useAutosave", () => {
  afterEach(() => vi.useRealTimers());

  const setup = (save, initial = { payload: { title: "a" }, dirty: true }) =>
    renderHook(
      (props) => useAutosave({ enabled: true, lockVersion: 1, save, delay: 1000, ...props }),
      {
        initialProps: initial,
      },
    );

  it("debounces bursts of changes into one request", async () => {
    vi.useFakeTimers();
    const save = vi.fn(() => Promise.resolve({ data: { lock_version: 2 } }));
    const { rerender, result } = setup(save);
    for (const title of ["ab", "abc", "abcd"]) {
      rerender({ payload: { title }, dirty: true });
      await act(() => vi.advanceTimersByTimeAsync(400));
    }
    expect(save).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({ title: "abcd" }, 1);
    expect(result.current.status).toBe("pending"); // still dirty until the parent updates
  });

  it("queues edits made while a save is in flight", async () => {
    vi.useFakeTimers();
    let resolveFirst;
    const save = vi
      .fn()
      .mockImplementationOnce(() => new Promise((r) => (resolveFirst = r)))
      .mockImplementation(() => Promise.resolve({ data: {} }));
    const { rerender } = setup(save);
    await act(() => vi.advanceTimersByTimeAsync(1000));
    rerender({ payload: { title: "newer" }, dirty: true });
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(save).toHaveBeenCalledTimes(1); // one request at a time
    await act(async () => resolveFirst({ data: {} }));
    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls[1][0]).toEqual({ title: "newer" });
  });

  it("stops on edit conflicts and retries network failures", async () => {
    vi.useFakeTimers();
    const conflict = vi.fn(() =>
      Promise.reject(
        new ApiError({ status: 409, code: "edit_conflict", details: { lock_version: 4 } }),
      ),
    );
    const { result } = setup(conflict);
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(result.current.status).toBe("conflict");
    expect(result.current.conflict).toEqual({ lock_version: 4 });
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(conflict).toHaveBeenCalledTimes(1);

    const flaky = vi
      .fn()
      .mockImplementationOnce(() =>
        Promise.reject(new ApiError({ status: 0, code: "network_error" })),
      )
      .mockImplementation(() => Promise.resolve({ data: {} }));
    const second = setup(flaky);
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(second.result.current.status).toBe("error");
    await act(() => vi.advanceTimersByTimeAsync(2500));
    expect(flaky).toHaveBeenCalledTimes(2);
  });
});

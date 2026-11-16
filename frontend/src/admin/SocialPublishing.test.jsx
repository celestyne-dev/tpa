import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { createFakeAdminApi, makeArticle } from "@/test/adminFake";
import { disconnected } from "@/test/socialFake";
import { preloadAdminApp, renderApp } from "@/test/utils";
import { leaveTo } from "./pages/social/leave";
import { socialComposeLink, socialPostsLink } from "./pages/social/socialLinks";

vi.mock("./pages/social/leave", () => ({ leaveTo: vi.fn() }));

beforeAll(preloadAdminApp);

const sidebar = () => screen.getAllByRole("navigation", { name: "Admin" })[0];

describe("integrations", () => {
  it("shows the connected accounts and starts the Pinterest connection for a Super Admin", async () => {
    const adminApi = createFakeAdminApi();
    adminApi.socialState.accounts = [disconnected("pinterest"), disconnected("instagram")];
    renderApp("/admin/integrations", { adminApi });
    const card = (await screen.findByRole("heading", { level: 2, name: "Pinterest" })).closest(
      "section",
    );
    expect(within(card).getByText("Not connected")).toBeInTheDocument();
    expect(
      within(card).getByText(
        "https://thinkpositivealways.com/admin/integrations/pinterest/callback",
      ),
    ).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Connect Pinterest" }));
    await waitFor(() =>
      expect(leaveTo).toHaveBeenCalledWith("https://www.pinterest.com/oauth/?state=signed-state"),
    );
    expect(screen.getByRole("heading", { name: "Claim the website on Pinterest" })).toBeVisible();
    // Importing needs a connected Instagram account.
    expect(
      screen.queryByRole("heading", { name: "Import images from Instagram" }),
    ).not.toBeInTheDocument();
  });

  it("shows that the Instagram authorisation does not expire and Pinterest's renews", async () => {
    renderApp("/admin/integrations", { adminApi: createFakeAdminApi() });
    const instagram = (await screen.findByRole("heading", { level: 2, name: "Instagram" })).closest(
      "section",
    );
    expect(within(instagram).getByText(/Does not expire/)).toBeVisible();
    expect(within(instagram).getByText("instagram_basic, instagram_content_publish")).toBeVisible();
    const pinterest = screen
      .getByRole("heading", { level: 2, name: "Pinterest" })
      .closest("section");
    expect(within(pinterest).getByText(/renewed automatically/)).toBeVisible();
    expect(within(pinterest).getByText(/boards:write/)).toBeVisible();
  });

  it("explains missing server settings instead of failing", async () => {
    const adminApi = createFakeAdminApi();
    adminApi.socialState.accounts = [
      disconnected("pinterest", {
        setup: { ready: false, missing: ["PINTEREST_CLIENT_ID", "SOCIAL_TOKEN_ENCRYPTION_KEY"] },
      }),
      disconnected("instagram"),
    ];
    renderApp("/admin/integrations", { adminApi });
    expect(await screen.findByText(/Pinterest is not set up on the server yet/)).toBeVisible();
    expect(screen.getByText("SOCIAL_TOKEN_ENCRYPTION_KEY")).toBeVisible();
    expect(screen.getByRole("button", { name: "Connect Pinterest" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Connect Instagram" })).toBeEnabled();
  });

  it("lets administrators see accounts without connecting or disconnecting them", async () => {
    renderApp("/admin/integrations", {
      adminApi: createFakeAdminApi({ role: "administrator" }),
    });
    await screen.findByRole("heading", { level: 2, name: "Instagram" });
    expect(screen.queryByRole("button", { name: /Reconnect|Disconnect/ })).not.toBeInTheDocument();
    expect(screen.getAllByText(/Only a Super Admin can connect/)).toHaveLength(2);
  });

  it("completes the connection once when the platform sends the administrator back", async () => {
    const adminApi = createFakeAdminApi();
    renderApp("/admin/integrations/instagram/callback?code=abc%23_&state=signed-state", {
      adminApi,
    });
    await screen.findByRole("heading", { level: 1, name: "Integrations" });
    expect(adminApi.social.callback).toHaveBeenCalledTimes(1);
    expect(adminApi.social.callback).toHaveBeenCalledWith("instagram", {
      code: "abc",
      state: "signed-state",
    });
  });

  it("reports a connection the administrator refused", async () => {
    const adminApi = createFakeAdminApi();
    renderApp("/admin/integrations/pinterest/callback?error=access_denied", { adminApi });
    expect(await screen.findByText(/was not approved on Pinterest/)).toBeVisible();
    expect(adminApi.social.callback).not.toHaveBeenCalled();
  });

  it("reports a forged or expired connection request", async () => {
    const adminApi = createFakeAdminApi();
    renderApp("/admin/integrations/pinterest/callback?code=abc&state=forged", { adminApi });
    expect(await screen.findByText(/connection request is invalid/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Back to Integrations" })).toBeVisible();
  });

  it("previews an Instagram image and imports it only after ownership is confirmed", async () => {
    const adminApi = createFakeAdminApi();
    renderApp("/admin/integrations", { adminApi });
    await userEvent.click(await screen.findByRole("button", { name: "Show my Instagram posts" }));
    expect(await screen.findByText(/Video: not importable/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Preview and import" }));
    const dialog = await screen.findByRole("dialog", { name: "Import this image" });
    const submit = within(dialog).getByRole("button", { name: "Import image" });
    expect(submit).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Alt text/), "A sunrise quote card");
    expect(submit).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("checkbox"));
    await userEvent.click(submit);
    await waitFor(() =>
      expect(adminApi.social.importInstagram).toHaveBeenCalledWith({
        external_id: "1790001",
        alt_text: "A sunrise quote card",
        ownership_confirmed: true,
      }),
    );
    expect(await screen.findByRole("link", { name: /Imported/ })).toBeVisible();
  });
});

describe("social publishing", () => {
  it("is in the menu for roles with the permission", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "marketing_manager" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    expect(within(sidebar()).getByRole("link", { name: "Social publishing" })).toBeVisible();
    expect(within(sidebar()).getByRole("link", { name: "Integrations" })).toBeVisible();
  });

  it("is hidden from roles without it", async () => {
    renderApp("/admin", { adminApi: createFakeAdminApi({ role: "content_writer" }) });
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    expect(
      within(sidebar()).queryByRole("link", { name: "Social publishing" }),
    ).not.toBeInTheDocument();
    expect(within(sidebar()).queryByRole("link", { name: "Integrations" })).not.toBeInTheDocument();
  });

  it("sends a Pin for a quote collection, linking to the collection", async () => {
    const quote = makeArticle({ id: 5, title: "30 Quotes About Confidence", status: "published" });
    const adminApi = createFakeAdminApi({ article: { ...quote, content_type: "quotes" } });
    renderApp(socialComposeLink({ platform: "pinterest", media: 3, article: 5 }), { adminApi });
    const form = await screen.findByRole("form", { name: "New post" });
    expect(await within(form).findByText("30 Quotes About Confidence")).toBeVisible();
    expect(within(form).getByText(/the Pin links to this quote collection’s page/)).toBeVisible();
    expect(within(form).queryByLabelText(/Destination link/)).not.toBeInTheDocument();
    await waitFor(() =>
      expect(within(form).getByLabelText(/Pin title/)).toHaveValue("30 Quotes About Confidence"),
    );
    await userEvent.selectOptions(await within(form).findByLabelText(/Board/), "b2");
    await userEvent.type(within(form).getByLabelText(/Pin description/), "Save for later");
    await userEvent.click(within(form).getByRole("button", { name: "Send to Pinterest" }));
    await waitFor(() => expect(adminApi.social.createPost).toHaveBeenCalledTimes(1));
    expect(adminApi.social.createPost.mock.calls[0][0]).toMatchObject({
      platform: "pinterest",
      media_asset_id: 3,
      article_id: 5,
      board_id: "b2",
      title: "30 Quotes About Confidence",
      text: "Save for later",
      scheduled_at: null,
    });
    expect(adminApi.social.createPost.mock.calls[0][0].destination_url).toBeUndefined();
  });

  it("asks before publishing the same image twice", async () => {
    const adminApi = createFakeAdminApi();
    adminApi.socialState.published.add("instagram:3");
    renderApp(socialComposeLink({ platform: "instagram", media: 3 }), { adminApi });
    const form = await screen.findByRole("form", { name: "New post" });
    expect(within(form).getByText(/not clickable/)).toBeVisible();
    expect(within(form).queryByLabelText(/Board/)).not.toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText(/Caption/), "Keep going #courage");
    await userEvent.click(within(form).getByRole("button", { name: "Publish to Instagram" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish this image again?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Publish again" }));
    await waitFor(() => expect(adminApi.social.createPost).toHaveBeenCalledTimes(2));
    expect(adminApi.social.createPost.mock.calls[1][0]).toMatchObject({
      platform: "instagram",
      text: "Keep going #courage",
      allow_repeat: true,
    });
  });

  it("schedules a post and requires a time", async () => {
    const adminApi = createFakeAdminApi();
    renderApp(socialComposeLink({ platform: "instagram", media: 3, schedule: true }), { adminApi });
    const form = await screen.findByRole("form", { name: "New post" });
    await userEvent.type(within(form).getByLabelText(/Caption/), "Tomorrow");
    await userEvent.click(within(form).getByRole("button", { name: "Schedule post" }));
    expect(await within(form).findByText("Choose a date and time.")).toBeVisible();
    expect(adminApi.social.createPost).not.toHaveBeenCalled();
    await userEvent.type(within(form).getByLabelText(/Date and time/), "2027-01-05T09:30");
    await userEvent.click(within(form).getByRole("button", { name: "Schedule post" }));
    await waitFor(() => expect(adminApi.social.createPost).toHaveBeenCalledTimes(1));
    expect(adminApi.social.createPost.mock.calls[0][0].scheduled_at).toBe(
      new Date("2027-01-05T09:30").toISOString(),
    );
  });

  it("lists the queue, history and failures with cancel, retry and permalinks", async () => {
    const adminApi = createFakeAdminApi();
    renderApp("/admin/social", { adminApi });
    const queue = await screen.findByRole("table", { name: "Scheduled queue" });
    await userEvent.click(within(queue).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(adminApi.social.cancelPost).toHaveBeenCalledWith(1));
    await userEvent.click(screen.getByRole("tab", { name: "Published" }));
    const published = await screen.findByRole("table", { name: "Published" });
    expect(within(published).getByRole("link", { name: /View on Pinterest/ })).toHaveAttribute(
      "href",
      "https://www.pinterest.com/pin/p9/",
    );
    await userEvent.click(screen.getByRole("tab", { name: "Failed and cancelled" }));
    const failed = await screen.findByRole("table", { name: "Failed and cancelled" });
    expect(within(failed).getByText("Instagram could not process the image.")).toBeVisible();
    await userEvent.click(within(failed).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(adminApi.social.retryPost).toHaveBeenCalledWith(3));
  });

  it("points to Integrations when no account is connected and hides the composer from viewers", async () => {
    const adminApi = createFakeAdminApi();
    adminApi.socialState.accounts = [disconnected("pinterest"), disconnected("instagram")];
    renderApp("/admin/social?media=3", { adminApi });
    const form = await screen.findByRole("form", { name: "New post" });
    expect(within(form).getByRole("note")).toHaveTextContent("Pinterest is not connected");
    expect(within(form).getByRole("button", { name: "Send to Pinterest" })).toBeDisabled();
  });

  it("filters posts to one image from the Media Library link", async () => {
    const adminApi = createFakeAdminApi();
    renderApp(socialPostsLink(3), { adminApi });
    expect(await screen.findByText("Showing posts made from one image.")).toBeVisible();
    await waitFor(() =>
      expect(adminApi.social.posts).toHaveBeenCalledWith(
        expect.objectContaining({ media_asset_id: 3, view: "published" }),
      ),
    );
  });
});

describe("contextual actions", () => {
  it("builds links that pre-select the image and its collection", () => {
    expect(socialComposeLink({ platform: "pinterest", media: 3, article: 5 })).toBe(
      "/admin/social?platform=pinterest&media=3&article=5",
    );
    expect(socialComposeLink({ media: 3, schedule: true })).toBe(
      "/admin/social?media=3&when=schedule",
    );
  });

  it("offers the social actions on a Media Library image", async () => {
    renderApp("/admin/media", { adminApi: createFakeAdminApi() });
    await userEvent.click(await screen.findByRole("button", { name: "Open Calm lake" }));
    const dialog = await screen.findByRole("dialog", { name: "Calm lake" });
    const nav = within(dialog).getByRole("navigation", { name: "Social publishing" });
    expect(within(nav).getByRole("link", { name: "Send to Pinterest" })).toHaveAttribute(
      "href",
      "/admin/social?platform=pinterest&media=3",
    );
    for (const name of ["Publish to Instagram", "Schedule social post", "View social posts"]) {
      expect(within(nav).getByRole("link", { name })).toBeVisible();
    }
  });

  it("hides them from people without social permissions", async () => {
    renderApp("/admin/media", { adminApi: createFakeAdminApi({ role: "editor" }) });
    await userEvent.click(await screen.findByRole("button", { name: "Open Calm lake" }));
    const dialog = await screen.findByRole("dialog", { name: "Calm lake" });
    expect(
      within(dialog).queryByRole("navigation", { name: "Social publishing" }),
    ).not.toBeInTheDocument();
  });
});

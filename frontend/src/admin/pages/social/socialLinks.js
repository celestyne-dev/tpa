/** Links into Admin › Social Publishing with an image (and its article) pre-selected. */
export function socialComposeLink({ platform, media, article, schedule } = {}) {
  const params = new URLSearchParams();
  if (platform) params.set("platform", platform);
  if (media) params.set("media", String(media));
  if (article) params.set("article", String(article));
  if (schedule) params.set("when", "schedule");
  return `/admin/social?${params.toString()}`;
}

export function socialPostsLink(media) {
  return `/admin/social?posts_for=${media}`;
}

export const PLATFORM_LABELS = { pinterest: "Pinterest", instagram: "Instagram" };

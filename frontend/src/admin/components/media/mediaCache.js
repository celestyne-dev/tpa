/** Session cache of media summaries, so block previews don't refetch the same image. */
export const mediaCache = new Map();

export function rememberMedia(asset) {
  if (asset?.id) mediaCache.set(asset.id, asset);
}

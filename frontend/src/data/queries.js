/** Shared article list queries (keep page hooks and prerender loaders on the same cache keys). */
export const PAGE_SIZE = 12;
export const FEATURED_QUERY = { featured: true, page: 1, pageSize: 3 };
export const LATEST_QUERY = { page: 1, pageSize: 3 };
export const ARTICLE_LIST_QUERY = { page: 1, pageSize: PAGE_SIZE };
export const articleListQuery = (page = 1) => ({ page, pageSize: PAGE_SIZE });
export const topicArticlesQuery = (slug, page = 1) => ({ topic: slug, page, pageSize: PAGE_SIZE });

/** Page number from a /page/:page route segment: 1 for none, null when invalid. */
export function pageParam(value) {
  if (value === undefined) return 1;
  if (!/^[1-9][0-9]{0,3}$/.test(value)) return null;
  return Number(value);
}

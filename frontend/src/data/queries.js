/** Shared article list queries (keep page hooks and prerender loaders on the same cache keys). */
export const FEATURED_QUERY = { featured: true, page: 1, pageSize: 3 };
export const LATEST_QUERY = { page: 1, pageSize: 3 };
export const ARTICLE_LIST_QUERY = { page: 1, pageSize: 12 };
export const topicArticlesQuery = (slug) => ({ topic: slug, page: 1, pageSize: 12 });

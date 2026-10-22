import { createApiClient } from "./apiClient";

/**
 * Content API for the Flask `/api/v1` endpoints. Each method resolves to the
 * response envelope `{ data, meta }` and rejects with an ApiError.
 */
export function createContentApi(client = createApiClient()) {
  const get = (url, params) => client.get(url, { params }).then((res) => res.data);
  return {
    getSite: () => get("/site"),
    getTopics: (params) => get("/topics", params),
    getTopic: (slug) => get(`/topics/${encodeURIComponent(slug)}`),
    getArticles: (params) => get("/articles", params),
    getArticle: (slug) => get(`/articles/${encodeURIComponent(slug)}`),
    getProducts: () => get("/products"),
    getPage: (path) => get("/pages/resolve", { path }),
    getPages: () => get("/pages"),
    getSitemap: () => get("/sitemap"),
    getRedirects: () => get("/redirects"),
    resolveRedirect: (path) => get("/redirects/resolve", { path }),
  };
}

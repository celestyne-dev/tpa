import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import { App } from "@/app/App";
import { loadAdminApp } from "@/routes/loadAdminApp";
import { ApiError } from "@/services/apiClient";
import { createAppStore } from "@/store";
import { createFakeAdminApi } from "./adminFake";
import * as fx from "./fixtures";

export const notFound = (message = "Not found") =>
  Promise.reject(new ApiError({ status: 404, code: "not_found", message }));

/**
 * Load the code-split admin chunk before a file's tests run (`beforeAll(preloadAdminApp)`).
 * Otherwise the first admin render in each file triggers Vite's on-demand transform of
 * the whole admin module graph, which on a cold cache or slower machine can take longer
 * than a `findBy*` query waits, making the first test in the file fail.
 */
export async function preloadAdminApp() {
  await loadAdminApp();
}

/** In-memory implementation of the content API used by the store's thunks. */
export function createFakeApi(overrides = {}) {
  const paginate = (items, params = {}) => {
    const page = params.page ?? 1;
    const size = params.page_size ?? 12;
    const total_pages = Math.max(1, Math.ceil(items.length / size));
    return {
      data: items.slice((page - 1) * size, page * size),
      meta: {
        pagination: {
          page,
          page_size: size,
          total: items.length,
          total_pages,
          has_next: page < total_pages,
          has_prev: page > 1,
        },
      },
    };
  };
  return {
    getSite: vi.fn(async () => ({ data: fx.site })),
    getTopics: vi.fn(async () => ({ data: fx.topics })),
    getTopic: vi.fn(async (slug) => {
      const topic = fx.topics.find((t) => t.slug === slug);
      return topic ? { data: topic } : notFound();
    }),
    getArticles: vi.fn(async (params = {}) => {
      let items = fx.articles;
      if (params.topic) items = items.filter((a) => a.topic_slug === params.topic);
      if (params.featured !== undefined)
        items = items.filter((a) => a.featured === params.featured);
      return paginate(items, params);
    }),
    getArticle: vi.fn(async (slug) =>
      slug === fx.articleDetail.slug
        ? { data: { article: fx.articleDetail, related: fx.articles.slice(1) } }
        : notFound(),
    ),
    getProducts: vi.fn(async () => ({ data: fx.products })),
    getPage: vi.fn(async (path) => {
      if (path === "/") return { data: fx.homePage };
      return fx.cmsPages[path] ? { data: fx.cmsPages[path] } : notFound("Page not found.");
    }),
    getPages: vi.fn(async () => ({
      data: Object.values(fx.cmsPages).map((p) => ({ path: p.path, title: p.title })),
    })),
    ...overrides,
  };
}

export function renderApp(
  path = "/",
  { api = createFakeApi(), adminApi = createFakeAdminApi(), preloadedState } = {},
) {
  const store = createAppStore({ api, adminApi, preloadedState });
  const utils = render(
    <MemoryRouter initialEntries={[path]}>
      <App store={store} adminApi={adminApi} />
    </MemoryRouter>,
  );
  return { ...utils, store, api, adminApi };
}

import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/** Stable cache key for an article list query. */
export function articleListKey({ topic, featured, page = 1, pageSize = 12 } = {}) {
  return [
    `topic=${topic ?? ""}`,
    `featured=${featured ?? ""}`,
    `page=${page}`,
    `page_size=${pageSize}`,
  ].join("&");
}

function toParams({ topic, featured, page = 1, pageSize = 12 } = {}) {
  return {
    ...(topic && { topic }),
    ...(featured !== undefined && { featured }),
    page,
    page_size: pageSize,
  };
}

export const fetchArticles = createAsyncThunk(
  "articles/fetchList",
  async (query = {}, { extra, rejectWithValue }) => {
    try {
      const { data, meta } = await extra.api.getArticles(toParams(query));
      return { items: data, pagination: meta?.pagination ?? null };
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: (query = {}, { getState }) =>
      shouldFetch(getState().articles.lists[articleListKey(query)], query.force),
  },
);

export const fetchArticle = createAsyncThunk(
  "articles/fetchOne",
  async ({ slug }, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getArticle(slug)).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: ({ slug, force }, { getState }) =>
      shouldFetch(getState().articles.bySlug[slug], force),
  },
);

const articlesSlice = createSlice({
  name: "articles",
  initialState: { lists: {}, bySlug: {} },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchArticles.pending, (state, action) => {
        const key = articleListKey(action.meta.arg);
        state.lists[key] = { ...state.lists[key], status: Status.loading, error: null };
      })
      .addCase(fetchArticles.fulfilled, (state, action) => {
        state.lists[articleListKey(action.meta.arg)] = {
          ...action.payload,
          status: Status.succeeded,
          error: null,
        };
      })
      .addCase(fetchArticles.rejected, (state, action) => {
        state.lists[articleListKey(action.meta.arg)] = {
          items: [],
          pagination: null,
          status: Status.failed,
          error: action.payload ?? serializeError(action.error),
        };
      })
      .addCase(fetchArticle.pending, (state, action) => {
        state.bySlug[action.meta.arg.slug] = { status: Status.loading, error: null };
      })
      .addCase(fetchArticle.fulfilled, (state, action) => {
        state.bySlug[action.meta.arg.slug] = {
          article: action.payload.article,
          related: action.payload.related,
          status: Status.succeeded,
          error: null,
        };
      })
      .addCase(fetchArticle.rejected, (state, action) => {
        state.bySlug[action.meta.arg.slug] = {
          status: Status.failed,
          error: action.payload ?? serializeError(action.error),
        };
      });
  },
});

export const selectArticleList = (query) => (state) => state.articles.lists[articleListKey(query)];
export const selectArticle = (slug) => (state) => state.articles.bySlug[slug];
export default articlesSlice.reducer;

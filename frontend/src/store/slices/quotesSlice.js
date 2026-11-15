import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/** Quote collections (/quotes): lists by topic, search and page, and collections by slug. */
export function quoteListKey({ topic, q, featured, page = 1, pageSize = 12 } = {}) {
  return [
    `topic=${topic ?? ""}`,
    `q=${q ?? ""}`,
    `featured=${featured ?? ""}`,
    `page=${page}`,
    `page_size=${pageSize}`,
  ].join("&");
}

function toParams({ topic, q, featured, page = 1, pageSize = 12 } = {}) {
  return {
    ...(topic && { topic }),
    ...(q && { q }),
    ...(featured !== undefined && { featured }),
    page,
    page_size: pageSize,
  };
}

export const fetchQuoteCollections = createAsyncThunk(
  "quotes/fetchList",
  async (query = {}, { extra, rejectWithValue }) => {
    try {
      const { data, meta } = await extra.api.getQuotes(toParams(query));
      return { items: data, pagination: meta?.pagination ?? null, topics: meta?.topics ?? [] };
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: (query = {}, { getState }) =>
      shouldFetch(getState().quotes.lists[quoteListKey(query)], query.force),
  },
);

export const fetchQuoteCollection = createAsyncThunk(
  "quotes/fetchOne",
  async ({ slug }, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getQuote(slug)).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: ({ slug, force }, { getState }) =>
      shouldFetch(getState().quotes.bySlug[slug], force),
  },
);

const quotesSlice = createSlice({
  name: "quotes",
  initialState: { lists: {}, bySlug: {} },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchQuoteCollections.pending, (state, action) => {
        const key = quoteListKey(action.meta.arg);
        state.lists[key] = { ...state.lists[key], status: Status.loading, error: null };
      })
      .addCase(fetchQuoteCollections.fulfilled, (state, action) => {
        state.lists[quoteListKey(action.meta.arg)] = {
          ...action.payload,
          status: Status.succeeded,
          error: null,
        };
      })
      .addCase(fetchQuoteCollections.rejected, (state, action) => {
        state.lists[quoteListKey(action.meta.arg)] = {
          items: [],
          pagination: null,
          topics: [],
          status: Status.failed,
          error: action.payload ?? serializeError(action.error),
        };
      })
      .addCase(fetchQuoteCollection.pending, (state, action) => {
        state.bySlug[action.meta.arg.slug] = { status: Status.loading, error: null };
      })
      .addCase(fetchQuoteCollection.fulfilled, (state, action) => {
        state.bySlug[action.meta.arg.slug] = {
          data: action.payload,
          status: Status.succeeded,
          error: null,
        };
      })
      .addCase(fetchQuoteCollection.rejected, (state, action) => {
        state.bySlug[action.meta.arg.slug] = {
          status: Status.failed,
          error: action.payload ?? serializeError(action.error),
        };
      });
  },
});

export const selectQuoteList = (query) => (state) => state.quotes.lists[quoteListKey(query)];
export const selectQuoteCollection = (slug) => (state) => state.quotes.bySlug[slug];
export default quotesSlice.reducer;

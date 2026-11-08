import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/** Cache key for one page of an author's articles. */
export const authorKey = (slug, page = 1) => `${slug}:${page}`;

export const fetchAuthor = createAsyncThunk(
  "authors/fetchOne",
  async ({ slug, page = 1 }, { extra, rejectWithValue }) => {
    try {
      const { data, meta } = await extra.api.getAuthor(slug, { page });
      return { ...data, pagination: meta?.pagination ?? null };
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: ({ slug, page = 1, force }, { getState }) =>
      shouldFetch(getState().authors.byKey[authorKey(slug, page)], force),
  },
);

/** Writers who have an author page (the /authors index). */
export const fetchAuthors = createAsyncThunk(
  "authors/fetchList",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      const { data } = await extra.api.getAuthors();
      return data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  { condition: (arg, { getState }) => shouldFetch(getState().authors.list, arg?.force) },
);

/** Site search: results stay in the page (never prerendered or cached in the store). */
export const runSearch = createAsyncThunk(
  "authors/search",
  async ({ q, page = 1 }, { extra, rejectWithValue }) => {
    try {
      const { data, meta } = await extra.api.search({ q, page });
      return { ...data, pagination: meta?.pagination ?? null };
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
);

const authorsSlice = createSlice({
  name: "authors",
  initialState: { byKey: {}, list: undefined },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchAuthor.pending, (state, action) => {
        const { slug, page } = action.meta.arg;
        state.byKey[authorKey(slug, page)] = { status: Status.loading, error: null };
      })
      .addCase(fetchAuthor.fulfilled, (state, action) => {
        const { slug, page } = action.meta.arg;
        state.byKey[authorKey(slug, page)] = {
          ...action.payload,
          status: Status.succeeded,
          error: null,
        };
      })
      .addCase(fetchAuthors.pending, (state) => {
        state.list = { status: Status.loading, error: null, items: state.list?.items };
      })
      .addCase(fetchAuthors.fulfilled, (state, action) => {
        state.list = { status: Status.succeeded, error: null, items: action.payload };
      })
      .addCase(fetchAuthors.rejected, (state, action) => {
        state.list = {
          status: Status.failed,
          error: action.payload ?? serializeError(action.error),
        };
      })
      .addCase(fetchAuthor.rejected, (state, action) => {
        const { slug, page } = action.meta.arg;
        state.byKey[authorKey(slug, page)] = {
          status: Status.failed,
          error: action.payload ?? serializeError(action.error),
        };
      });
  },
});

export const selectAuthor =
  (slug, page = 1) =>
  (state) =>
    state.authors.byKey[authorKey(slug, page)];
export const selectAuthorList = (state) => state.authors.list;
export default authorsSlice.reducer;

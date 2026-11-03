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
  initialState: { byKey: {} },
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
export default authorsSlice.reducer;

import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/** Published CMS pages keyed by path (the homepage is "/"). */
export const fetchPage = createAsyncThunk(
  "pages/fetch",
  async ({ path }, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getPage(path)).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: ({ path, force }, { getState }) => shouldFetch(getState().pages.byPath[path], force),
  },
);

const pagesSlice = createSlice({
  name: "pages",
  initialState: { byPath: {} },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchPage.pending, (state, action) => {
        state.byPath[action.meta.arg.path] = { status: Status.loading, data: null, error: null };
      })
      .addCase(fetchPage.fulfilled, (state, action) => {
        state.byPath[action.meta.arg.path] = {
          status: Status.succeeded,
          data: action.payload,
          error: null,
        };
      })
      .addCase(fetchPage.rejected, (state, action) => {
        state.byPath[action.meta.arg.path] = {
          status: Status.failed,
          data: null,
          error: action.payload ?? serializeError(action.error),
        };
      });
  },
});

export const selectPage = (path) => (state) => state.pages.byPath[path];
export default pagesSlice.reducer;

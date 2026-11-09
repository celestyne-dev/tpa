import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/**
 * The published media kit. A 404 is an answer, not an error: it means the kit hasn't been
 * published yet, so it is stored as a successful result with no data (`data: null`). That
 * keeps the three outcomes apart (published, not published, failed) and stops the browser
 * from asking again after hydrating a prerendered "not published" page.
 */
export const fetchMediaKit = createAsyncThunk(
  "mediaKit/fetch",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getMediaKit()).data ?? null;
    } catch (error) {
      if (error?.status === 404) return null;
      return rejectWithValue(serializeError(error));
    }
  },
  { condition: (arg, { getState }) => shouldFetch(getState().mediaKit, arg?.force) },
);

const mediaKitSlice = createSlice({
  name: "mediaKit",
  initialState: { data: null, status: Status.idle, error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchMediaKit.pending, (state) => {
        state.status = Status.loading;
        state.error = null;
      })
      .addCase(fetchMediaKit.fulfilled, (state, action) => {
        state.status = Status.succeeded;
        state.data = action.payload;
      })
      .addCase(fetchMediaKit.rejected, (state, action) => {
        state.status = Status.failed;
        state.error = action.payload ?? serializeError(action.error);
      });
  },
});

export const selectMediaKit = (state) => state.mediaKit;
export default mediaKitSlice.reducer;

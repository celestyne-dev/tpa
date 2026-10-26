import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/** The published media kit (a 404 means it hasn't been published yet). */
export const fetchMediaKit = createAsyncThunk(
  "mediaKit/fetch",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getMediaKit()).data;
    } catch (error) {
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

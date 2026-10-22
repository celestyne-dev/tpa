import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

export const fetchSite = createAsyncThunk(
  "site/fetch",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getSite()).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  { condition: (arg, { getState }) => shouldFetch(getState().site, arg?.force) },
);

const siteSlice = createSlice({
  name: "site",
  initialState: { data: null, status: Status.idle, error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchSite.pending, (state) => {
        state.status = Status.loading;
        state.error = null;
      })
      .addCase(fetchSite.fulfilled, (state, action) => {
        state.status = Status.succeeded;
        state.data = action.payload;
      })
      .addCase(fetchSite.rejected, (state, action) => {
        state.status = Status.failed;
        state.error = action.payload ?? serializeError(action.error);
      });
  },
});

export const selectSite = (state) => state.site;
export default siteSlice.reducer;

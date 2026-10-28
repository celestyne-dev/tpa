import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/** Published membership plans and the billing status (Batch 10.1: billing not open yet). */
export const fetchMemberships = createAsyncThunk(
  "memberships/fetch",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getMemberships()).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  { condition: (arg, { getState }) => shouldFetch(getState().memberships, arg?.force) },
);

const membershipsSlice = createSlice({
  name: "memberships",
  initialState: { data: null, status: Status.idle, error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchMemberships.pending, (state) => {
        state.status = Status.loading;
        state.error = null;
      })
      .addCase(fetchMemberships.fulfilled, (state, action) => {
        state.status = Status.succeeded;
        state.data = action.payload;
      })
      .addCase(fetchMemberships.rejected, (state, action) => {
        state.status = Status.failed;
        state.error = action.payload ?? serializeError(action.error);
      });
  },
});

export const selectMemberships = (state) => state.memberships;
export default membershipsSlice.reducer;

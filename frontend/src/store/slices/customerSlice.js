import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, Status } from "../status";

/**
 * The signed-in customer (never an administrator). Loaded only in the browser,
 * on pages that need it; it is never part of prerendered state.
 */
export const fetchCustomer = createAsyncThunk(
  "customer/fetch",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      return { profile: (await extra.shopApi.me()).data.customer, expired: false };
    } catch (error) {
      // "session_expired": the browser presented a session that has ended (reported once).
      if (error?.status === 401)
        return { profile: null, expired: error.code === "session_expired" };
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: (arg, { getState }) => {
      const { status } = getState().customer;
      return arg?.force || (status !== Status.loading && status !== Status.succeeded);
    },
  },
);

const customerSlice = createSlice({
  name: "customer",
  initialState: { status: Status.idle, profile: null, error: null, sessionExpired: false },
  reducers: {
    customerSignedIn(state, action) {
      state.status = Status.succeeded;
      state.profile = action.payload;
      state.error = null;
      state.sessionExpired = false;
    },
    customerSignedOut(state) {
      state.status = Status.succeeded;
      state.profile = null;
      state.sessionExpired = false;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchCustomer.pending, (state) => {
        state.status = Status.loading;
      })
      .addCase(fetchCustomer.fulfilled, (state, action) => {
        state.status = Status.succeeded;
        state.profile = action.payload.profile;
        state.sessionExpired =
          action.payload.expired || (state.sessionExpired && !action.payload.profile);
      })
      .addCase(fetchCustomer.rejected, (state, action) => {
        state.status = Status.failed;
        state.error = action.payload ?? serializeError(action.error);
      });
  },
});

export const { customerSignedIn, customerSignedOut } = customerSlice.actions;
export const selectCustomer = (state) => state.customer;
export default customerSlice.reducer;

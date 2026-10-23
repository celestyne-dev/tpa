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
      return (await extra.shopApi.me()).data.customer;
    } catch (error) {
      if (error?.status === 401) return null;
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
  initialState: { status: Status.idle, profile: null, error: null },
  reducers: {
    customerSignedIn(state, action) {
      state.status = Status.succeeded;
      state.profile = action.payload;
      state.error = null;
    },
    customerSignedOut(state) {
      state.status = Status.succeeded;
      state.profile = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchCustomer.pending, (state) => {
        state.status = Status.loading;
      })
      .addCase(fetchCustomer.fulfilled, (state, action) => {
        state.status = Status.succeeded;
        state.profile = action.payload;
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

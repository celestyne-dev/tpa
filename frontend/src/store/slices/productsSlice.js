import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

export const fetchProducts = createAsyncThunk(
  "products/fetchAll",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getProducts()).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  { condition: (arg, { getState }) => shouldFetch(getState().products, arg?.force) },
);

const productsSlice = createSlice({
  name: "products",
  initialState: { items: [], status: Status.idle, error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchProducts.pending, (state) => {
        state.status = Status.loading;
        state.error = null;
      })
      .addCase(fetchProducts.fulfilled, (state, action) => {
        state.status = Status.succeeded;
        state.items = action.payload;
      })
      .addCase(fetchProducts.rejected, (state, action) => {
        state.status = Status.failed;
        state.error = action.payload ?? serializeError(action.error);
      });
  },
});

export const selectProducts = (state) => state.products;
export default productsSlice.reducer;

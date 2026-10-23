import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/** The published catalogue (prerendered). Filtering and sorting happen in the browser. */
export const fetchProducts = createAsyncThunk(
  "products/fetchAll",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      const { data, meta } = await extra.api.getProducts();
      return { items: data, meta: meta ?? {} };
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  { condition: (arg, { getState }) => shouldFetch(getState().products, arg?.force) },
);

export const fetchProduct = createAsyncThunk(
  "products/fetchOne",
  async ({ slug }, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getProduct(slug)).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: ({ slug, force }, { getState }) =>
      shouldFetch(getState().products.bySlug[slug], force),
  },
);

export const fetchCollection = createAsyncThunk(
  "products/fetchCollection",
  async ({ slug }, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getCollection(slug)).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: ({ slug, force }, { getState }) =>
      shouldFetch(getState().products.collections[slug], force),
  },
);

function keyed(builder, thunk, bucket) {
  builder
    .addCase(thunk.pending, (state, action) => {
      const { slug } = action.meta.arg;
      state[bucket][slug] = { ...state[bucket][slug], status: Status.loading, error: null };
    })
    .addCase(thunk.fulfilled, (state, action) => {
      state[bucket][action.meta.arg.slug] = {
        status: Status.succeeded,
        error: null,
        data: action.payload,
      };
    })
    .addCase(thunk.rejected, (state, action) => {
      state[bucket][action.meta.arg.slug] = {
        status: Status.failed,
        error: action.payload ?? serializeError(action.error),
      };
    });
}

const productsSlice = createSlice({
  name: "products",
  initialState: {
    items: [],
    meta: {},
    status: Status.idle,
    error: null,
    bySlug: {},
    collections: {},
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchProducts.pending, (state) => {
        state.status = Status.loading;
        state.error = null;
      })
      .addCase(fetchProducts.fulfilled, (state, action) => {
        state.status = Status.succeeded;
        state.items = action.payload.items;
        state.meta = action.payload.meta;
      })
      .addCase(fetchProducts.rejected, (state, action) => {
        state.status = Status.failed;
        state.error = action.payload ?? serializeError(action.error);
      });
    keyed(builder, fetchProduct, "bySlug");
    keyed(builder, fetchCollection, "collections");
  },
});

export const selectProducts = (state) => state.products;
export const selectProduct = (slug) => (state) => state.products.bySlug[slug];
export const selectCollection = (slug) => (state) => state.products.collections[slug];
export default productsSlice.reducer;

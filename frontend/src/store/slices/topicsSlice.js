import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

export const fetchTopics = createAsyncThunk(
  "topics/fetchAll",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getTopics()).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  { condition: (arg, { getState }) => shouldFetch(getState().topics.list, arg?.force) },
);

export const fetchTopic = createAsyncThunk(
  "topics/fetchOne",
  async ({ slug }, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getTopic(slug)).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: ({ slug, force }, { getState }) =>
      shouldFetch(getState().topics.bySlug[slug], force),
  },
);

const topicsSlice = createSlice({
  name: "topics",
  initialState: {
    list: { items: [], status: Status.idle, error: null },
    bySlug: {},
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchTopics.pending, (state) => {
        state.list.status = Status.loading;
        state.list.error = null;
      })
      .addCase(fetchTopics.fulfilled, (state, action) => {
        state.list.status = Status.succeeded;
        state.list.items = action.payload;
      })
      .addCase(fetchTopics.rejected, (state, action) => {
        state.list.status = Status.failed;
        state.list.error = action.payload ?? serializeError(action.error);
      })
      .addCase(fetchTopic.pending, (state, action) => {
        state.bySlug[action.meta.arg.slug] = { data: null, status: Status.loading, error: null };
      })
      .addCase(fetchTopic.fulfilled, (state, action) => {
        state.bySlug[action.meta.arg.slug] = {
          data: action.payload,
          status: Status.succeeded,
          error: null,
        };
      })
      .addCase(fetchTopic.rejected, (state, action) => {
        state.bySlug[action.meta.arg.slug] = {
          data: null,
          status: Status.failed,
          error: action.payload ?? serializeError(action.error),
        };
      });
  },
});

export const selectTopicList = (state) => state.topics.list;
export const selectTopic = (slug) => (state) => state.topics.bySlug[slug];
export default topicsSlice.reducer;

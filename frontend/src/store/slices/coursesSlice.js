import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError, shouldFetch, Status } from "../status";

/** The published course catalogue (prerendered). Filtering happens in the browser. */
export const fetchCourses = createAsyncThunk(
  "courses/fetchAll",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      const { data, meta } = await extra.api.getCourses();
      return { items: data, meta: meta ?? {} };
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  { condition: (arg, { getState }) => shouldFetch(getState().courses, arg?.force) },
);

/** One published course page (marketing content and syllabus titles only). */
export const fetchCourse = createAsyncThunk(
  "courses/fetchOne",
  async ({ slug }, { extra, rejectWithValue }) => {
    try {
      return (await extra.api.getCourse(slug)).data;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
  {
    condition: ({ slug, force }, { getState }) =>
      shouldFetch(getState().courses.bySlug[slug], force),
  },
);

const coursesSlice = createSlice({
  name: "courses",
  initialState: { items: [], meta: {}, status: Status.idle, error: null, bySlug: {} },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchCourses.pending, (state) => {
        state.status = Status.loading;
        state.error = null;
      })
      .addCase(fetchCourses.fulfilled, (state, action) => {
        state.status = Status.succeeded;
        state.items = action.payload.items;
        state.meta = action.payload.meta;
      })
      .addCase(fetchCourses.rejected, (state, action) => {
        state.status = Status.failed;
        state.error = action.payload ?? serializeError(action.error);
      })
      .addCase(fetchCourse.pending, (state, action) => {
        const { slug } = action.meta.arg;
        state.bySlug[slug] = { ...state.bySlug[slug], status: Status.loading, error: null };
      })
      .addCase(fetchCourse.fulfilled, (state, action) => {
        state.bySlug[action.meta.arg.slug] = {
          status: Status.succeeded,
          error: null,
          data: action.payload,
        };
      })
      .addCase(fetchCourse.rejected, (state, action) => {
        state.bySlug[action.meta.arg.slug] = {
          status: Status.failed,
          error: action.payload ?? serializeError(action.error),
        };
      });
  },
});

export const selectCourses = (state) => state.courses;
export const selectCourse = (slug) => (state) => state.courses.bySlug[slug];
export default coursesSlice.reducer;

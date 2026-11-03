import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { serializeError } from "../status";

/**
 * Admin session state. Only the signed-in user's profile and permissions are
 * kept here — never tokens (they live in HttpOnly cookies).
 */

export const loadSession = createAsyncThunk(
  "auth/loadSession",
  async (_arg, { extra, rejectWithValue }) => {
    try {
      return (await extra.adminApi.auth.me()).data.user;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
);

export const login = createAsyncThunk(
  "auth/login",
  async (credentials, { extra, rejectWithValue }) => {
    try {
      const { data } = await extra.adminApi.auth.login(credentials);
      // Accounts with two-step sign-in get a short-lived challenge instead of a session.
      return data.mfa_required ? { mfaToken: data.mfa_token } : data.user;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
);

/** Second sign-in step: a code from the authenticator app or a recovery code. */
export const verifyMfa = createAsyncThunk(
  "auth/verifyMfa",
  async ({ token, code }, { extra, rejectWithValue }) => {
    try {
      return (await extra.adminApi.auth.verifyMfa({ mfa_token: token, code })).data.user;
    } catch (error) {
      return rejectWithValue(serializeError(error));
    }
  },
);

export const logout = createAsyncThunk("auth/logout", async (_arg, { extra }) => {
  try {
    await extra.adminApi.auth.logout();
  } catch {
    // Cookies are cleared server-side when possible; local state is reset regardless.
  }
});

const initialState = {
  user: null,
  status: "idle",
  error: null,
  sessionExpired: false,
  mfaToken: null,
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    sessionExpired(state) {
      if (state.status === "authenticated") state.sessionExpired = true;
      state.user = null;
      state.status = "anonymous";
    },
    userUpdated(state, action) {
      state.user = action.payload;
    },
    /** Back from the code step to email and password. */
    mfaCancelled(state) {
      state.mfaToken = null;
      state.error = null;
    },
    /** A session was established outside the login form (e.g. invitation activation). */
    signedIn(state, action) {
      state.user = action.payload;
      state.status = "authenticated";
      state.sessionExpired = false;
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadSession.pending, (state) => {
        state.status = "loading";
      })
      .addCase(loadSession.fulfilled, (state, action) => {
        state.status = "authenticated";
        state.user = action.payload;
        state.error = null;
      })
      .addCase(loadSession.rejected, (state, action) => {
        state.status = "anonymous";
        state.user = null;
        // A plain "not signed in" is not an error worth showing.
        state.error = action.payload?.status === 401 ? null : action.payload;
      })
      .addCase(login.pending, (state) => {
        state.error = null;
      })
      .addCase(login.fulfilled, (state, action) => {
        state.error = null;
        if (action.payload?.mfaToken) {
          state.mfaToken = action.payload.mfaToken;
          return;
        }
        state.status = "authenticated";
        state.user = action.payload;
        state.sessionExpired = false;
        state.mfaToken = null;
      })
      .addCase(verifyMfa.pending, (state) => {
        state.error = null;
      })
      .addCase(verifyMfa.fulfilled, (state, action) => {
        state.status = "authenticated";
        state.user = action.payload;
        state.sessionExpired = false;
        state.error = null;
        state.mfaToken = null;
      })
      .addCase(verifyMfa.rejected, (state, action) => {
        state.error = action.payload ?? serializeError(action.error);
      })
      .addCase(login.rejected, (state, action) => {
        state.error = action.payload ?? serializeError(action.error);
      })
      .addCase(logout.fulfilled, () => ({ ...initialState, status: "anonymous" }));
  },
});

export const { sessionExpired, userUpdated, signedIn, mfaCancelled } = authSlice.actions;
export const selectAuth = (state) => state.auth;
export const selectPermissions = (state) => state.auth.user?.permissions ?? [];
export default authSlice.reducer;

import { afterEach, describe, expect, it, vi } from "vitest";
import { createAdminApi } from "./adminApi";

function respond(config, status, data) {
  const response = { data, status, statusText: String(status), headers: {}, config };
  if (status >= 400) {
    const error = new Error(`HTTP ${status}`);
    error.isAxiosError = true;
    error.config = config;
    error.response = response;
    return Promise.reject(error);
  }
  return Promise.resolve(response);
}

afterEach(() => {
  document.cookie = "csrf_access_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  document.cookie = "csrf_refresh_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("admin API client", () => {
  it("sends the CSRF cookie value on mutations only", async () => {
    document.cookie = "csrf_access_token=abc123; path=/";
    const seen = [];
    const api = createAdminApi({
      baseURL: "/api/v1/admin",
      adapter: (config) => {
        seen.push([config.method, config.headers["X-CSRF-TOKEN"]]);
        return respond(config, 200, { data: {} });
      },
    });
    await api.dashboard();
    await api.tags.create({ name: "Hope" });
    expect(seen).toEqual([
      ["get", undefined],
      ["post", "abc123"],
    ]);
  });

  it("uses the refresh CSRF value for logout and refresh", async () => {
    document.cookie = "csrf_access_token=access; path=/";
    document.cookie = "csrf_refresh_token=refresh; path=/";
    const seen = {};
    const api = createAdminApi({
      adapter: (config) => {
        seen[config.url] = config.headers["X-CSRF-TOKEN"];
        return respond(config, 200, { data: {} });
      },
    });
    await api.auth.logout();
    await api.auth.changePassword({});
    expect(seen).toEqual({ "/auth/logout": "refresh", "/auth/change-password": "access" });
  });

  it("refreshes an expired session once and retries the request", async () => {
    document.cookie = "csrf_refresh_token=r1; path=/";
    const calls = [];
    let expired = true;
    const api = createAdminApi({
      adapter: (config) => {
        calls.push(config.url);
        if (config.url === "/auth/refresh") {
          expect(config.headers["X-CSRF-TOKEN"]).toBe("r1");
          expired = false;
          return respond(config, 200, { data: {} });
        }
        if (expired)
          return respond(config, 401, { error: { code: "token_expired", message: "expired" } });
        return respond(config, 200, { data: { ok: true } });
      },
    });
    await expect(api.dashboard()).resolves.toEqual({ data: { ok: true } });
    expect(calls).toEqual(["/dashboard", "/auth/refresh", "/dashboard"]);
  });

  it("reports session expiry when refresh fails, without leaking tokens", async () => {
    const onExpired = vi.fn();
    const api = createAdminApi({
      adapter: (config) =>
        respond(config, 401, {
          error: {
            code: config.url === "/auth/refresh" ? "session_revoked" : "token_expired",
            message: "x",
          },
        }),
    });
    api.onSessionExpired(onExpired);
    await expect(api.dashboard()).rejects.toMatchObject({ status: 401 });
    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  it("does not try to refresh failed logins", async () => {
    const calls = [];
    const api = createAdminApi({
      adapter: (config) => {
        calls.push(config.url);
        return respond(config, 401, {
          error: { code: "authentication_failed", message: "Invalid email or password." },
        });
      },
    });
    await expect(api.auth.login({ email: "a", password: "b" })).rejects.toMatchObject({
      message: "Invalid email or password.",
    });
    expect(calls).toEqual(["/auth/login"]);
  });
});

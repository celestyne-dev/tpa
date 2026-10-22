import axios from "axios";
import { siteConfig } from "@/config/site";

/** Normalised API error used across the app (and stored in Redux as plain data). */
export class ApiError extends Error {
  constructor({ message, status = 0, code = "network_error", details } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  toJSON() {
    return { message: this.message, status: this.status, code: this.code, details: this.details };
  }
}

export function toApiError(error) {
  if (error instanceof ApiError) return error;
  if (axios.isAxiosError(error)) {
    if (error.response) {
      const payload = error.response.data?.error;
      return new ApiError({
        status: error.response.status,
        code: payload?.code ?? "http_error",
        message: payload?.message ?? "The server returned an unexpected response.",
        details: payload?.details,
      });
    }
    return new ApiError({
      code: error.code === "ECONNABORTED" ? "timeout" : "network_error",
      message: "We could not reach the Think Positive Always service.",
    });
  }
  return new ApiError({ code: "unknown_error", message: "Something went wrong." });
}

/** Creates a configured Axios instance. Server-side prerendering passes an absolute baseURL. */
export function createApiClient({ baseURL = siteConfig.apiBaseUrl, timeout = 10000 } = {}) {
  const client = axios.create({
    baseURL,
    timeout,
    headers: { Accept: "application/json" },
  });
  client.interceptors.response.use(
    (response) => response,
    (error) => Promise.reject(toApiError(error)),
  );
  return client;
}

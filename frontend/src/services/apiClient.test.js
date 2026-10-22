import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";
import { ApiError, toApiError } from "./apiClient";

describe("toApiError", () => {
  it("maps API error envelopes", () => {
    const err = new AxiosError(
      "fail",
      "ERR_BAD_REQUEST",
      {},
      {},
      {
        status: 404,
        data: { error: { code: "not_found", message: "Article 'x' was not found." } },
      },
    );
    expect(toApiError(err).toJSON()).toEqual({
      status: 404,
      code: "not_found",
      message: "Article 'x' was not found.",
      details: undefined,
    });
  });

  it("maps network failures and timeouts", () => {
    expect(toApiError(new AxiosError("down", "ERR_NETWORK")).code).toBe("network_error");
    expect(toApiError(new AxiosError("slow", "ECONNABORTED")).code).toBe("timeout");
  });

  it("passes through ApiError and wraps unknown errors", () => {
    const original = new ApiError({ status: 400, code: "validation_error", message: "bad" });
    expect(toApiError(original)).toBe(original);
    expect(toApiError(new Error("x")).code).toBe("unknown_error");
  });
});

export const Status = {
  idle: "idle",
  loading: "loading",
  succeeded: "succeeded",
  failed: "failed",
};

/** Skip a fetch when data is already loading or loaded (unless forced). */
export function shouldFetch(entry, force = false) {
  if (!entry) return true;
  if (entry.status === Status.loading) return false;
  return force || entry.status !== Status.succeeded;
}

export const serializeError = (error) =>
  typeof error?.toJSON === "function"
    ? error.toJSON()
    : { message: error?.message ?? "Something went wrong.", status: 0, code: "unknown_error" };

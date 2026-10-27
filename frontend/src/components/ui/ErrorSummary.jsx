import { useEffect, useRef } from "react";
import { errorLines } from "./errorLines";

/**
 * Accessible error summary shown above a form: receives focus when it appears so keyboard
 * and screen-reader users hear what needs fixing.
 */
export function ErrorSummary({ error, title = "Please check the following", className = "" }) {
  const ref = useRef(null);
  useEffect(() => {
    if (error) ref.current?.focus();
  }, [error]);
  if (!error) return null;
  const lines = errorLines(error);
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="alert"
      className={`rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 outline-none ${className}`}
    >
      <p className="font-medium">{lines.length ? title : error.message}</p>
      {lines.length > 0 && (
        <>
          {error.message && <p className="mt-1">{error.message}</p>}
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
